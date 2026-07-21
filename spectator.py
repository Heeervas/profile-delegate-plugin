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
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, TextIO

TASK_ID_RE = re.compile(r"pd_\d{8}_\d{6}_[a-z0-9]{6,12}\Z")
TERMINAL = {"completed", "failed", "cancelled", "timed_out"}
FAILED = {"failed", "cancelled", "timed_out"}
READABLE_ARTIFACTS = {"status.json", "events.jsonl", "result.json", "request.json"}
MAX_JSON_BYTES = 262_144
MAX_INSPECT_EVENTS = 100
MAX_TEXT_CHARS = 8_192

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


def iter_events(path: Path, *, after_seq: int = 0) -> Iterator[Dict[str, Any]]:
    """Yield complete sanitized JSONL records newer than ``after_seq``."""
    try:
        with path.open("rb") as handle:
            raw = handle.read(1_048_577)
    except OSError as exc:
        raise SpectatorError(f"cannot read events.jsonl: {exc}", 4) from None
    if len(raw) > 1_048_576:
        raise SpectatorError("events.jsonl exceeds spectator bound", 4)
    complete = raw if raw.endswith(b"\n") else raw.rsplit(b"\n", 1)[0] + (b"\n" if b"\n" in raw else b"")
    for line in complete.splitlines():
        if not line:
            continue
        try:
            item = json.loads(line.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise SpectatorError(f"corrupt complete events.jsonl record: {exc}", 4) from None
        if not isinstance(item, dict) or not isinstance(item.get("seq"), int):
            raise SpectatorError("corrupt events.jsonl record shape", 4)
        if item["seq"] > after_seq:
            yield neutralize_terminal(item)


def inspect_run(run_dir: Path) -> Dict[str, Any]:
    """Return one bounded, machine-readable snapshot from allowed artifacts."""
    status_path = _artifact(run_dir, "status.json", required=True)
    assert status_path is not None
    status = _read_json(status_path)
    events_path = _artifact(run_dir, "events.jsonl")
    result_path = _artifact(run_dir, "result.json")
    events = list(iter_events(events_path))[-MAX_INSPECT_EVENTS:] if events_path else []
    result = _read_json(result_path) if result_path else None
    allowed_status = {
        "task_id", "status", "phase", "created_at", "started_at", "ended_at",
        "delegated_profile", "profile", "model", "provider", "turn_count", "api_calls",
        "tool_calls", "usage", "event_seq", "event_schema_version", "event_stream_truncated",
        "observability_degraded", "error_code", "child_session_id", "worker_pid",
    }
    snapshot: Dict[str, Any] = {key: status[key] for key in allowed_status if key in status}
    snapshot["task_id"] = str(snapshot.get("task_id") or run_dir.name)
    snapshot["limited_observability"] = events_path is None
    if events_path is None:
        snapshot["observation_note"] = "limited observability: legacy run has no events.jsonl"
    snapshot["events"] = events
    if result is not None:
        snapshot["result"] = {
            key: result[key] for key in ("status", "summary", "error_code", "artifacts", "errors", "next_steps")
            if key in result
        }
    return neutralize_terminal(snapshot)


def _status(run_dir: Path) -> Dict[str, Any]:
    path = _artifact(run_dir, "status.json", required=True)
    assert path is not None
    return _read_json(path)


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
    limited = events_path is None
    last_seq = 0
    last_status = ""
    stale_since: Optional[float] = None
    old_termios = None
    fd: Optional[int] = None
    old_winch = None
    redraw = True

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
                for event in iter_events(events_path, after_seq=last_seq):
                    last_seq = max(last_seq, int(event["seq"]))
                    if mode == "jsonl":
                        print(json.dumps(event, ensure_ascii=False, separators=(",", ":")), file=out, flush=True)
                    elif mode == "plain":
                        print(_event_line(event), file=out, flush=True)
                    redraw = True
            status = _status(run_dir)
            status_name = str(status.get("status") or "unknown").lower()
            status_text = _status_line(status, limited=limited)
            if mode == "tty" and redraw:
                print("\x1b[2J\x1b[HProfile Delegate spectator (read-only; q/Ctrl+C detaches)\n" + status_text, file=out, flush=True)
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
