"""Child launch argv adapter; approval binding remains in bootstrap."""
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
import core
import native_approval
from core import ensure_text, CHILD_BOOTSTRAP

def _hermes_command(request, run_dir, prompt_path, resume_session_id):
    requested = request.get("effective_execution") or request.get("requested_execution") or {}
    hermes_cmd = [ensure_text(request.get("hermes_bin")), "-p", ensure_text(request.get("profile")),
                  "chat", "-q", f"@file:{prompt_path or (run_dir / 'prompt.txt')}", "-Q"]
    native_approval.validate_request(request)
    approval_mode = ensure_text(request.get("child_approval_mode")) or "deny"
    if approval_mode in {"approve_yolo", "yolo"}:
        hermes_cmd.append("--yolo")
    if requested.get("model"):
        hermes_cmd += ["--model", ensure_text(requested["model"])]
    if requested.get("provider"):
        hermes_cmd += ["--provider", ensure_text(requested["provider"])]
    if requested.get("max_turns") is not None:
        hermes_cmd += ["--max-turns", str(requested["max_turns"])]
    if requested.get("toolsets"):
        hermes_cmd += ["--toolsets", ",".join(requested["toolsets"])]
    if requested.get("skills"):
        hermes_cmd += ["--skills", ",".join(requested["skills"])]
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
    try:
        hermes_cmd, approval_mode = _hermes_command(request, run_dir, prompt_path, resume_session_id)
    except ValueError as exc:
        raise core.ProfileDelegateError(str(exc), "approval_policy_error") from exc
    capabilities = request.get("effective_capabilities") or {}
    blocked_tools = capabilities.get("blocked_tools") or []
    hermes_path = Path(ensure_text(request.get("hermes_bin"))).resolve()
    sibling_python = hermes_path.parent / "python"
    # Only trust a sibling interpreter for the real Hermes launcher. Test
    # doubles and system utilities such as /bin/echo may sit beside a Python
    # installation that lacks Hermes dependencies.
    if hermes_path.name == "hermes" and sibling_python.is_file():
        child_python = str(sibling_python)
    else:
        runtime_python = Path("/opt/hermes/.venv/bin/python")
        child_python = str(runtime_python if runtime_python.is_file() else Path(sys.executable))
    return [
        child_python, str(CHILD_BOOTSTRAP),
        "--approval-mode", approval_mode,
        "--request-path", str(run_dir / "request.json"),
        *(["--test-shim"] if request.get("test_shim") is True else []),
        "--events-path", str(run_dir / "approval_events.jsonl"),
        "--blocked-tools", ",".join(ensure_text(item) for item in blocked_tools),
        "--", *hermes_cmd,
    ]
