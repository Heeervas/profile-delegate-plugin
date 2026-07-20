"""Profile Delegate 🤝 Hermes plugin. Registers bounded cross-profile delegation tools."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

try:
    from .core import (
        DEFAULT_CHILD_APPROVAL_MODE,
        DEFAULT_TIMEOUT_SECONDS,
        MAX_TIMEOUT_SECONDS,
        ProfileDelegateError,
        delegate_profile,
        profile_delegate_cancel as profile_delegate_cancel,
        profile_delegate_list,
        profile_delegate_policy,
        profile_delegate_prune,
        profile_delegate_status,
        profile_delegate_steer as profile_delegate_steer,
    )
except ImportError:  # direct import / pytest from plugin directory
    import sys
    from pathlib import Path

    plugin_dir = str(Path(__file__).resolve().parent)
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)
    from core import (  # type: ignore[no-redef]
        DEFAULT_CHILD_APPROVAL_MODE,
        DEFAULT_TIMEOUT_SECONDS,
        MAX_TIMEOUT_SECONDS,
        ProfileDelegateError,
        delegate_profile,
        profile_delegate_cancel as profile_delegate_cancel,
        profile_delegate_list,
        profile_delegate_policy,
        profile_delegate_prune,
        profile_delegate_status,
        profile_delegate_steer as profile_delegate_steer,
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
                    "description": (
                        f"Synchronous wait limit. Minimum 10 seconds. Current plugin cap: "
                        f"{'none' if MAX_TIMEOUT_SECONDS <= 0 else str(MAX_TIMEOUT_SECONDS) + ' seconds'}; "
                        "set PROFILE_DELEGATE_MAX_TIMEOUT_SECONDS to raise it, or 0 for no plugin cap. "
                        "On timeout the child process is terminated and a structured timeout result is returned."
                    ),
                    "default": DEFAULT_TIMEOUT_SECONDS,
                    "minimum": 10,
                    **({} if MAX_TIMEOUT_SECONDS <= 0 else {"maximum": MAX_TIMEOUT_SECONDS}),
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
                "background": {
                    "type": "boolean",
                    "description": "Run the target profile asynchronously and return a task_id immediately. Use this for long-running profile work that should outlive the current turn.",
                    "default": False,
                },
                "notify_on_complete": {
                    "type": "boolean",
                    "description": "When background=true, notify the originating chat when the delegated profile finishes. Default true.",
                    "default": True,
                },
                "model": {
                    "type": "string",
                    "description": "Optional requested model for this call. Overrides the target profile default temporarily; blank means inherit.",
                },
                "provider": {
                    "type": "string",
                    "description": "Optional requested provider for this call. Hermes validates compatibility; blank means inherit.",
                },
                "reasoning_effort": {
                    "type": "string",
                    "enum": ["none", "minimal", "low", "medium", "high", "xhigh", "max"],
                    "description": "Explicit child override, including 'none'. Omit it to inherit. Supplying it without reasoning_mode remains a backward-compatible explicit override.",
                },
                "reasoning_mode": {
                    "type": "string", "enum": ["inherit", "override"], "default": "inherit",
                    "description": "inherit creates no reasoning overlay; override requires reasoning_effort. 'none' is explicit, never inheritance.",
                },
                "max_turns": {
                    "type": "integer", "minimum": 1, "maximum": 10000,
                    "description": "Optional requested maximum child agent turns for this call.",
                },
                "toolsets": {
                    "type": "array", "items": {"type": "string"}, "maxItems": 100,
                    "description": "Optional requested toolsets. Every item must be explicitly allowed by PROFILE_DELEGATE_ALLOWED_TOOLSETS.",
                },
                "skills": {
                    "type": "array", "items": {"type": "string"}, "maxItems": 100,
                    "description": "Optional skills to preload. Every item must be explicitly allowed by PROFILE_DELEGATE_ALLOWED_SKILLS.",
                },
                "capability_preset": {
                    "type": "string",
                    "enum": ["review", "build"],
                    "default": "build",
                    "description": (
                        "Plugin-owned capability posture. review exposes web plus file reads/search while the child bootstrap "
                        "removes mutating file tools, terminal/process, and execute_code from the child schema. build preserves "
                        "the selected/inherited build capabilities; it does not bypass approval policy."
                    ),
                },
                "child_approval_mode": {
                    "type": "string",
                    "enum": ["deny", "approve_yolo"],
                    "description": (
                        "Optional per-call child approval policy. Default comes from config.yaml "
                        "plugins.entries.profile-delegate.child_approval_mode, or 'deny' if unset. "
                        "deny installs a plugin-owned immediate denial policy inside the child before agent execution; "
                        "approve_yolo explicitly runs the child with --yolo/HERMES_YOLO_MODE=1; "
                        "hardline and user deny rules remain enforced. Legacy config value strip_only migrates to deny, but new calls reject it."
                    ),
                    "default": DEFAULT_CHILD_APPROVAL_MODE,
                },
                "duplicate_policy": {
                    "type": "string", "enum": ["reuse", "new"], "default": "reuse",
                    "description": "reuse returns an identical active request from the same origin; new intentionally creates another run.",
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


def _steer_schema() -> Dict[str, Any]:
    return {
        "name": "profile_delegate_steer",
        "description": "Steer an active background TUI-backed Profile Delegate run from its exact originating session.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Active Profile Delegate task id."},
                "text": {"type": "string", "minLength": 1, "maxLength": 12000, "description": "Bounded steering instruction delivered through native session.steer."},
            },
            "required": ["task_id", "text"],
            "additionalProperties": False,
        },
    }


def _cancel_schema() -> Dict[str, Any]:
    return {
        "name": "profile_delegate_cancel",
        "description": "Cancel an active background TUI-backed Profile Delegate run through native session.interrupt.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Active Profile Delegate task id."},
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
            "properties": {
                "limit": {"type": "integer", "description": "Maximum matching runs to list, 1-100.", "default": 20},
                "scope": {
                    "type": "string",
                    "enum": ["current_session", "current_lane", "all"],
                    "default": "current_session",
                    "description": "Origin scope. Defaults to the current caller session; use current_lane or all explicitly to widen.",
                },
                "status": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["running", "completed", "failed", "corrupt"]},
                    "description": "Optional lifecycle status filters.",
                },
                "profile": {"type": "string", "description": "Optional exact canonical target-profile filter."},
            },
            "required": [],
            "additionalProperties": False,
        },
    }


def _policy_schema() -> Dict[str, Any]:
    return {
        "name": "profile_delegate_policy",
        "description": "Inspect the effective non-secret Profile Delegate policy before constructing a call.",
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
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
    return {"success": False, "error": str(exc), "error_code": code, "status": "failed", **getattr(exc, "details", {})}


def _current_session_key() -> str:
    try:
        from tools.approval import get_current_session_key

        key = get_current_session_key(default="")
        return key if key != "default" else ""
    except Exception:
        return os.environ.get("HERMES_SESSION_KEY", "")


def _current_origin() -> Dict[str, str]:
    """Capture caller provenance from concurrency-safe Hermes session context."""
    fields = {
        "platform": "HERMES_SESSION_PLATFORM",
        "source": "HERMES_SESSION_SOURCE",
        "profile": "HERMES_SESSION_PROFILE",
        "session_id": "HERMES_SESSION_ID",
        "ui_session_id": "HERMES_UI_SESSION_ID",
        "session_key": "HERMES_SESSION_KEY",
    }
    try:
        from gateway.session_context import get_session_env

        values = {field: str(get_session_env(env_name, "") or "").strip() for field, env_name in fields.items()}
    except Exception:
        values = {field: str(os.environ.get(env_name, "") or "").strip() for field, env_name in fields.items()}
    if not values["session_key"]:
        values["session_key"] = _current_session_key().strip()
    return values


def _handler(args: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
    payload = args if isinstance(args, dict) else {}
    # Hermes may pass internal kwargs such as session_id/task_id to handlers.
    # Model/tool arguments must win so profile_delegate.session_id is not
    # accidentally replaced by the caller's own Hermes session id.
    payload = {**kwargs, **payload}
    try:
        origin = _current_origin()
        result = delegate_profile(
            profile=payload.get("profile", ""),
            task=payload.get("task", ""),
            context=payload.get("context", ""),
            timeout_seconds=payload.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
            output_contract=payload.get("output_contract", ""),
            workdir=payload.get("workdir", ""),
            session_title=payload.get("session_title", ""),
            session_mode=payload.get("session_mode", "new"),
            session_id=payload.get("session_id", ""),
            background=bool(payload.get("background", False)),
            notify_on_complete=bool(payload.get("notify_on_complete", True)),
            origin_session_key=origin["session_key"],
            origin=origin,
            child_approval_mode=payload.get("child_approval_mode", None),
            model=payload.get("model"),
            provider=payload.get("provider"),
            reasoning_effort=payload.get("reasoning_effort"),
            reasoning_mode=payload.get("reasoning_mode"),
            max_turns=payload.get("max_turns"),
            toolsets=payload.get("toolsets"),
            skills=payload.get("skills"),
            capability_preset=payload.get("capability_preset", "build"),
            duplicate_policy=payload.get("duplicate_policy", "reuse"),
        )
    except ProfileDelegateError as exc:
        result = _error_result(exc)
    except Exception as exc:
        result = {"success": False, "error": f"profile_delegate internal error: {type(exc).__name__}: {exc}", "error_code": "internal_error", "status": "failed"}
    return json.dumps(result, ensure_ascii=False, indent=2)


def _status_handler(args: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
    payload = args if isinstance(args, dict) else {}
    # Hermes may pass internal kwargs such as task_id; explicit tool args must win.
    payload = {**kwargs, **payload}
    try:
        result = profile_delegate_status(
            payload.get("task_id", ""),
            payload.get("tail_chars", 4000),
            caller_origin=_current_origin(),
        )
    except ProfileDelegateError as exc:
        result = _error_result(exc)
    except Exception as exc:
        result = {"success": False, "error": f"profile_delegate_status internal error: {type(exc).__name__}: {exc}", "error_code": "internal_error", "status": "failed"}
    return json.dumps(result, ensure_ascii=False, indent=2)


def _steer_handler(args: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
    payload = {**kwargs, **(args if isinstance(args, dict) else {})}
    try:
        result = profile_delegate_steer(
            payload.get("task_id", ""),
            payload.get("text", ""),
            caller_origin=_current_origin(),
        )
    except ProfileDelegateError as exc:
        result = _error_result(exc)
    except Exception as exc:
        result = {"success": False, "error": f"profile_delegate_steer internal error: {type(exc).__name__}: {exc}", "error_code": "internal_error", "status": "failed"}
    return json.dumps(result, ensure_ascii=False, indent=2)


def _cancel_handler(args: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
    payload = {**kwargs, **(args if isinstance(args, dict) else {})}
    try:
        result = profile_delegate_cancel(
            payload.get("task_id", ""), caller_origin=_current_origin()
        )
    except ProfileDelegateError as exc:
        result = _error_result(exc)
    except Exception as exc:
        result = {"success": False, "error": f"profile_delegate_cancel internal error: {type(exc).__name__}: {exc}", "error_code": "internal_error", "status": "failed"}
    return json.dumps(result, ensure_ascii=False, indent=2)


def _list_handler(args: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
    payload = args if isinstance(args, dict) else {}
    payload = {**kwargs, **payload}
    try:
        result = profile_delegate_list(
            limit=payload.get("limit", 20),
            scope=payload.get("scope", "current_session"),
            statuses=payload.get("status"),
            profile=payload.get("profile", ""),
            caller_origin=_current_origin(),
        )
    except ProfileDelegateError as exc:
        result = _error_result(exc)
    except Exception as exc:
        result = {"success": False, "error": f"profile_delegate_list internal error: {type(exc).__name__}: {exc}", "error_code": "internal_error", "status": "failed"}
    return json.dumps(result, ensure_ascii=False, indent=2)


def _prune_handler(args: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
    payload = args if isinstance(args, dict) else {}
    payload = {**kwargs, **payload}
    try:
        result = profile_delegate_prune(payload.get("max_age_days", 14), bool(payload.get("dry_run", True)))
    except ProfileDelegateError as exc:
        result = _error_result(exc)
    except Exception as exc:
        result = {"success": False, "error": f"profile_delegate_prune internal error: {type(exc).__name__}: {exc}", "error_code": "internal_error", "status": "failed"}
    return json.dumps(result, ensure_ascii=False, indent=2)


def _policy_handler(args: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
    try:
        result = profile_delegate_policy()
    except ProfileDelegateError as exc:
        result = _error_result(exc)
    except Exception as exc:
        result = {"success": False, "error": f"profile_delegate_policy internal error: {type(exc).__name__}: {exc}", "error_code": "internal_error", "status": "failed"}
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
        ("profile_delegate_steer", _steer_schema(), _steer_handler, "Steer an active Profile Delegate run."),
        ("profile_delegate_cancel", _cancel_schema(), _cancel_handler, "Cancel an active Profile Delegate run."),
        ("profile_delegate_list", _list_schema(), _list_handler, "List recent Profile Delegate runs."),
        ("profile_delegate_policy", _policy_schema(), _policy_handler, "Inspect effective non-secret Profile Delegate policy."),
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
