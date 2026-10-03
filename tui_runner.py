"""Profile Delegate's single-run TUI worker. Internal; called by core detached worker."""
from __future__ import annotations

import time
import os
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from . import tui_rpc
    from . import core
    from .event_journal import EventJournal
except ImportError:
    import tui_rpc  # type: ignore[no-redef]
    import core  # type: ignore[no-redef]
    from event_journal import EventJournal  # type: ignore[no-redef]


CANCEL_GRACE_SECONDS = 5.0
# Twice the 0.6s delayed follow-up regression observation in test_tui_rpc.py.
# This only bounds observation of an unobserved follow-up, never proves delivery.
PENDING_FOLLOWUP_OBSERVATION_SECONDS = 1.2


def _stage_timeout(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        value = default
    return min(600.0, max(1.0, value))


def _environment(request: Dict[str, Any], run_dir: Path) -> Dict[str, str]:
    return core.prepare_child_environment(request, run_dir, tui=True)


def _gateway_command(request: Dict[str, Any], run_dir: Path) -> list[str]:
    if __package__:
        from .execution import bootstrap_command
    else:
        from execution import bootstrap_command
    return [*bootstrap_command(request, run_dir), "--tui-gateway"]


def _poll_event(
    client: tui_rpc.TuiRpcClient, timeout: float, journal: EventJournal,
) -> Optional[Dict[str, Any]]:
    """Read one frame and drive timer-based journal flushing on idle polls."""
    try:
        return client.read_event(timeout)
    except tui_rpc.TuiTransportError as exc:
        if "timed out" not in str(exc):
            raise
        return None
    finally:
        journal.flush()


def _is_local_timeout(exc: BaseException) -> bool:
    return isinstance(exc, tui_rpc.TuiTransportError) and "timed out" in str(exc).lower()


def execute(run_dir: Path) -> Dict[str, Any]:
    request = core.read_json_file(run_dir / "request.json")
    timeout = int(request.get("timeout_seconds") or core.DEFAULT_TIMEOUT_SECONDS)
    # Includes actual gateway startup; never grant startup an unmeasured bonus.
    deadline = time.monotonic() + timeout
    cwd = Path(core.ensure_text(request.get("workdir"))).resolve()
    profile = core.ensure_text(request.get("profile"))
    mode = core.ensure_text(request.get("session_mode") or "new")
    resume_id = core.ensure_text(request.get("requested_session_id") or "")
    title = core.ensure_text(request.get("session_title") or "")
    client: Optional[tui_rpc.TuiRpcClient] = None
    ui_session_id = ""
    child_session_id = ""
    final_text = ""
    message_status = ""
    terminal_event = False
    turn_settled = False
    followup_started = False
    followup_completed = False
    accepted_steer = False
    steer_response_uncertain = False
    cancelled = False
    cancel_deadline: Optional[float] = None
    cancel_transport_diagnostic = ""
    cancel_interrupt_accepted = False
    cancel_identity_observed = False
    timed_out = False
    final_status = "failed"
    error_code: Optional[str] = None
    exit_code: Optional[int] = None
    journal = EventJournal(
        run_dir, task_id=core.ensure_text(request.get("task_id") or run_dir.name),
        persist_message_text=bool(request.get("persist_message_text", False)),
    )
    last_snapshot = 0.0
    last_observed_event = "none"
    startup_identity_events: list[Dict[str, Any]] = []

    def merge_status(updates: Dict[str, Any], *, force: bool = False, terminal: bool = False) -> None:
        nonlocal last_snapshot
        now = time.monotonic()
        if not force and now - last_snapshot < 0.5:
            return
        if terminal:
            core.merge_run_status(run_dir, updates, terminal=True)
            last_snapshot = now
        elif core.merge_run_status_best_effort(run_dir, updates):
            last_snapshot = now

    def persist_event(frame: Dict[str, Any]) -> None:
        nonlocal final_text, message_status, terminal_event, turn_settled, last_observed_event
        nonlocal followup_started, followup_completed, child_session_id
        raw_params = frame.get("params")
        params: Dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}
        if frame.get("method") != "event":
            return
        last_observed_event = core.ensure_text(params.get("type") or "unknown")
        event_sid = params.get("session_id")
        if not ui_session_id:
            # Retain only the identity portion before response correlation, with
            # the journal's existing startup-event budget, not a new depth cap.
            if params.get("type") == "session.info":
                if len(startup_identity_events) >= journal.max_pre_session_events:
                    raise tui_rpc.TuiProtocolError("startup identity evidence overflow")
                payload = params.get("payload")
                if isinstance(payload, dict):
                    startup_identity_events.append({"method": "event", "params": {
                        "type": "session.info", "session_id": event_sid,
                        "payload": {k: payload[k] for k in ("stored_session_id", "profile_name") if k in payload},
                    }})
            journal.ingest(frame)
            return
        if event_sid != ui_session_id:
            return
        if params.get("type") == "session.info":
            payload = params.get("payload")
            if isinstance(payload, dict) and "stored_session_id" in payload:
                if "profile_name" in payload and payload["profile_name"] != profile:
                    raise tui_rpc.TuiProtocolError("contradictory child profile identity")
                proposed = payload["stored_session_id"]
                if not core.valid_session_identity(proposed):
                    raise tui_rpc.TuiProtocolError("malformed stored child session identity")
                if proposed != child_session_id:
                    if not core.compression_continuation(
                        Path(request["profile_home"]), child_session_id, proposed,
                        profile=profile, ui_correlated=True,
                    ):
                        raise tui_rpc.TuiProtocolError("unproven child compression identity")
                    child_session_id = proposed
                    core.merge_run_status(run_dir, {"child_session_id": proposed})
        try:
            journal.ingest(frame)
            merge_status(journal.snapshot_fields())
        except Exception:
            merge_status({"observability_degraded": True}, force=True)
        if params.get("type") == "message.complete" and event_sid == ui_session_id:
            payload = params.get("payload") if isinstance(params.get("payload"), dict) else {}
            final_text = core.ensure_text(payload.get("text"))
            message_status = core.ensure_text(payload.get("status") or "complete")
            terminal_event = True
            turn_settled = False
            if followup_started:
                followup_completed = True
        elif params.get("type") == "message.start" and event_sid == ui_session_id:
            if accepted_steer and terminal_event:
                followup_started = True
            terminal_event = False
            turn_settled = False
        elif params.get("type") == "session.info" and event_sid == ui_session_id and terminal_event:
            turn_settled = True

    def process_controls() -> None:
        nonlocal cancelled, cancel_deadline, cancel_transport_diagnostic, accepted_steer, cancel_interrupt_accepted
        nonlocal steer_response_uncertain
        if client is None or not ui_session_id or cancelled:
            return
        for command_path, command in core._pending_control_commands(run_dir):
            command_type = core.ensure_text(command.get("type"))
            try:
                if command.get("claimed_at"):
                    core._ack_control(
                        run_dir, command_path, command, "delivery_unknown",
                        "worker restarted after delivery claim",
                    )
                    continue
                command["claimed_at"] = core.now_iso()
                core.json_safe_write(command_path, command)
                if command_type == "steer":
                    if terminal_event and turn_settled:
                        core._ack_control(run_dir, command_path, command, "rejected", "turn already settled")
                        continue
                    try:
                        response = tui_rpc.steer(
                            client, ui_session_id,
                            core.ensure_text((command.get("payload") or {}).get("text")),
                            on_event=persist_event,
                        )
                    except tui_rpc.TuiRemoteError as exc:
                        if exc.code != 4010:
                            raise
                        core._ack_control(
                            run_dir, command_path, command, "rejected",
                            f"native steer unavailable: {exc.message}",
                        )
                    except tui_rpc.TuiTransportError as exc:
                        if not _is_local_timeout(exc):
                            raise
                        # A local RPC timeout does not prove the native steer
                        # was rejected; it may have queued a later follow-up.
                        accepted_steer = True
                        steer_response_uncertain = True
                        core._ack_control(
                            run_dir, command_path, command, "delivery_unknown", str(exc)
                        )
                    else:
                        state = "accepted" if response.get("status") == "queued" else "rejected"
                        accepted_steer = accepted_steer or state == "accepted"
                        core._ack_control(run_dir, command_path, command, state)
                elif command_type == "cancel":
                    # Local cancellation is terminal authority. Establish its
                    # short deadline before attempting the best-effort native
                    # interrupt so an unready agent cannot consume the run timeout.
                    cancelled = True
                    cancel_deadline = time.monotonic() + CANCEL_GRACE_SECONDS
                    core.merge_run_status(
                        run_dir, {"status": "cancelling", "phase": "interrupting"}
                    )
                    detail = "native interrupt accepted"
                    try:
                        interrupt_budget = max(
                            0.001, (cancel_deadline - time.monotonic()) * 0.5,
                        )
                        tui_rpc.interrupt(
                            client, ui_session_id,
                            timeout=interrupt_budget,
                            on_event=persist_event,
                        )
                        cancel_interrupt_accepted = True
                    except tui_rpc.TuiRemoteError as exc:
                        detail = (
                            "native interrupt rejected; local cancellation authoritative: "
                            f"{exc}"
                        )
                    except tui_rpc.TuiTransportError as exc:
                        detail = (
                            "native interrupt delivery unknown; local cancellation authoritative: "
                            f"{exc}"
                        )
                        if not _is_local_timeout(exc):
                            cancel_transport_diagnostic = detail
                    except tui_rpc.TuiProtocolError as exc:
                        detail = (
                            "native interrupt protocol failure; local cancellation authoritative: "
                            f"{exc}"
                        )
                        cancel_transport_diagnostic = detail
                    core._ack_control(run_dir, command_path, command, "accepted", detail)
                    # Cancellation owns the remaining lifecycle. Do not drain
                    # later controls under its absolute cleanup deadline.
                    return
                else:
                    core._ack_control(
                        run_dir, command_path, command, "rejected", "unsupported command type"
                    )
            except Exception as exc:
                core._ack_control(
                    run_dir, command_path, command, "rejected",
                    f"{type(exc).__name__}: {exc}",
                )
                if command_type != "cancel" and isinstance(
                    exc, (tui_rpc.TuiProtocolError, tui_rpc.TuiTransportError)
                ):
                    raise

    try:
        policy_limits = ((request.get("effective_policy") or {}).get("limits") or {})
        max_concurrent = int(policy_limits.get("max_concurrent", core.DEFAULT_MAX_CONCURRENT))
        with core.acquire_concurrency_slot(max_concurrent) as slot:
            core.merge_run_status(run_dir, {
                "concurrency_slot": slot.slot,
                "transport": "tui_stdio",
                "phase": "gateway_starting",
                "transport_alive": False,
            })
            env = _environment(request, run_dir)
            readiness_origin = time.monotonic()
            merge_status({"startup_readiness": {"stage": "readiness", "state": "waiting", "elapsed_ms": 0}}, force=True)
            try:
                client = tui_rpc.launch_gateway(
                    python=core.sys.executable,
                    cwd=str(cwd),
                    env=env,
                    command=_gateway_command(request, run_dir),
                )
                core.merge_run_status(run_dir, {
                    "actual_transport": "tui_stdio", "steerability": "unavailable",
                    "transport_pid": client.process.pid, "transport_alive": True,
                })
                gateway_timeout = min(
                    _stage_timeout("PROFILE_DELEGATE_GATEWAY_STARTUP_TIMEOUT_SECONDS", 30.0),
                    max(0.1, deadline - time.monotonic()),
                )
                client.wait_ready(
                    timeout=gateway_timeout,
                    on_event=persist_event,
                )
            except BaseException:
                merge_status({"startup_readiness": {
                    "stage": "readiness", "state": "failed",
                    "elapsed_ms": min(600_000, max(0, int((time.monotonic() - readiness_origin) * 1000))),
                }}, force=True)
                raise
            merge_status({"startup_readiness": {
                "stage": "readiness", "state": "ready",
                "elapsed_ms": min(600_000, max(0, int((time.monotonic() - readiness_origin) * 1000))),
            }}, force=True)
            core.merge_run_status(run_dir, {"phase": "transport_ready", "steerability": "available"})
            core.merge_run_status(run_dir, {"phase": "session_creating"})
            execution = request.get("effective_execution") or {}
            agent_init_deadline = min(
                deadline, time.monotonic() + _stage_timeout("PROFILE_DELEGATE_AGENT_INIT_TIMEOUT_SECONDS", 60.0),
            )
            identities = tui_rpc.start_session(
                client,
                profile=profile,
                mode=mode,
                session_id=resume_id,
                title=title,
                cwd=str(cwd),
                model=core.ensure_text(execution.get("model")),
                provider=core.ensure_text(execution.get("provider")),
                reasoning_effort=core.ensure_text(execution.get("reasoning_effort")),
                timeout=max(0.0, agent_init_deadline - time.monotonic()),
                on_event=persist_event,
            )
            ui_session_id = identities["ui_session_id"]
            resumed_identity = identities["child_session_id"]
            if (resume_id and resumed_identity != resume_id
                    and not core.compression_continuation(Path(request["profile_home"]),
                                                        resume_id, resumed_identity, profile=profile, ui_correlated=True)):
                raise tui_rpc.TuiProtocolError("unproven resumed child identity")
            child_session_id = resumed_identity
            # The reply can be older OR newer than callbacks read while waiting
            # for it. Anchor at the first correlated observation, then replay in
            # wire order; the reply must lie on the same forward-only chain.
            correlated = [f for f in startup_identity_events
                          if f["params"]["session_id"] == ui_session_id
                          and "stored_session_id" in f["params"]["payload"]]
            if correlated:
                initial = correlated[0]["params"]["payload"]["stored_session_id"]
                if not core.valid_session_identity(initial):
                    raise tui_rpc.TuiProtocolError("malformed startup child identity")
                if initial != resumed_identity and not core.compression_continuation(
                    Path(request["profile_home"]), initial, resumed_identity, profile=profile, ui_correlated=True,
                ):
                    # A later callback than the reply is also legitimate.
                    if not core.compression_continuation(
                        Path(request["profile_home"]), resumed_identity, initial, profile=profile, ui_correlated=True,
                    ):
                        raise tui_rpc.TuiProtocolError("unproven startup child identity")
                child_session_id = initial
            for startup_frame in startup_identity_events:
                persist_event(startup_frame)
            startup_identity_events.clear()
            if child_session_id != resumed_identity:
                if core.compression_continuation(Path(request["profile_home"]), child_session_id,
                                                resumed_identity, profile=profile, ui_correlated=True):
                    child_session_id = resumed_identity
                elif not core.compression_continuation(Path(request["profile_home"]), resumed_identity,
                                                      child_session_id, profile=profile, ui_correlated=True):
                    raise tui_rpc.TuiProtocolError("contradictory startup response identity")
            journal.set_session(ui_session_id)
            core.merge_run_status(run_dir, {
                "ui_child_session_id": ui_session_id,
                "child_session_id": child_session_id,
                "phase": "session_ready",
            })
            core.merge_run_status(run_dir, {
                "ui_child_session_id": ui_session_id,
                "child_session_id": child_session_id,
                "phase": "agent_initializing",
            })
            prompt = (run_dir / "prompt.txt").read_text(encoding="utf-8")
            tui_rpc.submit(
                client, ui_session_id, prompt, timeout=max(0.0, agent_init_deadline - time.monotonic()),
                on_event=persist_event,
            )
            core.merge_run_status(run_dir, {"phase": "model_running"})

            while not terminal_event:
                process_controls()
                if cancelled:
                    # Preserve the cleanup reserve: accepted local cancellation
                    # exits event polling immediately and reaps under the same deadline.
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    try:
                        tui_rpc.interrupt(client, ui_session_id, on_event=persist_event)
                    except Exception:
                        pass
                    break
                frame = _poll_event(client, min(0.15, remaining), journal)
                if frame is None:
                    continue
                persist_event(frame)

            if not cancelled:
                process_controls()
                # The host emits message.complete/session.info before it can
                # requeue a leftover steer (prompt_turn.py). A settled observed
                # follow-up needs no additional idle wait. Without a follow-up,
                # observe only within a bounded window to classify uncertainty;
                # silence is never delivery, missed-steer, or terminal proof.
                pending_deadline = min(
                    deadline, time.monotonic() + PENDING_FOLLOWUP_OBSERVATION_SECONDS,
                )
                while accepted_steer and not cancelled and not (followup_completed and turn_settled):
                    process_controls()
                    if cancelled or (followup_completed and turn_settled):
                        break
                    observation_deadline = deadline if followup_started else pending_deadline
                    remaining = observation_deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    frame = _poll_event(client, min(0.15, remaining), journal)
                    if frame is not None:
                        persist_event(frame)
                if accepted_steer and not cancelled and not (followup_completed and turn_settled):
                    if followup_started and time.monotonic() >= deadline:
                        timed_out = True
                    else:
                        # A quiet window cannot prove the host will not requeue
                        # the steer later. Fail closed without consuming the task
                        # deadline solely to resolve delivery uncertainty.
                        error_code, final_status = "steer_outcome_uncertain", "failed"
                # A settled completed turn is an execution receipt, not a
                # correlated steer-delivery receipt; retain delivery unknown.
            if ui_session_id and not cancelled and not accepted_steer:
                try:
                    client.call(
                        "session.close", {"session_id": ui_session_id}, timeout=5,
                        on_event=persist_event,
                    )
                except tui_rpc.TuiProtocolError:
                    raise
                except Exception:
                    pass
        if timed_out:
            error_code, final_status = "timeout", "timed_out"
        elif cancelled or message_status == "interrupted":
            cancelled, final_status, error_code = True, "cancelled", "cancelled"
        elif error_code == "steer_outcome_uncertain":
            pass
        elif message_status == "complete":
            final_status = "completed"
        else:
            error_code, final_status = "tui_turn_error", "failed"
    except Exception as exc:
        if cancelled:
            error_code = "cancelled"
            final_status = "cancelled"
            cancel_transport_diagnostic = cancel_transport_diagnostic or (
                f"{type(exc).__name__}: {exc}"
            )
        else:
            error_code = getattr(exc, "code", "tui_transport_error")
            final_status = "failed"
        core.text_safe_write(
            run_dir / "stderr.txt",
            f"{type(exc).__name__}: {exc}; last observed event={last_observed_event}\n"
            + (f"{cancel_transport_diagnostic}\n" if cancel_transport_diagnostic else "")
            + (client.stderr_tail if client else ""),
        )
    finally:
        if client is not None:
            if cancelled:
                if cancel_deadline is None:
                    cancel_deadline = time.monotonic()
                if cancel_interrupt_accepted:
                    # Observe trailing identity after ACK, never spend the reap
                    # reserve or restart normal controls/turn polling.
                    observation_end = min(cancel_deadline, time.monotonic() + min(
                        0.15, max(0.0, cancel_deadline - time.monotonic()) * 0.1))
                    try:
                        for _ in range(journal.max_pre_session_events):
                            remaining = observation_end - time.monotonic()
                            if remaining <= 0:
                                break
                            frame = _poll_event(client, remaining, journal)
                            if frame is None:
                                break
                            persist_event(frame)
                            params = frame.get("params") or {}
                            if (params.get("session_id") == ui_session_id
                                    and params.get("type") == "session.info"
                                    and "stored_session_id" in (params.get("payload") or {})):
                                cancel_identity_observed = True
                    except Exception as exc:
                        cancel_transport_diagnostic = cancel_transport_diagnostic or f"identity observation unavailable: {exc}"
                client.close(deadline=cancel_deadline)
            else:
                client.close()
            exit_code = client.process.poll()
        core.merge_run_status(run_dir, {"transport_alive": False})

    # The transport process is authoritative. A complete message followed by a
    # nonzero gateway exit is an execution failure, never completed+ok.
    if (
        not timed_out
        and not cancelled
        and exit_code not in (None, 0)
    ):
        final_status = "failed"
        error_code = error_code or "tui_nonzero_exit"

    core.text_safe_write(run_dir / "stdout.txt", final_text)
    if accepted_steer:
        core.merge_run_status(run_dir, {
            "steer_delivery_state": "unknown", "followup_observed": followup_started,
            "followup_settled": followup_completed,
            "steer_response_uncertain": steer_response_uncertain,
        })
    if client and not core.tail_text(run_dir / "stderr.txt", 1):
        core.text_safe_write(run_dir / "stderr.txt", client.stderr_tail)
    if timed_out:
        result = core.failure_result(f"Delegated profile timed out after {timeout} seconds.", "timeout", execution_status="timed_out")
        if final_text.strip():
            result["raw_output_path"] = str(run_dir / "stdout.txt")
            result["errors"].append("last settled turn preserved; follow-up did not settle")
    elif cancelled:
        result = core.failure_result("Delegated profile was cancelled.", "cancelled", execution_status="cancelled")
    elif final_status == "failed" and not final_text.strip():
        result = core.failure_result("Delegated profile transport failed before producing a result.", error_code or "tui_transport_error")
    else:
        result = core.output_result(final_text, str(run_dir / "stdout.txt"), request, final_status,
                                    error_code=(error_code or "tui_turn_error") if final_status != "completed" or message_status == "error" else None)
    if cancelled:
        result["session_identity_evidence"] = "post_interrupt_observed" if cancel_identity_observed else "last_observed_only"
        if cancel_transport_diagnostic:
            result["identity_diagnostic"] = cancel_transport_diagnostic
    terminal_updates = {
        "session_identity_evidence": result.get("session_identity_evidence"),
        "status": final_status,
        "phase": final_status,
        "ended_at": core.now_iso(),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "error_code": error_code,
        "child_session_id": child_session_id,
        "transport_alive": False,
    }
    final = core.finish_run(run_dir, request, result, {**terminal_updates, **journal.snapshot_fields()}, mode="async")
    final_status, error_code, child_session_id = final["status"], final["error_code"], final["child_session_id"]
    try:
        journal.finalize(final_status, error_code=error_code, child_session_id=child_session_id)
        merge_status(journal.snapshot_fields(), force=True)
    except Exception:
        merge_status({"observability_degraded": True}, force=True)
    return final
