"""Strictly read-only rendering of sanitized Profile Delegate run artifacts."""
from __future__ import annotations

import json
import os
import re
import select
import signal
import stat
import sys
import termios
import time
import tty
from collections import deque
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, TextIO

try:
    from .event_schema import (
        EVENT_IDENTIFIER_MAX_CHARS, EVENT_JOURNAL_MAX_BYTES, EVENT_MESSAGE_MAX_CHARS,
        EVENT_METADATA_MAX_CHARS, EVENT_SCHEMA_VERSION, EVENT_TIMESTAMP_MAX_CHARS,
    )
except ImportError:
    from event_schema import (  # type: ignore[no-redef]
        EVENT_IDENTIFIER_MAX_CHARS, EVENT_JOURNAL_MAX_BYTES, EVENT_MESSAGE_MAX_CHARS,
        EVENT_METADATA_MAX_CHARS, EVENT_SCHEMA_VERSION, EVENT_TIMESTAMP_MAX_CHARS,
    )

TASK_ID_RE = re.compile(r"pd_\d{8}_\d{6}_[a-z0-9]{6,12}\Z")
TERMINAL = {"completed", "failed", "cancelled", "timed_out"}
FAILED = {"failed", "cancelled", "timed_out"}
READABLE_ARTIFACTS = {"status.json", "events.jsonl", "result.json", "request.json"}
MAX_JSON_BYTES = 262_144
MAX_INSPECT_EVENTS = 100
MAX_TEXT_CHARS = EVENT_MESSAGE_MAX_CHARS
TTY_EVENT_RING = 20
VALID_STATUSES = {"running", "cancelling"} | TERMINAL
VALID_PHASES = {
    "starting", "transport_starting", "gateway_starting", "transport_ready", "session_creating",
    "session_ready", "agent_initializing", "model_running",
    "tool_running", "message_complete", "interrupting", "completed", "failed", "cancelled",
    "timed_out", "running",
}
COMMON_EVENT_KEYS = {
    "schema_version", "task_id", "seq", "at", "type", "phase", "payload", "redacted",
    "dropped_fields",
}
EVENT_PAYLOAD_KEYS = {
    "lifecycle": ({"status", "phase"}, {"status", "phase"}),
    "message.start": ({"message_id", "role"}, {"role"}),
    "message.delta": ({"message_id", "text"}, {"text"}),
    "message.complete": ({"message_id", "status", "text", "usage"}, {"status"}),
    "tool.start": ({"tool_id", "tool", "tool_class"}, {"tool_id", "tool", "tool_class"}),
    "tool.complete": (
        {"tool_id", "tool", "tool_class", "duration_s", "outcome"},
        {"tool_id", "tool", "tool_class", "duration_s", "outcome"},
    ),
    "session.info": ({"profile", "model", "provider", "usage"}, set()),
    "status.update": ({"kind"}, {"kind"}),
    "journal.truncated": ({"reason", "dropped_after_seq"}, {"reason", "dropped_after_seq"}),
    "terminal": ({"status", "error_code", "child_session_id"}, {"status"}),
    "event.dropped": ({"reason"}, {"reason"}),
}
SAFE_DROPPED_FIELDS = {
    "args", "arguments", "result", "summary", "diff", "text", "reasoning", "rendered",
    "warning",
}
TOOL_CLASSES = {"file", "web", "shell", "browser", "delegate", "other"}
MESSAGE_STATUSES = {"complete", "error", "interrupted", "cancelled"}
STATUS_KINDS = {
    "compacting", "retrying", "waiting", "streaming", "queued", "running", "idle",
    "rate_limited", "context_compacted",
}

# ESC/CSI/OSC plus C0/C1 controls. Newline and tab are retained for readable text.
_OSC_RE = re.compile(r"\x1b\][^\x07]*(?:\x07|\x1b\\)?")
_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_ESC_RE = re.compile(r"\x1b(?:[@-_]|\[[^@-~]*[@-~])")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


class SpectatorError(Exception):
    """A user-facing spectator failure carrying its documented exit code."""

    def __init__(self, message: str, exit_code: int = 4):
        super().__init__(message)
        self.exit_code = exit_code


def neutralize_terminal(value: Any) -> Any:
    """Repeat journal terminal-control neutralization before rendering."""
    if isinstance(value, str):
        value = value.encode("utf-8", "replace").decode("utf-8", "replace")
        value = _OSC_RE.sub("", value)
        value = _CSI_RE.sub("", value)
        value = _ESC_RE.sub("", value)
        return _CONTROL_RE.sub("", value)[:MAX_TEXT_CHARS]
    if isinstance(value, list):
        return [neutralize_terminal(item) for item in value[:100]]
    if isinstance(value, dict):
        return {
            neutralize_terminal(str(key))[:128]: neutralize_terminal(item)
            for key, item in list(value.items())[:100]
        }
    return value


def _effective_runs_root(*, runs_root: str = "", hermes_home: str = "") -> Path:
    if runs_root.strip():
        return Path(runs_root).expanduser()
    override = os.getenv("PROFILE_DELEGATE_RUNS_ROOT", "").strip()
    if override:
        return Path(override).expanduser()
    home = hermes_home.strip() or os.getenv("HERMES_HOME", "").strip()
    if not home:
        home = str(Path.home() / ".hermes")
    return Path(home).expanduser() / "profile_delegate" / "runs"


def resolve_spectator_run(task_id: str, *, runs_root: str = "", hermes_home: str = "") -> Path:
    """Resolve exactly one run using core-compatible precedence; never scan homes."""
    clean = str(task_id or "").strip()
    if not TASK_ID_RE.fullmatch(clean):
        raise SpectatorError("invalid task_id format (expected pd_YYYYMMDD_HHMMSS_suffix)", 2)
    root = _effective_runs_root(runs_root=runs_root, hermes_home=hermes_home)
    candidate = root / clean
    try:
        if root.is_symlink() or candidate.is_symlink():
            raise SpectatorError("unsafe run path: symlinks are not allowed", 3)
        root_resolved = root.resolve(strict=True)
        run_resolved = candidate.resolve(strict=True)
    except SpectatorError:
        raise
    except FileNotFoundError:
        raise SpectatorError(f"run not found: {clean} under {root}", 2) from None
    try:
        run_resolved.relative_to(root_resolved)
    except ValueError:
        raise SpectatorError("unsafe run path: resolved outside runs root", 3) from None
    try:
        info = run_resolved.stat()
    except OSError as exc:
        raise SpectatorError(f"cannot inspect run: {exc}", 3) from None
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise SpectatorError("unsafe run path: directory must belong to the current user", 3)
    return run_resolved


def _artifact(run_dir: Path, name: str, *, required: bool = False) -> Optional[Path]:
    if name not in READABLE_ARTIFACTS:
        raise SpectatorError("internal spectator artifact policy violation", 4)
    path = run_dir / name
    if path.is_symlink():
        raise SpectatorError(f"unsafe artifact: {name} is a symlink", 3)
    try:
        info = path.stat()
    except FileNotFoundError:
        if required:
            raise SpectatorError(f"required artifact missing: {name}", 4) from None
        return None
    except OSError as exc:
        raise SpectatorError(f"cannot inspect {name}: {exc}", 4) from None
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise SpectatorError(f"unsafe artifact: {name}", 3)
    return path


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise SpectatorError(f"artifact too large: {path.name}", 4)
        value = json.loads(raw.decode("utf-8"))
    except SpectatorError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SpectatorError(f"corrupt {path.name}: {exc}", 4) from None
    if not isinstance(value, dict):
        raise SpectatorError(f"corrupt {path.name}: expected JSON object", 4)
    return neutralize_terminal(value)


def _valid_usage(value: Any) -> bool:
    return isinstance(value, dict) and set(value) <= {"input", "output", "reasoning", "total", "calls"} and all(
        isinstance(item, int) and not isinstance(item, bool) and item >= 0
        for item in value.values()
    )


def _validate_event(
    item: Any, *, allow_message_text: bool, expected_task_id: str = "",
) -> Dict[str, Any]:
    if not isinstance(item, dict) or set(item) != COMMON_EVENT_KEYS:
        raise SpectatorError("corrupt events.jsonl record schema", 4)
    if item.get("schema_version") != EVENT_SCHEMA_VERSION or not isinstance(item.get("seq"), int) or item["seq"] < 1:
        raise SpectatorError("corrupt events.jsonl common fields", 4)
    if (
        not isinstance(item.get("task_id"), str)
        or len(item["task_id"]) > EVENT_IDENTIFIER_MAX_CHARS
        or (expected_task_id and item["task_id"] != expected_task_id)
    ):
        raise SpectatorError("corrupt events.jsonl task identity", 4)
    if not isinstance(item.get("at"), str) or len(item["at"]) > EVENT_TIMESTAMP_MAX_CHARS:
        raise SpectatorError("corrupt events.jsonl timestamp", 4)
    if item.get("phase") not in VALID_PHASES or not isinstance(item.get("redacted"), bool):
        raise SpectatorError("corrupt events.jsonl phase/redaction metadata", 4)
    dropped = item.get("dropped_fields")
    if not isinstance(dropped, list) or len(dropped) > 20 or any(
        value not in SAFE_DROPPED_FIELDS for value in dropped
    ):
        raise SpectatorError("corrupt events.jsonl dropped-fields metadata", 4)
    kind = item.get("type")
    if kind not in EVENT_PAYLOAD_KEYS:
        raise SpectatorError("corrupt events.jsonl event type", 4)
    payload = item.get("payload")
    allowed, required = EVENT_PAYLOAD_KEYS[kind]
    if not isinstance(payload, dict) or not required <= set(payload) <= allowed:
        raise SpectatorError("corrupt events.jsonl event payload schema", 4)
    for key, value in payload.items():
        if key == "usage":
            if not _valid_usage(value):
                raise SpectatorError("corrupt events.jsonl usage", 4)
        elif key == "duration_s":
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 86_400:
                raise SpectatorError("corrupt events.jsonl duration", 4)
        elif key == "dropped_after_seq":
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise SpectatorError("corrupt events.jsonl truncation sequence", 4)
        elif not isinstance(value, str) or len(value) > (
            EVENT_MESSAGE_MAX_CHARS if key == "text" else EVENT_METADATA_MAX_CHARS
        ):
            raise SpectatorError("corrupt events.jsonl bounded string", 4)
    if "role" in payload and payload["role"] != "assistant":
        raise SpectatorError("corrupt events.jsonl message role", 4)
    if "text" in payload and not allow_message_text:
        raise SpectatorError("message text present without frozen opt-in", 4)
    if kind in {"tool.start", "tool.complete"} and payload["tool_class"] not in TOOL_CLASSES:
        raise SpectatorError("corrupt events.jsonl tool class", 4)
    if kind == "tool.complete" and payload["outcome"] not in {"complete", "unknown"}:
        raise SpectatorError("corrupt events.jsonl tool outcome", 4)
    if kind == "message.complete" and payload["status"] not in MESSAGE_STATUSES:
        raise SpectatorError("corrupt events.jsonl message status", 4)
    if kind == "status.update" and payload["kind"] not in STATUS_KINDS:
        raise SpectatorError("corrupt events.jsonl status kind", 4)
    if kind in {"lifecycle", "terminal"} and payload["status"] not in VALID_STATUSES:
        raise SpectatorError("corrupt events.jsonl lifecycle status", 4)
    return neutralize_terminal(item)


def iter_events(
    path: Path, *, after_seq: int = 0, allow_message_text: bool = False,
    expected_task_id: str = "",
) -> Iterator[Dict[str, Any]]:
    """Yield complete, exactly validated JSONL records newer than ``after_seq``."""
    try:
        with path.open("rb") as handle:
            raw = handle.read(EVENT_JOURNAL_MAX_BYTES + 1)
    except OSError as exc:
        raise SpectatorError(f"cannot read events.jsonl: {exc}", 4) from None
    if len(raw) > EVENT_JOURNAL_MAX_BYTES:
        raise SpectatorError("events.jsonl exceeds spectator bound", 4)
    complete = raw if raw.endswith(b"\n") else raw.rsplit(b"\n", 1)[0] + (b"\n" if b"\n" in raw else b"")
    for line in complete.splitlines():
        if not line:
            continue
        try:
            item = json.loads(line.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise SpectatorError(f"corrupt complete events.jsonl record: {exc}", 4) from None
        validated = _validate_event(
            item, allow_message_text=allow_message_text, expected_task_id=expected_task_id,
        )
        if validated["seq"] > after_seq:
            yield validated


def _bounded_string(value: Any, limit: int, *, nullable: bool = False) -> bool:
    return (nullable and value is None) or (isinstance(value, str) and len(value) <= limit)


def _bounded_counter(value: Any, *, nullable: bool = False) -> bool:
    return (nullable and value is None) or (
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
    )


def _validate_status(status: Dict[str, Any], *, expected_task_id: str = "") -> Dict[str, Any]:
    status_name = status.get("status")
    if not isinstance(status_name, str) or status_name not in VALID_STATUSES:
        raise SpectatorError("corrupt status.json: missing or unknown status", 4)
    phase = status.get("phase")
    if phase is not None and (not isinstance(phase, str) or phase not in VALID_PHASES):
        raise SpectatorError("corrupt status.json: unknown phase", 4)
    task_id = status.get("task_id")
    if not _bounded_string(task_id, EVENT_IDENTIFIER_MAX_CHARS) or (
        expected_task_id and task_id != expected_task_id
    ):
        raise SpectatorError("corrupt status.json: task identity mismatch", 4)
    string_fields = {
        "created_at": EVENT_TIMESTAMP_MAX_CHARS, "started_at": EVENT_TIMESTAMP_MAX_CHARS,
        "ended_at": EVENT_TIMESTAMP_MAX_CHARS, "delegated_profile": EVENT_METADATA_MAX_CHARS,
        "profile": EVENT_METADATA_MAX_CHARS, "model": EVENT_METADATA_MAX_CHARS,
        "provider": EVENT_METADATA_MAX_CHARS, "error_code": EVENT_IDENTIFIER_MAX_CHARS,
        "child_session_id": EVENT_IDENTIFIER_MAX_CHARS,
    }
    nullable_strings = {"ended_at", "error_code", "child_session_id"}
    for key, limit in string_fields.items():
        if key in status and not _bounded_string(
            status[key], limit, nullable=key in nullable_strings,
        ):
            raise SpectatorError(f"corrupt status.json: invalid {key}", 4)
    for key in ("turn_count", "api_calls", "tool_calls", "event_seq", "event_schema_version", "worker_pid"):
        if key in status and not _bounded_counter(
            status[key], nullable=key in {"api_calls", "worker_pid"},
        ):
            raise SpectatorError(f"corrupt status.json: invalid {key}", 4)
    for key in ("event_stream_truncated", "observability_degraded"):
        if key in status and not isinstance(status[key], bool):
            raise SpectatorError(f"corrupt status.json: invalid {key}", 4)
    if "usage" in status and not _valid_usage(status["usage"]):
        raise SpectatorError("corrupt status.json: invalid usage", 4)
    return status


def _validate_result(
    result: Dict[str, Any], *, expected_task_id: str = "", legacy: bool = False,
) -> Dict[str, Any]:
    current_schema = result.get("result_schema_version")
    if current_schema is not None and current_schema != 1:
        raise SpectatorError("corrupt result.json: unknown schema version", 4)
    if not legacy and current_schema != 1:
        raise SpectatorError("corrupt result.json: missing schema version", 4)
    if (not legacy or current_schema is not None) and (
        not _bounded_string(result.get("task_id"), EVENT_IDENTIFIER_MAX_CHARS)
        or result.get("task_id") != expected_task_id
    ):
        raise SpectatorError("corrupt result.json: task identity mismatch", 4)
    if (
        not _bounded_string(result.get("status"), 32)
        or result.get("status") not in {"ok", "blocked", "failed", "completed", "cancelled", "timed_out"}
    ):
        raise SpectatorError("corrupt result.json: invalid status", 4)
    for key in ("error_code", "session_id"):
        if key in result and not _bounded_string(
            result[key], EVENT_IDENTIFIER_MAX_CHARS, nullable=key == "error_code",
        ):
            raise SpectatorError(f"corrupt result.json: invalid {key}", 4)
    if "summary" in result and not _bounded_string(result["summary"], EVENT_MESSAGE_MAX_CHARS):
        raise SpectatorError("corrupt result.json: invalid summary", 4)
    for key in ("artifacts", "errors", "next_steps"):
        if key in result:
            value = result[key]
            if not isinstance(value, list) or len(value) > 100 or any(
                not _bounded_string(item, EVENT_MESSAGE_MAX_CHARS) for item in value
            ):
                raise SpectatorError(f"corrupt result.json: invalid {key}", 4)
    return result


def _message_text_opt_in(run_dir: Path) -> bool:
    request_path = _artifact(run_dir, "request.json")
    if request_path is None:
        return False
    request = _read_json(request_path)
    value = request.get("persist_message_text", False)
    if not isinstance(value, bool):
        raise SpectatorError("corrupt request.json: persist_message_text must be boolean", 4)
    return value


def inspect_run(run_dir: Path) -> Dict[str, Any]:
    """Return one bounded, machine-readable snapshot from allowed artifacts."""
    status_path = _artifact(run_dir, "status.json", required=True)
    assert status_path is not None
    status = _validate_status(_read_json(status_path), expected_task_id=run_dir.name)
    allow_message_text = _message_text_opt_in(run_dir)
    events_path = _artifact(run_dir, "events.jsonl")
    result_path = _artifact(run_dir, "result.json")
    events = list(iter_events(
        events_path, allow_message_text=allow_message_text, expected_task_id=run_dir.name,
    ))[-MAX_INSPECT_EVENTS:] if events_path else []
    result = _validate_result(
        _read_json(result_path), expected_task_id=run_dir.name, legacy=events_path is None,
    ) if result_path else None
    allowed_status = {
        "task_id", "status", "phase", "created_at", "started_at", "ended_at",
        "delegated_profile", "profile", "model", "provider", "turn_count", "api_calls",
        "tool_calls", "usage", "event_seq", "event_schema_version", "event_stream_truncated",
        "observability_degraded", "error_code", "child_session_id", "worker_pid",
    }
    snapshot: Dict[str, Any] = {key: status[key] for key in allowed_status if key in status}
    snapshot["task_id"] = status["task_id"]
    snapshot["limited_observability"] = events_path is None
    if events_path is None:
        snapshot["observation_note"] = "limited observability: legacy run has no events.jsonl"
    snapshot["events"] = events
    if result is not None:
        result_keys = ["status", "error_code", "session_id"]
        if allow_message_text:
            result_keys.extend(["summary", "artifacts", "errors", "next_steps"])
        snapshot["result"] = {key: result[key] for key in result_keys if key in result}
    return neutralize_terminal(snapshot)


def _status(run_dir: Path) -> Dict[str, Any]:
    path = _artifact(run_dir, "status.json", required=True)
    assert path is not None
    return _validate_status(_read_json(path), expected_task_id=run_dir.name)


def _pid_alive(pid: Any) -> bool:
    try:
        value = int(pid)
        if value <= 0:
            return False
        os.kill(value, 0)  # existence check only; never sends a signal
        return True
    except PermissionError:
        return True
    except (ValueError, TypeError, ProcessLookupError):
        return False


def _event_line(event: Dict[str, Any]) -> str:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    detail = payload.get("tool") or payload.get("status") or payload.get("kind") or payload.get("text") or ""
    return neutralize_terminal(f"[{event.get('seq', '?')}] {event.get('type', 'event')} {detail}".rstrip())


def _status_line(status: Dict[str, Any], *, limited: bool = False) -> str:
    parts = [f"status={status.get('status', 'unknown')}", f"phase={status.get('phase', 'unknown')}"]
    profile = status.get("delegated_profile") or status.get("profile")
    if profile:
        parts.append(f"profile={profile}")
    if limited:
        parts.append("limited observability")
    return neutralize_terminal(" | ".join(parts))


def _terminal_code(status: str) -> int:
    return 1 if status in FAILED else 0


def _tty_screen(status: Dict[str, Any], events: Any, *, limited: bool) -> str:
    lines = [
        "Profile Delegate spectator (read-only; q/Ctrl+C detaches)",
        _status_line(status, limited=limited),
    ]
    counters = " | ".join(
        f"{key}={status[key]}" for key in ("turn_count", "api_calls", "tool_calls")
        if status.get(key) is not None
    )
    if counters:
        lines.append(counters)
    lines.append("Recent events (bounded):")
    lines.extend(_event_line(event) for event in events)
    return "\x1b[2J\x1b[H" + "\n".join(lines)


def watch_run(
    run_dir: Path, *, output_mode: str = "auto", poll_interval: float = 0.2,
    stdout: Optional[TextIO] = None,
) -> int:
    """Follow sanitized artifacts without opening transport, control, or writable files."""
    out = stdout or sys.stdout
    interval = min(5.0, max(0.05, float(poll_interval)))
    tty_mode = output_mode == "tty" or (output_mode == "auto" and bool(getattr(out, "isatty", lambda: False)()))
    mode = "tty" if tty_mode else ("jsonl" if output_mode == "jsonl" else "plain")
    events_path = _artifact(run_dir, "events.jsonl")
    allow_message_text = _message_text_opt_in(run_dir)
    limited = events_path is None
    last_seq = 0
    last_status = ""
    stale_since: Optional[float] = None
    old_termios = None
    fd: Optional[int] = None
    old_winch = None
    redraw = True
    event_ring = deque(maxlen=TTY_EVENT_RING)

    def on_winch(_signum, _frame):
        nonlocal redraw
        redraw = True

    try:
        if tty_mode and out is sys.stdout and sys.stdin.isatty():
            fd = sys.stdin.fileno()
            old_termios = termios.tcgetattr(fd)
            tty.setcbreak(fd)
            old_winch = signal.getsignal(signal.SIGWINCH)
            signal.signal(signal.SIGWINCH, on_winch)
        while True:
            if not run_dir.exists():
                raise SpectatorError("run disappeared while being observed", 4)
            if events_path is None:
                events_path = _artifact(run_dir, "events.jsonl")
                limited = events_path is None
            if events_path is not None:
                for event in iter_events(
                    events_path, after_seq=last_seq, allow_message_text=allow_message_text,
                    expected_task_id=run_dir.name,
                ):
                    last_seq = max(last_seq, int(event["seq"]))
                    event_ring.append(event)
                    if mode == "jsonl":
                        print(json.dumps(event, ensure_ascii=False, separators=(",", ":")), file=out, flush=True)
                    elif mode == "plain":
                        print(_event_line(event), file=out, flush=True)
                    redraw = True
            status = _status(run_dir)
            status_name = str(status.get("status") or "unknown").lower()
            status_text = _status_line(status, limited=limited)
            if status_text != last_status:
                redraw = True
            if mode == "tty" and redraw:
                print(_tty_screen(status, event_ring, limited=limited), file=out, flush=True)
                redraw = False
            elif mode == "plain" and status_text != last_status:
                print(status_text, file=out, flush=True)
            last_status = status_text
            if status_name in TERMINAL:
                return _terminal_code(status_name)
            if status_name in {"running", "cancelling"} and status.get("worker_pid") and not _pid_alive(status.get("worker_pid")):
                if stale_since is None:
                    stale_since = time.monotonic()
                    if mode != "jsonl":
                        print("stale/degraded: worker PID is not alive; confirming for 2 seconds", file=out, flush=True)
                elif time.monotonic() - stale_since >= 2.0:
                    return 4
            else:
                stale_since = None
            if fd is not None:
                readable, _, _ = select.select([fd], [], [], interval)
                if readable and os.read(fd, 1).lower() == b"q":
                    return 0
            else:
                time.sleep(interval)
    except KeyboardInterrupt:
        return 0
    except BrokenPipeError:
        return 0
    finally:
        if old_termios is not None and fd is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_termios)
        if old_winch is not None:
            signal.signal(signal.SIGWINCH, old_winch)
