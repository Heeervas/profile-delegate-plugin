"""Profile Delegate 🤝 Hermes plugin. Registers bounded cross-profile delegation tools."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

try:
    from .core import (
        ProfileDelegateError,
        delegate_profile,
        profile_delegate_list,
        profile_delegate_prune,
        profile_delegate_status,
    )
except ImportError:  # direct import / pytest from plugin directory
    import sys
    from pathlib import Path

    plugin_dir = str(Path(__file__).resolve().parent)
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)
    from core import (  # type: ignore[no-redef]
        ProfileDelegateError,
        delegate_profile,
        profile_delegate_list,
        profile_delegate_prune,
        profile_delegate_status,
    )


TOOL_DESCRIPTION = (
    "Delegate a bounded task to another Hermes profile using that profile's normal context, memory, rules, and tool defaults. "
    "Use this instead of Kanban for small specialist jobs like review, inspection, drafting, or verification. "
    "Supports fresh one-shot runs or explicit target-profile session resume; no parent approval brokering. "
    "Caller chooses what context to pass; prefer compact summaries and artifact paths over giant transcript dumps. "
    "The target profile's policy/tool permissions apply. Requires PROFILE_DELEGATE_ALLOWED_PROFILES unless explicitly configured to allow all. "
    "Returns compact JSON plus local run artifact paths."
)


def _schema() -> Dict[str, Any]:
    return {
        "name": "profile_delegate",
        "description": TOOL_DESCRIPTION,
        "parameters": {
            "type": "object",
            "properties": {
                "profile": {
                    "type": "string",
                    "description": "Target Hermes profile name, e.g. reviewer, builder, research, work. Must exist locally.",
                },
                "task": {
                    "type": "string",
                    "description": "Self-contained bounded task for the target profile. Be explicit about success criteria.",
                },
                "session_title": {
                    "type": "string",
                    "description": "Required short title for this delegated session/run, max 50 chars. If longer, it is truncated. Broken English or Spanish shorthand is fine, e.g. 'seguir tests builder' or 'review plan riesgos'.",
                },
                "session_mode": {
                    "type": "string",
                    "enum": ["new", "resume"],
                    "description": "Start a fresh target-profile session or resume an explicit target-profile session_id. Default: new.",
                    "default": "new",
                },
                "session_id": {
                    "type": "string",
                    "description": "Target-profile Hermes session id to resume when session_mode='resume'. Use `hermes -p <profile> sessions list` to find it.",
                    "default": "",
                },
                "context": {
                    "type": "string",
                    "description": "Optional caller-selected context. Keep compact; pass paths/artifacts/summaries instead of dumping chat history unless truly needed.",
                    "default": "",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Synchronous wait limit, 10-900 seconds. On timeout the child process is terminated and a structured timeout result is returned.",
                    "default": 240,
                    "minimum": 10,
                    "maximum": 900,
                },
                "output_contract": {
                    "type": "string",
                    "description": "Optional extra output instructions. Default asks target profile to return JSON with status, summary, artifacts, errors, next_steps. If files are created, require paths in artifacts.",
                    "default": "",
                },
                "workdir": {
                    "type": "string",
                    "description": "Optional working directory for the delegated Hermes subprocess. Defaults to the current process working directory.",
                    "default": "",
                },
            },
            "required": ["profile", "task", "session_title"],
            "additionalProperties": False,
        },
    }


def _status_schema() -> Dict[str, Any]:
    return {
        "name": "profile_delegate_status",
        "description": "Read a Profile Delegate run by task_id. Returns status, result, log tails, and artifact paths.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task id returned by profile_delegate, e.g. pd_20260613_083528_9hksdn."},
                "tail_chars": {"type": "integer", "description": "Maximum stdout/stderr tail chars to return, 0-20000.", "default": 4000},
            },
            "required": ["task_id"],
            "additionalProperties": False,
        },
    }


def _list_schema() -> Dict[str, Any]:
    return {
        "name": "profile_delegate_list",
        "description": "List recent Profile Delegate runs for local inspection/debugging.",
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Maximum runs to list, 1-100.", "default": 20}},
            "required": [],
            "additionalProperties": False,
        },
    }


def _prune_schema() -> Dict[str, Any]:
    return {
        "name": "profile_delegate_prune",
        "description": "Prune old Profile Delegate run artifacts from the local runs directory. Dry-run by default.",
        "parameters": {
            "type": "object",
            "properties": {
                "max_age_days": {"type": "integer", "description": "Delete runs older than this many days. Minimum 1.", "default": 14},
                "dry_run": {"type": "boolean", "description": "If true, report matches without deleting.", "default": True},
            },
            "required": [],
            "additionalProperties": False,
        },
    }


def _error_result(exc: Exception) -> Dict[str, Any]:
    code = getattr(exc, "code", "internal_error")
    return {"success": False, "error": str(exc), "error_code": code, "status": "failed"}


def _handler(args: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
    payload = args if isinstance(args, dict) else {}
    payload = {**payload, **kwargs}
    try:
        result = delegate_profile(
            profile=payload.get("profile", ""),
            task=payload.get("task", ""),
            context=payload.get("context", ""),
            timeout_seconds=payload.get("timeout_seconds", 240),
            output_contract=payload.get("output_contract", ""),
            workdir=payload.get("workdir", ""),
            session_title=payload.get("session_title", ""),
            session_mode=payload.get("session_mode", "new"),
            session_id=payload.get("session_id", ""),
        )
    except ProfileDelegateError as exc:
        result = _error_result(exc)
    except Exception as exc:
        result = {"success": False, "error": f"profile_delegate internal error: {type(exc).__name__}: {exc}", "error_code": "internal_error", "status": "failed"}
    return json.dumps(result, ensure_ascii=False, indent=2)


def _status_handler(args: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
    payload = args if isinstance(args, dict) else {}
    payload = {**payload, **kwargs}
    try:
        result = profile_delegate_status(payload.get("task_id", ""), payload.get("tail_chars", 4000))
    except ProfileDelegateError as exc:
        result = _error_result(exc)
    except Exception as exc:
        result = {"success": False, "error": f"profile_delegate_status internal error: {type(exc).__name__}: {exc}", "error_code": "internal_error", "status": "failed"}
    return json.dumps(result, ensure_ascii=False, indent=2)


def _list_handler(args: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
    payload = args if isinstance(args, dict) else {}
    payload = {**payload, **kwargs}
    try:
        result = profile_delegate_list(payload.get("limit", 20))
    except ProfileDelegateError as exc:
        result = _error_result(exc)
    except Exception as exc:
        result = {"success": False, "error": f"profile_delegate_list internal error: {type(exc).__name__}: {exc}", "error_code": "internal_error", "status": "failed"}
    return json.dumps(result, ensure_ascii=False, indent=2)


def _prune_handler(args: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
    payload = args if isinstance(args, dict) else {}
    payload = {**payload, **kwargs}
    try:
        result = profile_delegate_prune(payload.get("max_age_days", 14), bool(payload.get("dry_run", True)))
    except ProfileDelegateError as exc:
        result = _error_result(exc)
    except Exception as exc:
        result = {"success": False, "error": f"profile_delegate_prune internal error: {type(exc).__name__}: {exc}", "error_code": "internal_error", "status": "failed"}
    return json.dumps(result, ensure_ascii=False, indent=2)


def _oneline(text: str) -> str:
    return " ".join(str(text or "").split())


def _profile_delegate_preview(args: Dict[str, Any], max_len: int | None = None) -> str:
    profile = _oneline(args.get("profile") or "?")
    task = _oneline(args.get("session_title") or args.get("task") or "")
    if max_len is None or max_len <= 0:
        task_budget = 96
    else:
        task_budget = max(16, max_len - len(profile) - len("to : "))
    if len(task) > task_budget:
        task = task[: max(0, task_budget - 3)] + "..."
    return f"to {profile}: {task}" if task else f"to {profile}"


def _install_tool_preview_patch() -> None:
    """Patch Hermes' display preview for this plugin until core exposes a preview hook."""
    if os.getenv("PROFILE_DELEGATE_ENABLE_PREVIEW_PATCH", "true").strip().lower() in {"0", "false", "no", "off"}:
        return
    try:
        import agent.display as display
    except Exception:
        return

    current = getattr(display, "build_tool_preview", None)
    if not callable(current) or getattr(current, "_profile_delegate_patch", False):
        return

    def wrapped(tool_name: str, args: dict, max_len: int | None = None):
        if tool_name == "profile_delegate" and isinstance(args, dict):
            return _profile_delegate_preview(args, max_len=max_len)
        return current(tool_name, args, max_len=max_len)

    wrapped._profile_delegate_patch = True  # type: ignore[attr-defined]
    display.build_tool_preview = wrapped

    try:
        import run_agent
        if getattr(run_agent, "_build_tool_preview", None) is current:
            run_agent._build_tool_preview = wrapped
    except Exception:
        pass


def register(ctx: Any) -> None:
    _install_tool_preview_patch()
    for name, schema, handler, desc in [
        ("profile_delegate", _schema(), _handler, "Profile Delegate 🤝: bounded task delegation to another Hermes profile."),
        ("profile_delegate_status", _status_schema(), _status_handler, "Inspect a Profile Delegate run by task_id."),
        ("profile_delegate_list", _list_schema(), _list_handler, "List recent Profile Delegate runs."),
        ("profile_delegate_prune", _prune_schema(), _prune_handler, "Prune old Profile Delegate run artifacts."),
    ]:
        ctx.register_tool(
            name=name,
            toolset="delegation",
            schema=schema,
            handler=handler,
            check_fn=lambda: True,
            requires_env=[],
            description=desc,
            emoji="🤝",
        )
