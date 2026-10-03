"""Shared child launch selection; CLI/TUI execute in the chosen profile runtime."""
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
if __package__:
    from . import native_approval
    from .contracts import ProfileDelegateError, ensure_text
else:
    import native_approval
    from contracts import ProfileDelegateError, ensure_text

CHILD_BOOTSTRAP = Path(__file__).resolve().parent / "child_bootstrap.py"


def bootstrap_command(request: Dict[str, Any], run_dir: Path) -> List[str]:
    """Shared interpreter/authority prefix for CLI and native TUI gateway."""
    try:
        native_approval.validate_request(request)
        approval_mode = native_approval.selector(request.get("child_approval_mode") or "deny")
    except ValueError as exc:
        raise ProfileDelegateError(str(exc), "approval_policy_error") from exc
    hermes_path = Path(ensure_text(request.get("hermes_bin"))).resolve()
    sibling_python = hermes_path.parent / "python"
    runtime_python = Path("/opt/hermes/.venv/bin/python")
    child_python = sibling_python if hermes_path.name == "hermes" and sibling_python.is_file() else runtime_python
    if not child_python.is_file():
        child_python = Path(sys.executable)
    blocked = (request.get("effective_capabilities") or {}).get("blocked_tools") or []
    return [str(child_python), str(CHILD_BOOTSTRAP), "--approval-mode", approval_mode,
            "--request-path", str(run_dir / "request.json"),
            "--events-path", str(run_dir / "approval_events.jsonl"),
            "--blocked-tools", ",".join(ensure_text(item) for item in blocked)]


def _hermes_command(request, run_dir, prompt_path, resume_session_id):
    requested = request.get("effective_execution") or request.get("requested_execution") or {}
    hermes_cmd = [ensure_text(request.get("hermes_bin")), "-p", ensure_text(request.get("profile")),
                  "chat", "-q", f"@file:{prompt_path or (run_dir / 'prompt.txt')}", "-Q"]
    approval_mode = ensure_text(request.get("child_approval_mode")) or "deny"
    if approval_mode in {"approve_yolo", "yolo"}:
        hermes_cmd.append("--yolo")
    for name in ("model", "provider", "max_turns", "toolsets", "skills"):
        value = requested.get(name)
        if value is None or (name != "max_turns" and not value):
            continue
        rendered = ",".join(value) if name in {"toolsets", "skills"} else ensure_text(value)
        hermes_cmd.extend(["--" + name.replace("_", "-"), rendered])
    effective_resume_id = resume_session_id
    if effective_resume_id is None and ensure_text(request.get("session_mode") or "new") == "resume":
        effective_resume_id = ensure_text(request.get("requested_session_id"))
    if effective_resume_id:
        hermes_cmd += ["--resume", effective_resume_id]
    hermes_cmd += ["--pass-session-id", "--source", "profile-delegate"]

    return hermes_cmd, approval_mode


def build_child_command(
    request: Dict[str, Any], run_dir: Path, *,
    prompt_path: Optional[Path] = None,
    resume_session_id: Optional[str] = None,
) -> List[str]:
    prefix = bootstrap_command(request, run_dir)
    hermes_cmd, _ = _hermes_command(request, run_dir, prompt_path, resume_session_id)
    return [*prefix, *(["--test-shim"] if request.get("test_shim") is True else []), "--", *hermes_cmd]
