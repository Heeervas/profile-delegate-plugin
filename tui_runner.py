"""Profile Delegate's single-run TUI worker. Internal; called by core detached worker."""
from __future__ import annotations

import time
import threading
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


class _RunCoordinator:
    """Single run state owner; core.finish_run remains terminal authority."""

    def __init__(self, run_dir: Path) -> None:
        self._cleanup_lock = threading.Lock()
        self.run_dir = run_dir
        self.request = core.read_json_file(self.run_dir / "request.json")
        self.timeout = int(self.request.get("timeout_seconds") or core.DEFAULT_TIMEOUT_SECONDS)
        # Includes actual gateway startup; never grant startup an unmeasured bonus.
        self.deadline = time.monotonic() + self.timeout
        self.cwd = Path(core.ensure_text(self.request.get("workdir"))).resolve()
        self.profile = core.ensure_text(self.request.get("profile"))
        self.mode = core.ensure_text(self.request.get("session_mode") or "new")
        self.resume_id = core.ensure_text(self.request.get("requested_session_id") or "")
        self.title = core.ensure_text(self.request.get("session_title") or "")
        self.client: Optional[tui_rpc.TuiRpcClient] = None
        self.ui_session_id = ""
        self.child_session_id = ""
        self.final_text = ""
        self.message_status = ""
        self.terminal_event = False
        self.turn_settled = False
        self.followup_started = False
        self.followup_completed = False
        self.accepted_steer = False
        self.steer_response_uncertain = False
        self.steer_baseline = None
        self.steer_texts: list[str] = []
        self.checked_steers = 0
        self.steer_delivery_proven = False
        self.cancelled = False
        self.cancel_deadline: Optional[float] = None
        self.cancel_transport_diagnostic = ""
        self.cancel_interrupt_accepted = False
        self.cancel_identity_observed = False
        self.timed_out = False
        self.final_status = "failed"
        self.error_code: Optional[str] = None
        self.exit_code: Optional[int] = None
        self.journal = EventJournal(
            self.run_dir, task_id=core.ensure_text(self.request.get("task_id") or self.run_dir.name),
            persist_message_text=bool(self.request.get("persist_message_text", False)),
        )
        self.last_snapshot = 0.0
        self.last_observed_event = "none"
        self.startup_identity_events: list[Dict[str, Any]] = []

    def merge_status(self, updates: Dict[str, Any], *, force: bool = False, terminal: bool = False) -> None:

        now = time.monotonic()
        if not force and now - self.last_snapshot < 0.5:
            return
        if terminal:
            core.merge_run_status(self.run_dir, updates, terminal=True)
            self.last_snapshot = now
        elif core.merge_run_status_best_effort(self.run_dir, updates):
            self.last_snapshot = now

    def retain_startup_identity(self, frame, params, event_sid):
        # Retain only the identity portion before response correlation, with
        # the journal's existing startup-event budget, not a new depth cap.
        if params.get("type") == "session.info":
            if len(self.startup_identity_events) >= self.journal.max_pre_session_events:
                raise tui_rpc.TuiProtocolError("startup identity evidence overflow")
            payload = params.get("payload")
            if isinstance(payload, dict):
                self.startup_identity_events.append({"method": "event", "params": {
                    "type": "session.info", "session_id": event_sid,
                    "payload": {k: payload[k] for k in ("stored_session_id", "profile_name") if k in payload},
                }})
        self.journal.ingest(frame)

    def observe_identity(self, params):
        if params.get("type") == "session.info":
            payload = params.get("payload")
            if isinstance(payload, dict) and "stored_session_id" in payload:
                if "profile_name" in payload and payload["profile_name"] != self.profile:
                    raise tui_rpc.TuiProtocolError("contradictory child profile identity")
                proposed = payload["stored_session_id"]
                if not core.valid_session_identity(proposed):
                    raise tui_rpc.TuiProtocolError("malformed stored child session identity")
                if proposed != self.child_session_id:
                    if not core.compression_continuation(
                        Path(self.request["profile_home"]), self.child_session_id, proposed,
                        profile=self.profile, ui_correlated=True,
                    ):
                        raise tui_rpc.TuiProtocolError("unproven child compression identity")
                    self.child_session_id = proposed
                    core.merge_run_status(self.run_dir, {"child_session_id": proposed})

    def persist_event(self, frame: Dict[str, Any]) -> None:


        raw_params = frame.get("params")
        params: Dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}
        if frame.get("method") != "event":
            return
        self.last_observed_event = core.ensure_text(params.get("type") or "unknown")
        event_sid = params.get("session_id")
        if not self.ui_session_id:
            self.retain_startup_identity(frame, params, event_sid)
            return
        if event_sid != self.ui_session_id:
            return
        self.observe_identity(params)
        try:
            self.journal.ingest(frame)
            self.merge_status(self.journal.snapshot_fields())
        except Exception:
            self.merge_status({"observability_degraded": True}, force=True)
        self.observe_message(params)

    def observe_message(self, params):
        if params.get("type") == "message.complete":
            payload = params.get("payload") if isinstance(params.get("payload"), dict) else {}
            self.final_text = core.ensure_text(payload.get("text"))
            self.message_status = core.ensure_text(payload.get("status") or "complete")
            self.terminal_event = True
            self.turn_settled = False
            if self.followup_started:
                self.followup_completed = True
        elif params.get("type") == "message.start":
            if self.accepted_steer and self.terminal_event:
                self.followup_started = True
            self.terminal_event = False
            self.turn_settled = False
        elif params.get("type") == "session.info" and self.terminal_event:
            self.turn_settled = True

    def process_controls(self) -> None:


        if self.client is None or not self.ui_session_id or self.cancelled:
            return
        for command_path, command in core._pending_control_commands(self.run_dir):
            command_type = core.ensure_text(command.get("type"))
            try:
                if command.get("claimed_at"):
                    core._ack_control(
                        self.run_dir, command_path, command, "delivery_unknown",
                        "worker restarted after delivery claim",
                    )
                    continue
                command["claimed_at"] = core.now_iso()
                core.json_safe_write(command_path, command)
                if command_type == "steer":
                    self.apply_steer(command_path, command)
                    if self.timed_out:
                        return
                elif command_type == "cancel":
                    self.apply_cancel(command_path, command)
                    return
                else:
                    core._ack_control(
                        self.run_dir, command_path, command, "rejected", "unsupported command type"
                    )
            except Exception as exc:
                core._ack_control(
                    self.run_dir, command_path, command, "rejected",
                    f"{type(exc).__name__}: {exc}",
                )
                if command_type != "cancel" and isinstance(
                    exc, (tui_rpc.TuiProtocolError, tui_rpc.TuiTransportError)
                ):
                    raise

    def apply_steer(self, command_path, command):
        if self.terminal_event and self.turn_settled:
            core._ack_control(self.run_dir, command_path, command, "rejected", "turn already settled")
            return
        text = core.ensure_text((command.get("payload") or {}).get("text")).strip()
        if not self.steer_texts:
            self.steer_baseline = core.native.steer_snapshot(
                Path(self.request["profile_home"]), self.child_session_id,
                deadline=self.deadline, include_inactive=True,
            )
        if time.monotonic() >= self.deadline:
            self.timed_out = True
            core._ack_control(self.run_dir, command_path, command, "rejected", "task deadline exhausted")
            return
        self.deliver_steer(command_path, command, text)

    def deliver_steer(self, command_path, command, text):
        try:
            response = tui_rpc.steer(
                self.client, self.ui_session_id, text,
                on_event=self.persist_event,
            )
        except tui_rpc.TuiRemoteError as exc:
            if exc.code != 4010:
                raise
            core._ack_control(
                self.run_dir, command_path, command, "rejected",
                f"native steer unavailable: {exc.message}",
            )
        except tui_rpc.TuiTransportError as exc:
            if not _is_local_timeout(exc):
                raise
            # A local RPC timeout does not prove the native steer
            # was rejected; it may have queued a later follow-up.
            self.accepted_steer = True
            self.steer_texts.append(text)
            self.steer_delivery_proven = False
            self.steer_response_uncertain = True
            core._ack_control(
                self.run_dir, command_path, command, "delivery_unknown", str(exc)
            )
        else:
            state = "accepted" if response.get("status") == "queued" else "rejected"
            self.accepted_steer = self.accepted_steer or state == "accepted"
            if state == "accepted":
                self.steer_texts.append(text)
                self.steer_delivery_proven = False
            core._ack_control(self.run_dir, command_path, command, state)

    def apply_cancel(self, command_path, command):
        # Local cancellation is terminal authority. Establish its
        # short deadline before attempting the best-effort native
        # interrupt so an unready agent cannot consume the run timeout.
        self.cancelled = True
        self.cancel_deadline = time.monotonic() + CANCEL_GRACE_SECONDS
        core.merge_run_status(
            self.run_dir, {"status": "cancelling", "phase": "interrupting"}
        )
        detail = "native interrupt accepted"
        try:
            interrupt_budget = max(
                0.001, (self.cancel_deadline - time.monotonic()) * 0.5,
            )
            tui_rpc.interrupt(
                self.client, self.ui_session_id,
                timeout=interrupt_budget,
                on_event=self.persist_event,
            )
            self.cancel_interrupt_accepted = True
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
                self.cancel_transport_diagnostic = detail
        except tui_rpc.TuiProtocolError as exc:
            detail = (
                "native interrupt protocol failure; local cancellation authoritative: "
                f"{exc}"
            )
            self.cancel_transport_diagnostic = detail
        core._ack_control(self.run_dir, command_path, command, "accepted", detail)
        # Cancellation owns the remaining lifecycle. Do not drain
        # later controls under its absolute cleanup deadline.
        return

    def start_gateway(self, slot):
        core.merge_run_status(self.run_dir, {
            "concurrency_slot": slot.slot,
            "transport": "tui_stdio",
            "phase": "gateway_starting",
            "transport_alive": False,
        })
        env = _environment(self.request, self.run_dir)
        readiness_origin = time.monotonic()
        self.merge_status({"startup_readiness": {"stage": "readiness", "state": "waiting", "elapsed_ms": 0}}, force=True)
        try:
            self.client = tui_rpc.launch_gateway(
                python=core.sys.executable,
                cwd=str(self.cwd),
                env=env,
                command=_gateway_command(self.request, self.run_dir),
            )
            core.merge_run_status(self.run_dir, {
                "actual_transport": "tui_stdio", "steerability": "unavailable",
                "transport_pid": self.client.process.pid, "transport_alive": True,
            })
            gateway_timeout = min(
                _stage_timeout("PROFILE_DELEGATE_GATEWAY_STARTUP_TIMEOUT_SECONDS", 30.0),
                max(0.1, self.deadline - time.monotonic()),
            )
            self.client.wait_ready(
                timeout=gateway_timeout,
                on_event=self.persist_event,
            )
        except BaseException:
            self.merge_status({"startup_readiness": {
                "stage": "readiness", "state": "failed",
                "elapsed_ms": min(600_000, max(0, int((time.monotonic() - readiness_origin) * 1000))),
            }}, force=True)
            raise
        self.merge_status({"startup_readiness": {
            "stage": "readiness", "state": "ready",
            "elapsed_ms": min(600_000, max(0, int((time.monotonic() - readiness_origin) * 1000))),
        }}, force=True)
        core.merge_run_status(self.run_dir, {"phase": "transport_ready", "steerability": "available"})

    def start_agent(self):
        core.worktrees.before_continue(self.request, self.resume_id)
        core.merge_run_status(self.run_dir, {"phase": "session_creating"})
        execution = self.request.get("effective_execution") or {}
        agent_init_deadline = min(
            self.deadline, time.monotonic() + _stage_timeout("PROFILE_DELEGATE_AGENT_INIT_TIMEOUT_SECONDS", 60.0),
        )
        identities = tui_rpc.start_session(
            self.client,
            profile=self.profile,
            mode=self.mode,
            session_id=self.resume_id,
            title=self.title,
            cwd=str(self.cwd),
            model=core.ensure_text(execution.get("model")),
            provider=core.ensure_text(execution.get("provider")),
            reasoning_effort=core.ensure_text(execution.get("reasoning_effort")),
            timeout=max(0.0, agent_init_deadline - time.monotonic()),
            on_event=self.persist_event,
        )
        self.bind_startup_identity(identities)
        self.journal.set_session(self.ui_session_id)
        core.merge_run_status(self.run_dir, {
            "ui_child_session_id": self.ui_session_id,
            "child_session_id": self.child_session_id,
            "phase": "session_ready",
        })
        core.merge_run_status(self.run_dir, {
            "ui_child_session_id": self.ui_session_id,
            "child_session_id": self.child_session_id,
            "phase": "agent_initializing",
        })
        prompt = (self.run_dir / "prompt.txt").read_text(encoding="utf-8")
        tui_rpc.submit(
            self.client, self.ui_session_id, prompt, timeout=max(0.0, agent_init_deadline - time.monotonic()),
            on_event=self.persist_event,
        )
        core.merge_run_status(self.run_dir, {"phase": "model_running"})

    def bind_startup_identity(self, identities):
        self.ui_session_id = identities["ui_session_id"]
        resumed_identity = identities["child_session_id"]
        if (self.resume_id and resumed_identity != self.resume_id
                and not core.compression_continuation(Path(self.request["profile_home"]),
                                                    self.resume_id, resumed_identity, profile=self.profile, ui_correlated=True)):
            raise tui_rpc.TuiProtocolError("unproven resumed child identity")
        self.child_session_id = resumed_identity
        # The reply can be older OR newer than callbacks read while waiting
        # for it. Anchor at the first correlated observation, then replay in
        # wire order; the reply must lie on the same forward-only chain.
        correlated = [f for f in self.startup_identity_events
                      if f["params"]["session_id"] == self.ui_session_id
                      and "stored_session_id" in f["params"]["payload"]]
        if correlated:
            initial = correlated[0]["params"]["payload"]["stored_session_id"]
            if not core.valid_session_identity(initial):
                raise tui_rpc.TuiProtocolError("malformed startup child identity")
            if initial != resumed_identity and not core.compression_continuation(
                Path(self.request["profile_home"]), initial, resumed_identity, profile=self.profile, ui_correlated=True,
            ):
                # A later callback than the reply is also legitimate.
                if not core.compression_continuation(
                    Path(self.request["profile_home"]), resumed_identity, initial, profile=self.profile, ui_correlated=True,
                ):
                    raise tui_rpc.TuiProtocolError("unproven startup child identity")
            self.child_session_id = initial
        for startup_frame in self.startup_identity_events:
            self.persist_event(startup_frame)
        self.startup_identity_events.clear()
        if self.child_session_id != resumed_identity:
            if core.compression_continuation(Path(self.request["profile_home"]), self.child_session_id,
                                            resumed_identity, profile=self.profile, ui_correlated=True):
                self.child_session_id = resumed_identity
            elif not core.compression_continuation(Path(self.request["profile_home"]), resumed_identity,
                                                  self.child_session_id, profile=self.profile, ui_correlated=True):
                raise tui_rpc.TuiProtocolError("contradictory startup response identity")

    def observe_turn(self):
        while not self.terminal_event:
            self.process_controls()
            if self.cancelled:
                # Preserve the cleanup reserve: accepted local cancellation
                # exits event polling immediately and reaps under the same deadline.
                break
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                self.timed_out = True
                try:
                    tui_rpc.interrupt(self.client, self.ui_session_id, on_event=self.persist_event)
                except Exception:
                    pass
                break
            frame = _poll_event(self.client, min(0.15, remaining), self.journal)
            if frame is None:
                continue
            self.persist_event(frame)

    def followup_resolved(self):
        return self.cancelled or self.steer_delivery_proven or (self.followup_completed and self.turn_settled)

    def verify_steer_delivery(self):
        if self.steer_baseline is not None and self.terminal_event and self.turn_settled and self.checked_steers < len(self.steer_texts):
            self.checked_steers = len(self.steer_texts)
            self.steer_delivery_proven = core.native.steers_consumed(
                self.steer_baseline,
                core.native.steer_snapshot(Path(self.request["profile_home"]), self.child_session_id, deadline=self.deadline),
                self.steer_texts,
            )
            if time.monotonic() >= self.deadline:
                self.timed_out = True
                self.steer_delivery_proven = False
                return

    def observe_followup(self):
        if not self.cancelled:
            self.process_controls()
            # The host emits message.complete/session.info before it can
            # requeue a leftover steer (prompt_turn.py). A settled observed
            # follow-up needs no additional idle wait. Without a follow-up,
            # observe only within a bounded window to classify uncertainty;
            # silence is never delivery, missed-steer, or terminal proof.
            pending_deadline = min(
                self.deadline, time.monotonic() + PENDING_FOLLOWUP_OBSERVATION_SECONDS,
            )
            while self.accepted_steer and not self.followup_resolved():
                self.process_controls()
                if self.cancelled:
                    break
                self.verify_steer_delivery()
                if self.timed_out or self.followup_resolved():
                    break
                observation_deadline = self.deadline if self.followup_started else pending_deadline
                remaining = observation_deadline - time.monotonic()
                if remaining <= 0:
                    break
                frame = _poll_event(self.client, min(0.15, remaining), self.journal)
                if frame is not None:
                    self.persist_event(frame)
            if self.accepted_steer and not self.followup_resolved():
                if self.followup_started and time.monotonic() >= self.deadline:
                    self.timed_out = True
                else:
                    # A quiet window cannot prove the host will not requeue
                    # the steer later. Fail closed without consuming the task
                    # deadline solely to resolve delivery uncertainty.
                    self.error_code, self.final_status = "steer_outcome_uncertain", "failed"
            # Only fresh typed native occurrences prove same-turn steering;
            # a settled follow-up alone leaves delivery unknown.

    def close_session(self):
        if self.ui_session_id and not self.cancelled and not self.accepted_steer:
            try:
                self.client.call(
                    "session.close", {"session_id": self.ui_session_id}, timeout=5,
                    on_event=self.persist_event,
                )
            except tui_rpc.TuiProtocolError:
                raise
            except Exception:
                pass

    def classify(self):
        if self.timed_out:
            self.error_code, self.final_status = "timeout", "timed_out"
        elif self.cancelled or self.message_status == "interrupted":
            self.cancelled, self.final_status, self.error_code = True, "cancelled", "cancelled"
        elif self.error_code == "steer_outcome_uncertain":
            pass
        elif self.message_status == "complete":
            self.final_status = "completed"
        else:
            self.error_code, self.final_status = "tui_turn_error", "failed"

    def record_error(self, exc):
        if self.cancelled:
            self.error_code = "cancelled"
            self.final_status = "cancelled"
            self.cancel_transport_diagnostic = self.cancel_transport_diagnostic or (
                f"{type(exc).__name__}: {exc}"
            )
        else:
            self.error_code = getattr(exc, "code", "tui_transport_error")
            self.final_status = "failed"
        core.text_safe_write(
            self.run_dir / "stderr.txt",
            f"{type(exc).__name__}: {exc}; last observed event={self.last_observed_event}\n"
            + (f"{self.cancel_transport_diagnostic}\n" if self.cancel_transport_diagnostic else "")
            + (self.client.stderr_tail if self.client else ""),
        )

    def observe_cancel_identity(self):
        # Observe trailing identity after ACK, never spend the reap
        # reserve or restart normal controls/turn polling.
        observation_end = min(self.cancel_deadline, time.monotonic() + min(
            0.15, max(0.0, self.cancel_deadline - time.monotonic()) * 0.1))
        try:
            for _ in range(self.journal.max_pre_session_events):
                remaining = observation_end - time.monotonic()
                if remaining <= 0:
                    break
                frame = _poll_event(self.client, remaining, self.journal)
                if frame is None:
                    break
                self.persist_event(frame)
                params = frame.get("params") or {}
                if (params.get("session_id") == self.ui_session_id
                        and params.get("type") == "session.info"
                        and "stored_session_id" in (params.get("payload") or {})):
                    self.cancel_identity_observed = True
        except Exception as exc:
            self.cancel_transport_diagnostic = self.cancel_transport_diagnostic or f"identity observation unavailable: {exc}"

    def teardown(self):
        if self.client is not None:
            if self.cancelled:
                if self.cancel_deadline is None:
                    self.cancel_deadline = time.monotonic()
                if self.cancel_interrupt_accepted:
                    self.observe_cancel_identity()
                self.client.close(deadline=self.cancel_deadline)
            else:
                self.client.close()
            self.exit_code = self.client.process.poll()
            if self.exit_code is None:
                # close() is bounded, not a promise that the OS reaped the child.
                # Preserve the unresolved lifecycle as a failure for publication;
                # execution_slot transfers the still-held permit to its reaper.
                self.final_status, self.error_code = "failed", "tui_reap_pending"
        pending = self.client is not None and self.exit_code is None
        core.merge_run_status(self.run_dir, {"transport_alive": pending})

    def build_result(self):
        if self.timed_out:
            result = core.failure_result(f"Delegated profile timed out after {self.timeout} seconds.", "timeout", execution_status="timed_out")
            if self.final_text.strip():
                result["raw_output_path"] = str(self.run_dir / "stdout.txt")
                result["errors"].append("last settled turn preserved; follow-up did not settle")
        elif self.cancelled:
            result = core.failure_result("Delegated profile was cancelled.", "cancelled", execution_status="cancelled")
        elif self.final_status == "failed" and not self.final_text.strip():
            result = core.failure_result("Delegated profile transport failed before producing a result.", self.error_code or "tui_transport_error")
        else:
            result = core.output_result(self.final_text, str(self.run_dir / "stdout.txt"), self.request, self.final_status,
                                        error_code=(self.error_code or "tui_turn_error") if self.final_status != "completed" or self.message_status == "error" else None)
        if self.cancelled:
            result["session_identity_evidence"] = "post_interrupt_observed" if self.cancel_identity_observed else "last_observed_only"
            if self.cancel_transport_diagnostic:
                result["identity_diagnostic"] = self.cancel_transport_diagnostic
        return result

    def publish(self):
        with self._cleanup_lock:
            return self._publish()

    def _publish(self):
        # The transport process is authoritative. A complete message followed by a
        # nonzero gateway exit is an execution failure, never completed+ok.
        if (
            not self.timed_out
            and not self.cancelled
            and self.exit_code != 0
        ):
            self.final_status = "failed"
            self.error_code = self.error_code or "tui_nonzero_exit"

        core.text_safe_write(self.run_dir / "stdout.txt", self.final_text)
        if self.accepted_steer:
            core.merge_run_status(self.run_dir, {
                "steer_delivery_state": "delivered" if self.steer_delivery_proven else "unknown",
                "followup_observed": self.followup_started,
                "followup_settled": self.followup_completed,
                "steer_response_uncertain": self.steer_response_uncertain,
            })
        if self.client and not core.tail_text(self.run_dir / "stderr.txt", 1):
            core.text_safe_write(self.run_dir / "stderr.txt", self.client.stderr_tail)
        result = self.build_result()
        terminal_updates = {
            "session_identity_evidence": result.get("session_identity_evidence"),
            "status": self.final_status,
            "phase": self.final_status,
            "ended_at": core.now_iso(),
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "error_code": self.error_code,
            "child_session_id": self.child_session_id,
            "transport_alive": self.client is not None and self.client.process.poll() is None,
        }
        final = core.finish_run(self.run_dir, self.request, result, {**terminal_updates, **self.journal.snapshot_fields()}, mode="async")
        self.final_status, self.error_code, self.child_session_id = final["status"], final["error_code"], final["child_session_id"]
        try:
            self.journal.finalize(self.final_status, error_code=self.error_code, child_session_id=self.child_session_id)
            self.merge_status(self.journal.snapshot_fields(), force=True)
        except Exception:
            self.merge_status({"observability_degraded": True}, force=True)
        return final

    def execution_slot(self, maximum):
        """Transfer the permit to a reaper if bounded teardown cannot reap."""
        from contextlib import contextmanager

        @contextmanager
        def owned_slot():
            slot_manager = core.acquire_concurrency_slot(maximum)
            slot = slot_manager.__enter__()
            try:
                yield slot
            finally:
                process = self.client.process if self.client is not None else None
                if process is None or process.poll() is not None:
                    slot_manager.__exit__(None, None, None)
                else:
                    # Keep the acquired permit itself alive; do not move a
                    # generator context-manager's __exit__ across threads.
                    def reap():
                        # A failed wait is not evidence of death: retain ownership.
                        process.wait()
                        with self._cleanup_lock:
                            try:
                                core.merge_run_status(self.run_dir, {"transport_alive": False})
                            finally:
                                slot_manager.__exit__(None, None, None)

                    reaper = threading.Thread(
                        target=reap, name="profile-delegate-reaper", daemon=False,
                    )
                    try:
                        reaper.start()
                    except RuntimeError:
                        # Thread creation failure cannot justify releasing the
                        # permit while the child is live. Reap here, then release.
                        reap()
        return owned_slot()

    def run(self) -> Dict[str, Any]:
        try:
            limits = ((self.request.get("effective_policy") or {}).get("limits") or {})
            maximum = int(limits.get("max_concurrent", core.DEFAULT_MAX_CONCURRENT))
            with self.execution_slot(maximum) as slot:
                try:
                    self.start_gateway(slot)
                    self.start_agent()
                    self.observe_turn()
                    self.observe_followup()
                    self.close_session()
                    self.classify()
                finally:
                    # The permit accounts for the live child, not just its turn.
                    # Publish/notification happens only after reaping and release.
                    self.teardown()
        except Exception as exc:
            self.record_error(exc)
        return self.publish()


def execute(run_dir: Path) -> Dict[str, Any]:
    return _RunCoordinator(run_dir).run()
