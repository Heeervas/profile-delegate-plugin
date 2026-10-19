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


def bind_cli_workspace(request):
    """Bind native terminal policy in the child, preserving all but local cwd."""
    if not request.get('workspace'):
        return
    from tools.terminal_scope import build_profile_terminal_scope, set_terminal_scope
    scope = build_profile_terminal_scope(request['profile_home'])
    if scope.get('TERMINAL_ENV', 'local') != 'local':
        raise ProfileDelegateError('Managed Git checkout requires local terminal backend; prepare a remote workspace manually', 'workspace_error')
    scope['TERMINAL_CWD'] = request['workdir']
    set_terminal_scope(scope)


def cli_workspace_args(request):
    """Select native launch cwd and cwd-persisting source only for managed runs."""
    if request.get('workspace'):
        return ['--in', ensure_text(request['workdir']), '--source', 'cli']
    return ['--source', 'profile-delegate']


def select_transport(request, detached):
    """Persist selection intent once; the worker publishes actual transport later."""
    pending = request['background'] and detached
    request.update(selected_transport=None if pending else 'simple',
                   transport_selection_state='selection_pending' if pending else 'selected',
                   transport='tui_stdio' if pending and request['requested_transport'] != 'simple' else 'cli')


def observe_attempt(request, stable_id, stdout, stderr, meta, integrity_error):
    """Validate one process observation; never manufacture a recoverable identity."""
    if __package__:
        from . import core
    else:
        import core
    out_id, err_id = core.extract_session_id_footer(stdout), core.extract_session_id_footer(stderr)
    footer = out_id or err_id
    observed = ""
    if out_id is None or err_id is None:
        integrity_error = "resume_session_mismatch"
    elif footer:
        if (not core.valid_session_identity(footer)
                or (out_id and err_id and out_id != err_id)
                or (stable_id and footer != stable_id and not core.compression_continuation(
                    Path(request['profile_home']), stable_id, footer, profile=request['profile'], cli_footer=True))):
            integrity_error = "resume_session_mismatch"
        else:
            stable_id = observed = footer
    transient = None if integrity_error else core.classify_transient_failure(
        exit_code=meta['exit_code'], timed_out=bool(meta['timed_out']),
        stdout=meta.get('stdout_diagnostic_tail', stdout), stderr=meta.get('stderr_diagnostic_tail', stderr),
        parsed_result=core.extract_json_object(core.strip_session_id_footer(stdout)),
        stdout_truncated=bool(meta.get('stdout_truncated')), stderr_truncated=bool(meta.get('stderr_truncated')),
        interrupted=meta.get('stop_reason') in {'cancelled', 'interrupted'}, native_stdout=stdout, native_stderr=stderr)
    return stable_id, observed, integrity_error, transient


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


def build_child_command(
    request: Dict[str, Any], run_dir: Path, *,
    prompt_path: Optional[Path] = None,
    resume_session_id: Optional[str] = None,
) -> List[str]:
    prefix = bootstrap_command(request, run_dir)
    requested = request.get("effective_execution") or request.get("requested_execution") or {}
    hermes_cmd = [ensure_text(request.get("hermes_bin")), "-p", ensure_text(request.get("profile")),
                  "chat", "--query-file", str(prompt_path or (run_dir / "prompt.txt")), "-Q"]
    approval_mode = ensure_text(request.get("child_approval_mode")) or "deny"
    if approval_mode in {"approve_yolo", "yolo"}:
        hermes_cmd.append("--yolo")
    for name in ("model", "provider", "reasoning_effort", "max_turns", "toolsets", "skills"):
        value = requested.get(name)
        if value is None or (name != "max_turns" and not value):
            continue
        rendered = ",".join(value) if name in {"toolsets", "skills"} else ensure_text(value)
        hermes_cmd.extend(["--" + {"reasoning_effort": "reasoning"}.get(name, name.replace("_", "-")), rendered])
    effective_resume_id = resume_session_id
    if effective_resume_id is None and ensure_text(request.get("session_mode") or "new") == "resume":
        effective_resume_id = ensure_text(request.get("requested_session_id"))
    if effective_resume_id:
        hermes_cmd += ["--resume", effective_resume_id]
    # Native CLI records cwd only for CLI-family sources. Pin managed checkouts
    # through its public --in seam; subprocess cwd alone loses to profile config.
    hermes_cmd += ["--pass-session-id", *cli_workspace_args(request)]

    return [*prefix, *(["--test-shim"] if request.get("test_shim") is True else []), "--", *hermes_cmd]
