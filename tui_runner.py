"""Profile Delegate's single-run TUI worker. Internal; called by core detached worker."""
from __future__ import annotations

import time
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


def _environment(request: Dict[str, Any], run_dir: Path) -> Dict[str, str]:
    mode = core.coerce_child_approval_mode(
        request.get("child_approval_mode", core.DEFAULT_CHILD_APPROVAL_MODE)
    )
    env = core.child_environment(int(request.get("delegate_depth") or 0), mode)
    env["HERMES_HOME"] = core.ensure_text(request.get("profile_home"))
    execution = request.get("effective_execution") or {}
    if execution.get("toolsets"):
        env["HERMES_TUI_TOOLSETS"] = ",".join(execution["toolsets"])
    if execution.get("skills"):
        env["HERMES_TUI_SKILLS"] = ",".join(execution["skills"])
    if execution.get("max_turns"):
        env["HERMES_TUI_MAX_TURNS"] = str(execution["max_turns"])
        env["HERMES_MAX_ITERATIONS"] = str(execution["max_turns"])
    effort = execution.get("reasoning_effort")
    if effort:
        existing = core.discover_managed_scope(env)
        if existing is not None:
            raise core.ProfileDelegateError(
                f"reasoning_effort cannot replace existing Hermes managed scope: {existing}",
                "reasoning_managed_scope_conflict",
            )
        env["HERMES_MANAGED_DIR"] = str(
            core.prepare_reasoning_config(run_dir, core.ensure_text(effort))
        )
    return env


def _gateway_command(request: Dict[str, Any], run_dir: Path) -> list[str]:
    blocked = ((request.get("effective_capabilities") or {}).get("blocked_tools") or [])
    hermes_path = Path(core.ensure_text(request.get("hermes_bin"))).resolve()
    sibling_python = hermes_path.parent / "python"
    runtime_python = Path("/opt/hermes/.venv/bin/python")
    child_python = sibling_python if hermes_path.name == "hermes" and sibling_python.is_file() else runtime_python
    if not child_python.is_file():
        child_python = Path(core.sys.executable)
    return [
        str(child_python),
        str(core.CHILD_BOOTSTRAP),
        "--approval-mode",
        core.coerce_child_approval_mode(request.get("child_approval_mode")),
        "--events-path",
        str(run_dir / "approval_events.jsonl"),
        "--blocked-tools",
        ",".join(core.ensure_text(item) for item in blocked),
        "--tui-gateway",
    ]


def execute(run_dir: Path) -> Dict[str, Any]:
    request = core.read_json_file(run_dir / "request.json")
    timeout = int(request.get("timeout_seconds") or core.DEFAULT_TIMEOUT_SECONDS)
    deadline = time.monotonic() + timeout
    cwd = Path(core.ensure_text(request.get("workdir"))).resolve()
    profile = core.ensure_text(request.get("profile"))
    mode = core.ensure_text(request.get("session_mode") or "new")
    resume_id = core.ensure_text(request.get("requested_session_id") or "")
    title = core.ensure_text(request.get("session_title") or "")
    client: Optional[tui_rpc.TuiRpcClient] = None
    ui_session_id = ""
    child_session_id = resume_id
    final_text = ""
    message_status = ""
    terminal_event = False
    cancelled = False
    cancel_deadline: Optional[float] = None
    timed_out = False
    final_status = "failed"
    error_code: Optional[str] = None
    exit_code: Optional[int] = None
    journal = EventJournal(
        run_dir, task_id=core.ensure_text(request.get("task_id") or run_dir.name),
        persist_message_text=bool(request.get("persist_message_text", False)),
    )
    last_snapshot = 0.0

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
        nonlocal final_text, message_status, terminal_event
        params = frame.get("params") if isinstance(frame.get("params"), dict) else {}
        event_sid = params.get("session_id")
        if event_sid and ui_session_id and event_sid != ui_session_id:
            return
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

    def process_controls() -> None:
        nonlocal cancelled, cancel_deadline
        if client is None or not ui_session_id:
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
                    response = tui_rpc.steer(
                        client, ui_session_id,
                        core.ensure_text((command.get("payload") or {}).get("text")),
                        on_event=persist_event,
                    )
                    state = "accepted" if response.get("status") == "queued" else "rejected"
                    core._ack_control(run_dir, command_path, command, state)
                elif command_type == "cancel":
                    tui_rpc.interrupt(client, ui_session_id, on_event=persist_event)
                    cancelled = True
                    cancel_deadline = time.monotonic() + 5.0
                    core.merge_run_status(run_dir, {"status": "cancelling", "phase": "interrupting"})
                    core._ack_control(run_dir, command_path, command, "accepted")
                else:
                    core._ack_control(
                        run_dir, command_path, command, "rejected", "unsupported command type"
                    )
            except Exception as exc:
                core._ack_control(
                    run_dir, command_path, command, "rejected",
                    f"{type(exc).__name__}: {exc}",
                )

    try:
        policy_limits = ((request.get("effective_policy") or {}).get("limits") or {})
        max_concurrent = int(policy_limits.get("max_concurrent", core.DEFAULT_MAX_CONCURRENT))
        with core.acquire_concurrency_slot(max_concurrent) as slot:
            core.merge_run_status(run_dir, {
                "concurrency_slot": slot.slot,
                "transport": "tui_stdio",
                "phase": "transport_starting",
                "transport_alive": False,
            })
            env = _environment(request, run_dir)
            client = tui_rpc.launch_gateway(
                python=core.sys.executable,
                cwd=str(cwd),
                env=env,
                command=_gateway_command(request, run_dir),
            )
            core.merge_run_status(run_dir, {"transport_pid": client.process.pid, "transport_alive": True})
            client.wait_ready(
                timeout=min(30.0, max(0.1, deadline - time.monotonic())),
                on_event=persist_event,
            )
            execution = request.get("effective_execution") or {}
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
                on_event=persist_event,
            )
            ui_session_id = identities["ui_session_id"]
            child_session_id = identities["child_session_id"]
            journal.set_session(ui_session_id)
            core.merge_run_status(run_dir, {
                "ui_child_session_id": ui_session_id,
                "child_session_id": child_session_id,
                "phase": "session_ready",
            })
            prompt = (run_dir / "prompt.txt").read_text(encoding="utf-8")
            tui_rpc.submit(client, ui_session_id, prompt, on_event=persist_event)
            core.merge_run_status(run_dir, {"phase": "model_running"})

            while not terminal_event:
                process_controls()
                if cancelled and cancel_deadline is not None and time.monotonic() >= cancel_deadline:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    try:
                        tui_rpc.interrupt(client, ui_session_id, on_event=persist_event)
                    except Exception:
                        pass
                    break
                try:
                    frame = client.read_frame(min(0.15, remaining))
                except tui_rpc.TuiTransportError as exc:
                    if "timed out" in str(exc):
                        continue
                    raise
                if frame.get("method") != "event":
                    raise tui_rpc.TuiProtocolError(
                        f"unexpected idle response id {frame.get('id')!r}"
                    )
                persist_event(frame)

            process_controls()
            if ui_session_id:
                try:
                    client.call(
                        "session.close", {"session_id": ui_session_id}, timeout=5,
                        on_event=persist_event,
                    )
                except Exception:
                    pass
        if timed_out:
            error_code, final_status = "timeout", "timed_out"
        elif cancelled or message_status == "interrupted":
            cancelled, final_status, error_code = True, "cancelled", "cancelled"
        elif message_status == "complete":
            final_status = "completed"
        else:
            error_code, final_status = "tui_turn_error", "failed"
    except Exception as exc:
        error_code = getattr(exc, "code", "tui_transport_error")
        final_status = "failed"
        core.text_safe_write(
            run_dir / "stderr.txt",
            f"{type(exc).__name__}: {exc}\n" + (client.stderr_tail if client else ""),
        )
    finally:
        if client is not None:
            client.close()
            exit_code = client.process.poll()
        core.merge_run_status(run_dir, {"transport_alive": False})

    core.text_safe_write(run_dir / "stdout.txt", final_text)
    if client and not core.tail_text(run_dir / "stderr.txt", 1):
        core.text_safe_write(run_dir / "stderr.txt", client.stderr_tail)
    if timed_out:
        result = {
            "status": "failed", "summary": f"Delegated profile timed out after {timeout} seconds.",
            "artifacts": [], "errors": ["timeout"], "next_steps": [], "structured": True,
            "error_code": "timeout",
        }
    elif cancelled:
        result = {
            "status": "failed", "summary": "Delegated profile was cancelled.",
            "artifacts": [], "errors": ["cancelled"], "next_steps": [], "structured": True,
            "error_code": "cancelled",
        }
    else:
        result = core.normalize_result(
            core.extract_json_object(final_text), str(run_dir / "stdout.txt"), raw_output=final_text
        )
        if final_status != "completed" or message_status == "error":
            result["status"] = "failed"
            result["error_code"] = error_code or "tui_turn_error"
            result["errors"] = core.coerce_list(result.get("errors")) + [result["error_code"]]
    if child_session_id:
        result["session_id"] = child_session_id
    result.update(
        {
            "requested_execution": request.get("requested_execution") or {},
            "effective_execution": request.get("effective_execution") or {},
            "effective_capabilities": request.get("effective_capabilities") or {},
            "approval_policy": request.get("approval_policy") or {},
            "recovery_history": [],
        }
    )
    core.json_safe_write(run_dir / "result.json", result)
    terminal_updates = {
        "status": final_status,
        "phase": final_status,
        "ended_at": core.now_iso(),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "error_code": error_code,
        "child_session_id": child_session_id,
        "transport_alive": False,
    }
    merge_status({**terminal_updates, **journal.snapshot_fields()}, force=True, terminal=True)
    try:
        journal.finalize(final_status, error_code=error_code, child_session_id=child_session_id)
        merge_status(journal.snapshot_fields(), force=True)
    except Exception:
        merge_status({"observability_degraded": True}, force=True)
    return {
        "success": final_status == "completed" and result.get("status") != "failed",
        "mode": "async",
        "task_id": request.get("task_id", run_dir.name),
        "profile": profile,
        "status": final_status,
        "error_code": error_code,
        "session_title": title,
        "session_mode": mode,
        "requested_session_id": resume_id,
        "child_session_id": child_session_id,
        "result": result,
        "paths": core.base_paths(run_dir),
        "exit_code": exit_code,
        "timed_out": timed_out,
    }
