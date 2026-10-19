"""Opt-in Git workspace preparation. Never removes a checkout or changes source files."""
from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess
from contextlib import closing


def _core():
    if __package__:
        from . import core
    else:
        import core
    return core


def git(root, *args, allowed_codes=(0,)):
    core = _core()
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    try:
        result = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", "-C", str(root), *args],
            env=env, capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise core.ProfileDelegateError(f"Git workspace unavailable: {exc}", "workspace_error") from exc
    if result.returncode not in allowed_codes:
        raise core.ProfileDelegateError(result.stderr.strip()[:1000] or "Git workspace command failed", "workspace_error")
    return result.stdout.strip()


def reject_external_filters(source):
    """Checkout drivers execute parent-side programs, not merely Git operations."""
    configured = git(source, "config", "--get-regexp", r"^filter\..*\.(smudge|process)$", allowed_codes=(0, 1))
    if configured:
        raise _core().ProfileDelegateError(
            "Repository config contains external checkout filters; prepare and authorize a worktree manually, then pass workdir without worktree=true",
            "workspace_external_filter")


def options(worktree, base_ref, branch, mode, workdir, preset):
    core = _core()
    if type(worktree) is not bool:
        raise core.ProfileDelegateError("worktree must be a boolean", "validation_error")
    if not worktree:
        if base_ref is not None or branch is not None:
            raise core.ProfileDelegateError("base_ref/branch require worktree=true", "validation_error")
        return None
    if mode != "new" or not isinstance(workdir, str) or not workdir.strip() or preset != "build":
        raise core.ProfileDelegateError("worktree requires new session, explicit repository root and build preset", "validation_error")
    validate_option("base_ref", base_ref)
    validate_option("branch", branch)
    return {"base_ref": "HEAD" if base_ref is None else base_ref, "branch": branch}


def validate_option(name, value):
    if value is None:
        return
    if not isinstance(value, str) or not value or value.startswith("-") or "\0" in value or value != value.strip():
        raise _core().ProfileDelegateError(f"invalid {name}", "validation_error")


def destination(source, task_id):
    return Path(source).parent / ".profile-delegate-worktrees" / Path(source).name / task_id


def resolve_workspace(request, target, workdir, requested, policy, records):
    core = _core()
    retained = resume(target, request['requested_session_id'], request['origin'], workdir, policy, records) if request['session_mode'] == 'resume' else None
    cwd = core.resolve_workdir(retained['workdir'] if retained else workdir, policy)
    workspace = inspect(cwd, requested, policy) if requested else (retained['workspace'] if retained else None)
    return cwd, workspace


def inspect(source, requested, policy):
    core = _core()
    if git(source, "rev-parse", "--is-bare-repository") != "false" or Path(git(source, "rev-parse", "--show-toplevel")).resolve() != source:
        raise core.ProfileDelegateError("workdir must be the exact non-bare checkout root", "workspace_error")
    reject_external_filters(source)
    sha = git(source, "rev-parse", "--verify", "--end-of-options", requested["base_ref"] + "^{commit}")
    if requested["branch"] is not None:
        if git(source, "check-ref-format", "--branch", requested["branch"]) != requested["branch"]:
            raise core.ProfileDelegateError("branch must be literal, not a previous-checkout expression", "validation_error")
    # Validate every directory we may create, including existing symlink parents.
    target = destination(source, "TASK_ID")
    for path in (target.parent.parent, target.parent, target):
        core.enforce_workdir_policy(path.resolve(), True, policy)
    return {"source_root": str(source), "requested_ref": requested["base_ref"], "initial_sha": sha,
            "initial_branch": requested["branch"], "destination_pattern": str(target), "preparation_state": "planned",
            "dirty_warning": "Only committed base files are materialized; staged, unstaged, untracked and ignored files are excluded."}


def create(workspace, task_id, policy):
    """Called only after authorized matching and persisted intention. Retain on failure."""
    core = _core()
    source = Path(workspace["source_root"])
    target = destination(source, task_id)
    reject_external_filters(source)
    branch = workspace["initial_branch"] or f"pd/{task_id}"
    workspace.update(destination=str(target), initial_branch=branch, preparation_state="unknown")
    for path in (target.parent.parent, target.parent, target):
        core.enforce_workdir_policy(path.resolve(), True, policy)
    if target.exists() or target.is_symlink():
        raise core.ProfileDelegateError("workspace destination already exists; prepare manually", "workspace_error")
    sha = workspace["initial_sha"]
    if target.resolve() != target:
        raise core.ProfileDelegateError("workspace destination traverses a symlink; prepare manually", "workspace_error")
    command = ["git", "-c", "core.hooksPath=/dev/null", "-C", str(source), "worktree", "add", "-b", branch, str(target), sha]
    from tools.approval import check_all_command_guards
    decision = check_all_command_guards(shlex.join(command), "local")
    if not decision.get("approved"):
        raise core.ProfileDelegateError(decision.get("message") or "Parent Git preparation not authorized; prepare worktree manually", "workspace_approval_required")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        git(source, "worktree", "add", "-b", branch, str(target), sha)
    finally:
        observe_creation(workspace)
    if workspace["preparation_state"] != "created":
        raise core.ProfileDelegateError("Created workspace base/branch mismatch", "workspace_error")
    return target.resolve()


def observe_creation(workspace):
    """An exit code alone cannot establish whether Git left usable resources."""
    try:
        verify(workspace)
        target = Path(workspace["destination"])
        if git(target, "rev-parse", "HEAD") == workspace["initial_sha"] and git(target, "symbolic-ref", "--short", "HEAD") == workspace["initial_branch"]:
            workspace["preparation_state"] = "created"
    except _core().ProfileDelegateError:
        pass


def prepare(request, run_dir, policy):
    """Persist intent before Git; publish observed workspace even on later failure."""
    core = _core()
    workspace = request["workspace"]
    workspace.update(destination=str(destination(Path(request["workdir"]), request["task_id"])),
                     initial_branch=workspace["initial_branch"] or f'pd/{request["task_id"]}')
    workspace.pop("destination_pattern", None)
    core.json_safe_write(run_dir / "request.json", request)
    try:
        request["workdir"] = str(create(workspace, request["task_id"], policy))
        core.json_safe_write(run_dir / "request.json", request)
        core.json_safe_write(run_dir / "status.json", {**request, "status": "running"})
    except Exception as exc:
        if workspace["preparation_state"] == "created":
            request["workdir"] = workspace["destination"]
        details = dict(workspace=workspace, task_id=request["task_id"], paths=core.base_paths(run_dir))
        try:
            core.json_safe_write(run_dir / "request.json", request)
            core.json_safe_write(run_dir / "status.json", {**request, "status": "failed"})
        except Exception as persist_error:
            details["publication_error"] = str(persist_error)
        # Let the existing terminal failure publisher retain the handle.
        raise core.ProfileDelegateError(str(exc), getattr(exc, "code", "workspace_error"), **details) from exc


def verify(workspace):
    core = _core()
    target = Path(workspace["destination"])
    source = Path(workspace["source_root"])
    if not target.is_dir() or target.resolve() != target or Path(git(target, "rev-parse", "--show-toplevel")).resolve() != target:
        raise core.ProfileDelegateError("Workspace missing or replaced; recover manually", "workspace_continuity_error")
    if common_directory(source) != common_directory(target):
        raise core.ProfileDelegateError("Workspace repository association changed", "workspace_continuity_error")


def common_directory(path):
    return (path / git(path, "rev-parse", "--git-common-dir")).resolve()


def projection(record):
    return {"workspace": dict(record["workspace"])} if record.get("workspace") else {}


def failure_next_steps(code):
    if code.startswith("workspace") or code in {"workdir_not_allowed", "resume_evidence_error"}:
        return ["Inspect the retained workspace and run artifacts; recover the same checkout manually. Do not recreate or delete it automatically."]
    if code in {"async_concurrency_limit", "concurrency_limit"}:
        return ["Wait for an existing background run to finish before retrying."]
    return ["Inspect preserved run artifacts before retrying the request."]


def native_cwd(home, session_id):
    core = _core()
    try:
        from hermes_state import SessionDB
        path = Path(home) / "state.db"
        if not path.is_file() or path.is_symlink():
            raise ValueError("native session database unavailable")
        with closing(SessionDB(path, read_only=True)) as db:
            effective = db.resolve_resume_session_id(session_id)
            row = db.get_session(effective)
            if not row or not row.get("cwd"):
                raise ValueError("native session cwd unavailable")
            return Path(row["cwd"]).resolve()
    except Exception as exc:
        raise core.ProfileDelegateError(f"Cannot verify effective native cwd; recover manually: {exc}", "workspace_continuity_error") from exc


def before_continue(request, session_id):
    workspace = request.get("workspace")
    if not workspace or not session_id:
        return
    core = _core()
    target = Path(request["workdir"])
    core.enforce_workdir_policy(target, True)
    verify(workspace)
    if native_cwd(request["profile_home"], session_id) != target:
        raise core.ProfileDelegateError("Effective native cwd differs from retained workspace; recover manually", "workspace_continuity_error")


def resume(target, session_id, origin, workdir, policy, records=None):
    """Reuse existing run evidence; authorization is independent of session matching."""
    core = _core()
    matches = []
    for request, status in core.matching_resume_records(target, session_id) if records is None else records:
        if "workspace" in request:
            core.authorize_run("resume", origin, request)
            matches.append(request)
    if not matches:
        return None
    selected = matches[0]
    if any(r.get("workspace") != selected["workspace"] or r.get("workdir") != selected["workdir"] for r in matches):
        raise core.ProfileDelegateError("Conflicting workspace associations; recover manually", "workspace_continuity_error")
    cwd = Path(selected["workdir"])
    if workdir and Path(workdir).expanduser().resolve() != cwd:
        raise core.ProfileDelegateError("Resume workdir must match retained workspace", "workspace_continuity_error")
    core.enforce_workdir_policy(cwd, True, policy)
    before_continue(selected, session_id)
    return selected
