"""Profile Delegate core. Usage: imported by plugin; delegates bounded tasks to Hermes profiles."""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import string
import selectors
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:  # Unix-only; Hermes currently targets Linux/macOS/WSL for this plugin.
    import fcntl
except Exception:  # pragma: no cover - Windows fallback is conservative.
    fcntl = None  # type: ignore[assignment]

def _int_env_at_import(name: str, default: int, minimum: int, maximum: Optional[int] = None) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except Exception:
        return default
    if value < minimum:
        return default
    if maximum is not None and value > maximum:
        return default
    return value


DEFAULT_TIMEOUT_SECONDS = _int_env_at_import("PROFILE_DELEGATE_DEFAULT_TIMEOUT_SECONDS", 1200, 10)


def _max_timeout_env_at_import() -> int:
    raw = os.getenv("PROFILE_DELEGATE_MAX_TIMEOUT_SECONDS", "").strip()
    if raw == "0":
        return 0
    return _int_env_at_import("PROFILE_DELEGATE_MAX_TIMEOUT_SECONDS", max(DEFAULT_TIMEOUT_SECONDS, 1800), DEFAULT_TIMEOUT_SECONDS)


MAX_TIMEOUT_SECONDS = _max_timeout_env_at_import()
MAX_TASK_CHARS = 30_000
MAX_CONTEXT_CHARS = 60_000
MAX_OUTPUT_CONTRACT_CHARS = 8_000
MAX_SESSION_TITLE_CHARS = 50
MAX_SESSION_ID_CHARS = 200
DEFAULT_MAX_STDOUT_CHARS = 200_000
DEFAULT_MAX_STDERR_CHARS = 100_000
DEFAULT_MAX_DEPTH = 1
DEFAULT_MAX_CONCURRENT = 1
DEFAULT_MAX_ASYNC = 2
DEFAULT_MAX_TRANSIENT_RESUMES = 2
TRANSIENT_RESUME_DELAY_SECONDS = 10
DIAGNOSTIC_TAIL_CHARS = 4_000
DIAGNOSTIC_TAIL_LINES = 20
VALID_RESULT_STATUSES = {"ok", "blocked", "failed"}
VALID_SESSION_MODES = {"new", "resume"}
VALID_CHILD_APPROVAL_MODES = {"deny", "approve_yolo"}
LEGACY_CHILD_APPROVAL_MODES = {"strip_only"}
VALID_CAPABILITY_PRESETS = {"review", "build"}
REVIEW_TOOLSETS = ["web", "file"]
REVIEW_BLOCKED_TOOLS = [
    "write_file", "patch", "execute_code", "terminal", "process",
    "skill_manage", "memory", "cronjob", "send_message", "delegate_task",
    "profile_delegate", "profile_delegate_prune",
]
VALID_REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
DEFAULT_CHILD_APPROVAL_MODE = "deny"
DEFAULT_CAPABILITY_PRESET = "build"
TRUTHY = {"1", "true", "yes", "on"}
MAX_EXECUTION_NAME_CHARS = 200
MAX_EXECUTION_LIST_ITEMS = 100
APPROVAL_TIMEOUT_MARKERS = ("Timeout — denying command", "Timeout - denying command")
PLUGIN_DIR = Path(__file__).resolve().parent
CHILD_BOOTSTRAP = PLUGIN_DIR / "child_bootstrap.py"
ARTIFACT_SCHEMA_VERSION = 2
ORIGIN_FIELDS = ("platform", "source", "profile", "session_id", "ui_session_id", "session_key")
MAX_ORIGIN_VALUE_CHARS = 500
VALID_INSPECTION_SCOPES = {"current_session", "current_lane", "all"}
VALID_RUN_STATUSES = {"running", "completed", "failed", "corrupt"}

TRANSIENT_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("incomplete_chunked_read", re.compile(r"^(?:[\w.]+\.)?RemoteProtocolError:\s*(?:peer closed connection without sending complete message body|incomplete chunked read).*$", re.I)),
    ("connection_reset", re.compile(r"^(?:[\w.]+(?:Error|Exception):\s*)?.*Connection reset by peer\.?$", re.I)),
    ("stream_closed_prematurely", re.compile(r"^(?:API call failed after \d+ retries:|(?:[\w.]+\.)?(?:ReadError|WriteError|NetworkError):)\s*.*(?:stream closed prematurely|stream ended unexpectedly)\.?$", re.I)),
    ("provider_503", re.compile(r"^API call failed after \d+ retries:\s*HTTP 503(?::|\s).*(?:Service Unavailable|upstream|temporarily unavailable|try again|retry later).*$", re.I)),
    ("codex_slots_temporarily_unavailable", re.compile(r"^(?:HTTP 503:\s*)?All Codex auth slots are temporarily unavailable.*(?:upstream|try again|retry later).*$", re.I)),
    ("server_disconnected", re.compile(r"^(?:[\w.]+\.)?ServerDisconnectedError:\s*\S.*$", re.I)),
    ("remote_protocol_error", re.compile(r"^(?:[\w.]+\.)?RemoteProtocolError:\s*\S.*$", re.I)),
    ("connection_error", re.compile(r"^API call failed after \d+ retries:\s*Connection error\.?$", re.I)),
)


class ProfileDelegateError(Exception):
    """Expected profile-delegate failure with a stable machine-readable code."""

    def __init__(self, message: str, code: str = "profile_delegate_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class ValidatedProfile:
    requested: str
    canonical: str
    home: str


class ConcurrencySlot:
    """Held lock file descriptor for one active delegation slot."""

    def __init__(self, path: Path, handle: Any, slot: int) -> None:
        self.path = path
        self.handle = handle
        self.slot = slot

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            if fcntl is not None:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            try:
                self.handle.close()
            finally:
                self.handle = None

    def __enter__(self) -> "ConcurrencySlot":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.release()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def normalize_origin(origin: Any = None, legacy_session_key: Any = "") -> Dict[str, str]:
    """Return the bounded, privacy-minimal origin provenance shape."""
    source = origin if isinstance(origin, dict) else {}
    normalized = {
        field: ensure_text(source.get(field, "")).strip()[:MAX_ORIGIN_VALUE_CHARS]
        for field in ORIGIN_FIELDS
    }
    if not normalized["session_key"]:
        normalized["session_key"] = ensure_text(legacy_session_key).strip()[:MAX_ORIGIN_VALUE_CHARS]
    return normalized


def normalize_persisted_origin(artifact: Any) -> Dict[str, str]:
    artifact_dict = artifact if isinstance(artifact, dict) else {}
    return normalize_origin(
        artifact_dict.get("origin"),
        artifact_dict.get("origin_session_key", ""),
    )


def origin_match(
    run_origin: Any,
    caller_origin: Any,
    scope: str = "current_session",
) -> Tuple[bool, Optional[str]]:
    """Compare run provenance without weakening a present identifier mismatch."""
    if scope == "all":
        return True, None
    run = normalize_origin(run_origin)
    caller = normalize_origin(caller_origin)
    fields = ("session_key",) if scope == "current_lane" else (
        "ui_session_id", "session_id", "session_key"
    )
    for field in fields:
        if caller[field] and run[field]:
            return run[field] == caller[field], field
    return False, None


def probe_worker_alive(pid: Any) -> Optional[bool]:
    """Return advisory process liveness without changing run state."""
    if isinstance(pid, bool):
        return None
    try:
        normalized_pid = int(pid)
    except (TypeError, ValueError):
        return None
    if normalized_pid <= 0:
        return None
    try:
        os.kill(normalized_pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def derive_activity(status: Any) -> Dict[str, Any]:
    """Project advisory activity from canonical status; never mutate artifacts."""
    data = status if isinstance(status, dict) else {}
    lifecycle = ensure_text(data.get("status")).strip().lower()
    if lifecycle in {"completed", "failed"}:
        return {"activity": "finished", "worker_alive": None}
    if lifecycle != "running" or data.get("background_worker_mode") != "detached":
        return {"activity": "unknown", "worker_alive": None}
    alive = probe_worker_alive(data.get("worker_pid"))
    if alive is True:
        return {"activity": "active", "worker_alive": True}
    if alive is False:
        return {"activity": "stale", "worker_alive": False}
    return {"activity": "unknown", "worker_alive": None}


def make_task_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    return f"pd_{stamp}_{suffix}"


def get_hermes_home_path() -> Path:
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home()).expanduser().resolve()
    except Exception:
        return Path(os.getenv("HERMES_HOME", Path.home() / ".hermes")).expanduser().resolve()


def get_runs_root() -> Path:
    override = os.getenv("PROFILE_DELEGATE_RUNS_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return get_hermes_home_path() / "profile_delegate" / "runs"


def get_locks_root() -> Path:
    override = os.getenv("PROFILE_DELEGATE_LOCKS_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return get_hermes_home_path() / "profile_delegate" / "locks"


def chmod_best_effort(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except PermissionError:
        # Existing shared runtime dirs may be group-writable but owned by the
        # host user. Writing can still be valid even when chmod is forbidden.
        pass


def json_safe_write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    chmod_best_effort(tmp, 0o600)
    tmp.replace(path)


def read_json_file(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProfileDelegateError(f"file not found: {path}", "file_not_found") from exc
    except json.JSONDecodeError as exc:
        raise ProfileDelegateError(f"invalid JSON in {path}: {exc}", "invalid_json") from exc
    if not isinstance(data, dict):
        raise ProfileDelegateError(f"expected object JSON in {path}", "invalid_json_shape")
    return data


def ensure_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def text_safe_write(path: Path, text: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(ensure_text(text), encoding="utf-8")
    chmod_best_effort(path, 0o600)


def tail_text(path: Path, max_chars: int = 4000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    return text[-max_chars:] if max_chars and len(text) > max_chars else text


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in TRUTHY


def env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except Exception as exc:
        raise ProfileDelegateError(f"{name} must be an integer", "configuration_error") from exc
    if value < minimum or value > maximum:
        raise ProfileDelegateError(f"{name} must be between {minimum} and {maximum}", "configuration_error")
    return value


def parse_csv_env(name: str) -> List[str]:
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _optional_execution_string(name: str, value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProfileDelegateError(f"{name} must be a string", "validation_error")
    text = value.strip()
    if not text:
        return None
    if len(text) > MAX_EXECUTION_NAME_CHARS or any(ord(char) < 32 for char in text):
        raise ProfileDelegateError(f"{name} is invalid or too long", "validation_error")
    return text


def _execution_list(name: str, value: Any, policy_env: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProfileDelegateError(f"{name} must be an array of strings", "validation_error")
    if len(value) > MAX_EXECUTION_LIST_ITEMS:
        raise ProfileDelegateError(f"{name} has too many items", "validation_error")
    normalized: List[str] = []
    for item in value:
        text = _optional_execution_string(name, item)
        if not text or "," in text:
            raise ProfileDelegateError(f"{name} entries must be non-empty strings without commas", "validation_error")
        if text not in normalized:
            normalized.append(text)
    if normalized:
        allowed = set(parse_csv_env(policy_env))
        if not allowed:
            raise ProfileDelegateError(f"{name} overrides require {policy_env}", "validation_error")
        rejected = [item for item in normalized if item not in allowed]
        if rejected:
            raise ProfileDelegateError(f"{name} not allowed by {policy_env}: {', '.join(rejected)}", "validation_error")
    return normalized


def normalize_requested_execution(
    model: Any = None, provider: Any = None, reasoning_effort: Any = None,
    max_turns: Any = None, toolsets: Any = None, skills: Any = None,
) -> Dict[str, Any]:
    normalized_reasoning = _optional_execution_string("reasoning_effort", reasoning_effort)
    if normalized_reasoning and normalized_reasoning not in VALID_REASONING_EFFORTS:
        raise ProfileDelegateError("reasoning_effort must be one of: " + ", ".join(VALID_REASONING_EFFORTS), "validation_error")
    normalized_turns: Optional[int] = None
    if max_turns is not None:
        if isinstance(max_turns, bool):
            raise ProfileDelegateError("max_turns must be an integer", "validation_error")
        try:
            normalized_turns = int(max_turns)
        except Exception as exc:
            raise ProfileDelegateError("max_turns must be an integer", "validation_error") from exc
        if normalized_turns < 1 or normalized_turns > 10000:
            raise ProfileDelegateError("max_turns must be between 1 and 10000", "validation_error")
    return {
        "model": _optional_execution_string("model", model),
        "provider": _optional_execution_string("provider", provider),
        "reasoning_effort": normalized_reasoning,
        "max_turns": normalized_turns,
        "toolsets": _execution_list("toolsets", toolsets, "PROFILE_DELEGATE_ALLOWED_TOOLSETS"),
        "skills": _execution_list("skills", skills, "PROFILE_DELEGATE_ALLOWED_SKILLS"),
    }


def resolve_capability_preset(
    preset: Any, requested_execution: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Resolve a plugin-owned child capability posture without widening parent policy."""
    normalized = (ensure_text(preset) or DEFAULT_CAPABILITY_PRESET).strip().lower().replace("-", "_")
    if normalized not in VALID_CAPABILITY_PRESETS:
        raise ProfileDelegateError("capability_preset must be one of: review, build", "validation_error")
    effective = dict(requested_execution)
    if normalized == "review":
        if effective.get("toolsets"):
            raise ProfileDelegateError(
                "capability_preset='review' cannot be combined with toolsets overrides",
                "validation_error",
            )
        # Hermes' file toolset also contains mutators. The child bootstrap removes
        # those tool schemas before agent execution, leaving read_file/search_files.
        effective["toolsets"] = list(REVIEW_TOOLSETS)
        return effective, {
            "preset": "review",
            "toolsets": list(REVIEW_TOOLSETS),
            "blocked_tools": list(REVIEW_BLOCKED_TOOLS),
            "terminal_access": False,
            "read_only_terminal_claimed": False,
        }
    return effective, {
        "preset": "build",
        "toolsets": list(effective.get("toolsets") or []),
        "blocked_tools": [],
        "terminal_access": "terminal" in (effective.get("toolsets") or []),
        "read_only_terminal_claimed": False,
    }


def normalize_profile_for_policy(profile: str) -> str:
    try:
        from hermes_cli.profiles import normalize_profile_name

        return normalize_profile_name(profile)
    except Exception:
        return profile.strip().lower()


def enforce_profile_policy(canonical_profile: str) -> None:
    """Require an explicit profile allowlist unless allow-all is deliberately enabled."""
    if env_bool("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", False):
        return
    allowed = {normalize_profile_for_policy(item) for item in parse_csv_env("PROFILE_DELEGATE_ALLOWED_PROFILES")}
    if not allowed:
        raise ProfileDelegateError(
            "profile delegation is disabled until PROFILE_DELEGATE_ALLOWED_PROFILES is set "
            "or PROFILE_DELEGATE_ALLOW_ALL_PROFILES=true is explicitly configured",
            "profile_policy_required",
        )
    if canonical_profile not in allowed:
        raise ProfileDelegateError(
            f"profile {canonical_profile!r} is not allowed by PROFILE_DELEGATE_ALLOWED_PROFILES",
            "profile_not_allowed",
        )


def current_depth() -> int:
    raw = os.getenv("PROFILE_DELEGATE_DEPTH", "0").strip() or "0"
    try:
        depth = int(raw)
    except Exception as exc:
        raise ProfileDelegateError("PROFILE_DELEGATE_DEPTH must be an integer", "configuration_error") from exc
    if depth < 0:
        raise ProfileDelegateError("PROFILE_DELEGATE_DEPTH must be >= 0", "configuration_error")
    return depth


def enforce_depth_policy() -> Tuple[int, int]:
    depth = current_depth()
    max_depth = env_int("PROFILE_DELEGATE_MAX_DEPTH", DEFAULT_MAX_DEPTH, 0, 20)
    if depth >= max_depth:
        raise ProfileDelegateError(
            f"profile delegation recursion limit reached: depth={depth}, max={max_depth}",
            "recursion_limit",
        )
    return depth, max_depth


def acquire_concurrency_slot() -> ConcurrencySlot:
    max_concurrent = env_int("PROFILE_DELEGATE_MAX_CONCURRENT", DEFAULT_MAX_CONCURRENT, 1, 100)
    if fcntl is None:
        if max_concurrent != 1:
            raise ProfileDelegateError("concurrency limits require fcntl on this platform", "configuration_error")
        # Conservative fallback: no reliable interprocess lock, but keep code usable.
        root = get_locks_root()
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        return ConcurrencySlot(root / "slot_0.lock", None, 0)

    root = get_locks_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    chmod_best_effort(root, 0o700)
    for slot in range(max_concurrent):
        path = root / f"slot_{slot}.lock"
        handle = path.open("a+", encoding="utf-8")
        chmod_best_effort(path, 0o600)
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            handle.seek(0)
            handle.truncate()
            handle.write(json.dumps({"pid": os.getpid(), "acquired_at": now_iso(), "slot": slot}))
            handle.flush()
            return ConcurrencySlot(path, handle, slot)
        except BlockingIOError:
            handle.close()
            continue
    raise ProfileDelegateError(
        f"profile delegation concurrency limit reached ({max_concurrent} active slot(s))",
        "concurrency_limit",
    )


def resolve_hermes_bin() -> str:
    configured = os.getenv("PROFILE_DELEGATE_HERMES_BIN", "").strip()
    if configured:
        path = Path(configured).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise ProfileDelegateError(f"PROFILE_DELEGATE_HERMES_BIN does not exist: {path}", "hermes_missing")
        if not os.access(path, os.X_OK):
            raise ProfileDelegateError(f"PROFILE_DELEGATE_HERMES_BIN is not executable: {path}", "hermes_not_executable")
        return str(path)

    found = shutil.which("hermes")
    if not found:
        raise ProfileDelegateError("hermes command not found on PATH", "hermes_missing")
    path = Path(found).resolve()
    if not os.access(path, os.X_OK):
        raise ProfileDelegateError(f"resolved hermes is not executable: {path}", "hermes_not_executable")
    return str(path)


def validate_profile(profile: str) -> ValidatedProfile:
    if not isinstance(profile, str) or not profile.strip():
        raise ProfileDelegateError("profile must be a non-empty string", "validation_error")
    raw = profile.strip()
    try:
        from hermes_cli.profiles import (
            get_profile_dir,
            normalize_profile_name,
            profile_exists,
            validate_profile_name,
        )

        canonical = normalize_profile_name(raw)
        validate_profile_name(canonical)
        if not profile_exists(canonical):
            raise ProfileDelegateError(f"profile {canonical!r} does not exist", "profile_not_found")
        home = str(get_profile_dir(canonical))
    except ProfileDelegateError:
        raise
    except Exception as exc:
        raise ProfileDelegateError(
            f"failed to validate profile {raw!r}: {type(exc).__name__}: {exc}",
            "profile_validation_failed",
        ) from exc
    enforce_profile_policy(canonical)
    return ValidatedProfile(requested=raw, canonical=canonical, home=home)


def coerce_timeout(value: Any) -> int:
    try:
        timeout = int(value or DEFAULT_TIMEOUT_SECONDS)
    except Exception as exc:
        raise ProfileDelegateError("timeout_seconds must be an integer", "validation_error") from exc
    if timeout < 10:
        raise ProfileDelegateError("timeout_seconds must be >= 10", "validation_error")
    if MAX_TIMEOUT_SECONDS > 0 and timeout > MAX_TIMEOUT_SECONDS:
        raise ProfileDelegateError(f"timeout_seconds must be <= {MAX_TIMEOUT_SECONDS} (set PROFILE_DELEGATE_MAX_TIMEOUT_SECONDS=0 for no plugin cap)", "validation_error")
    return timeout


def bounded_text(name: str, value: Any, limit: int) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) > limit:
        raise ProfileDelegateError(f"{name} is too large ({len(text)} chars > {limit})", "input_too_large")
    return text


def allowed_workdir_roots() -> List[Path]:
    return [Path(item).expanduser().resolve() for item in parse_csv_env("PROFILE_DELEGATE_ALLOWED_WORKDIRS")]


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def enforce_workdir_policy(cwd: Path, explicit_workdir: bool) -> None:
    roots = allowed_workdir_roots()
    if roots:
        if any(is_relative_to(cwd, root) for root in roots):
            return
        raise ProfileDelegateError(
            f"workdir {cwd} is not under PROFILE_DELEGATE_ALLOWED_WORKDIRS",
            "workdir_not_allowed",
        )

    # Safe public default: without an allowlist, callers may only use the current
    # process working directory. This preserves simple installs while preventing
    # model-selected arbitrary filesystem roots.
    process_cwd = Path.cwd().resolve()
    if cwd == process_cwd and not explicit_workdir:
        return
    raise ProfileDelegateError(
        "explicit workdir delegation requires PROFILE_DELEGATE_ALLOWED_WORKDIRS",
        "workdir_policy_required",
    )


def normalize_session_title(value: Any) -> str:
    title = " ".join(str(value or "").split())
    if not title:
        raise ProfileDelegateError("session_title is required", "validation_error")
    return title[:MAX_SESSION_TITLE_CHARS]


def coerce_session_mode(value: Any) -> str:
    mode = (ensure_text(value) or "new").strip().lower()
    if mode not in VALID_SESSION_MODES:
        raise ProfileDelegateError("session_mode must be 'new' or 'resume'", "validation_error")
    return mode


def coerce_child_approval_mode(value: Any, *, allow_legacy_config: bool = False) -> str:
    mode = (ensure_text(value) or DEFAULT_CHILD_APPROVAL_MODE).strip().lower().replace("-", "_")
    aliases = {
        "approve": "approve_yolo",
        "yolo": "approve_yolo",
        "off": "approve_yolo",
        "auto": "approve_yolo",
        "block": "deny",
        "blocked": "deny",
        "strip": "strip_only",
        "none": "strip_only",
    }
    mode = aliases.get(mode, mode)
    if mode in LEGACY_CHILD_APPROVAL_MODES:
        if allow_legacy_config:
            return "deny"
        raise ProfileDelegateError(
            "child_approval_mode='strip_only' is deprecated and no longer accepted for new calls; use 'deny'",
            "validation_error",
        )
    if mode not in VALID_CHILD_APPROVAL_MODES:
        raise ProfileDelegateError(
            "child_approval_mode must be one of: deny, approve_yolo",
            "validation_error",
        )
    return mode


def plugin_config_child_approval_mode() -> str:
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        entries = (cfg.get("plugins") or {}).get("entries") or {}
        entry = entries.get("profile-delegate") or {}
        return coerce_child_approval_mode(
            entry.get("child_approval_mode", DEFAULT_CHILD_APPROVAL_MODE),
            allow_legacy_config=True,
        )
    except ProfileDelegateError:
        raise
    except Exception:
        return DEFAULT_CHILD_APPROVAL_MODE


def validate_session_id(value: Any, required: bool = False) -> str:
    text = bounded_text("session_id", value, MAX_SESSION_ID_CHARS).strip()
    if required and not text:
        raise ProfileDelegateError("session_id is required when session_mode='resume'", "validation_error")
    if text and not re.fullmatch(r"[A-Za-z0-9_.:@/+\-= ]{1,200}", text):
        raise ProfileDelegateError("session_id contains unsupported characters", "validation_error")
    return text


def resolve_workdir(workdir: str = "") -> Path:
    raw = (workdir or "").strip()
    explicit = bool(raw)
    candidate = Path(raw).expanduser() if raw else Path.cwd()
    cwd = candidate.resolve()
    if not cwd.exists() or not cwd.is_dir():
        raise ProfileDelegateError(f"workdir does not exist or is not a directory: {cwd}", "workdir_not_found")
    enforce_workdir_policy(cwd, explicit)
    return cwd


def load_yaml_mapping(path: Path) -> Dict[str, Any]:
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise ProfileDelegateError(f"failed to load profile config {path}: {exc}", "reasoning_overlay_error") from exc
    if not isinstance(data, dict):
        raise ProfileDelegateError(f"profile config must contain a mapping: {path}", "reasoning_overlay_error")
    return data


DEFAULT_MANAGED_SCOPE = Path("/etc/hermes")


def discover_managed_scope(env: Dict[str, str]) -> Optional[Path]:
    """Find any inherited or canonical administrator-managed scope."""
    override = env.get("HERMES_MANAGED_DIR", "").strip()
    if override:
        return Path(override)
    return DEFAULT_MANAGED_SCOPE if DEFAULT_MANAGED_SCOPE.exists() else None


def prepare_reasoning_config(run_dir: Path, reasoning_effort: str) -> Path:
    """Create config-only managed input when no administrator scope exists."""
    managed_dir = run_dir / "reasoning_config"
    if managed_dir.is_symlink():
        raise ProfileDelegateError("reasoning overlay path must not be a symlink", "reasoning_overlay_error")
    try:
        managed_dir.mkdir(mode=0o700)
        chmod_best_effort(managed_dir, 0o700)
        config_path = managed_dir / "config.yaml"
        import yaml

        config_path.write_text(yaml.safe_dump({"agent": {"reasoning_effort": reasoning_effort}}, sort_keys=False), encoding="utf-8")
        chmod_best_effort(config_path, 0o600)
    except ProfileDelegateError:
        raise
    except Exception as exc:
        raise ProfileDelegateError(f"failed to write reasoning overlay: {exc}", "reasoning_overlay_error") from exc
    return managed_dir


def build_child_command(
    request: Dict[str, Any], run_dir: Path, *,
    prompt_path: Optional[Path] = None,
    resume_session_id: Optional[str] = None,
) -> List[str]:
    requested = request.get("effective_execution") or request.get("requested_execution") or {}
    hermes_cmd = [ensure_text(request.get("hermes_bin")), "-p", ensure_text(request.get("profile")),
                  "chat", "-q", f"@file:{prompt_path or (run_dir / 'prompt.txt')}", "-Q"]
    approval_mode = ensure_text(request.get("child_approval_mode")) or DEFAULT_CHILD_APPROVAL_MODE
    if approval_mode == "approve_yolo":
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

    capabilities = request.get("effective_capabilities") or {}
    blocked_tools = capabilities.get("blocked_tools") or []
    child_python = str(Path(ensure_text(request.get("hermes_bin"))).resolve().parent / "python")
    if not Path(child_python).is_file():
        child_python = sys.executable
    return [
        child_python, str(CHILD_BOOTSTRAP),
        "--approval-mode", approval_mode,
        "--events-path", str(run_dir / "approval_events.jsonl"),
        "--blocked-tools", ",".join(ensure_text(item) for item in blocked_tools),
        "--", *hermes_cmd,
    ]


def capped_text(text: str, limit: int) -> Tuple[str, bool]:
    if limit < 0:
        limit = 0
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def output_limits() -> Tuple[int, int]:
    stdout_limit = env_int("PROFILE_DELEGATE_MAX_STDOUT_CHARS", DEFAULT_MAX_STDOUT_CHARS, 0, 10_000_000)
    stderr_limit = env_int("PROFILE_DELEGATE_MAX_STDERR_CHARS", DEFAULT_MAX_STDERR_CHARS, 0, 10_000_000)
    return stdout_limit, stderr_limit


def append_capped(path: Path, chunk: str, written: int, limit: int) -> Tuple[int, bool]:
    if not chunk or written >= limit:
        return written, bool(chunk)
    remaining = limit - written
    kept = chunk[:remaining]
    with path.open("a", encoding="utf-8", errors="replace") as handle:
        handle.write(kept)
    return written + len(kept), len(chunk) > remaining


def run_capped_subprocess(cmd: List[str], cwd: Path, env: Dict[str, str], timeout: int, stdout_path: Path, stderr_path: Path) -> Dict[str, Any]:
    """Run child process while streaming stdout/stderr to capped files."""
    stdout_limit, stderr_limit = output_limits()
    text_safe_write(stdout_path, "")
    text_safe_write(stderr_path, "")
    stdout_written = 0
    stderr_written = 0
    stdout_truncated = False
    stderr_truncated = False
    timed_out = False
    exit_code: Optional[int] = None
    diagnostic_tails = {"stdout": "", "stderr": ""}

    with subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    ) as proc:
        assert proc.stdout is not None
        assert proc.stderr is not None
        sel = selectors.DefaultSelector()
        sel.register(proc.stdout, selectors.EVENT_READ, "stdout")
        sel.register(proc.stderr, selectors.EVENT_READ, "stderr")
        deadline = time.monotonic() + timeout

        while sel.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                break
            events = sel.select(timeout=min(0.2, remaining))
            if not events:
                if proc.poll() is not None:
                    continue
                continue
            for key, _mask in events:
                stream = key.fileobj
                chunk_bytes = os.read(stream.fileno(), 8192)
                if not chunk_bytes:
                    try:
                        sel.unregister(stream)
                    except Exception:
                        pass
                    continue
                chunk = chunk_bytes.decode("utf-8", "replace")
                diagnostic_tails[key.data] = (diagnostic_tails[key.data] + chunk)[-DIAGNOSTIC_TAIL_CHARS:]
                if key.data == "stdout":
                    stdout_written, truncated = append_capped(stdout_path, chunk, stdout_written, stdout_limit)
                    stdout_truncated = stdout_truncated or truncated
                else:
                    stderr_written, truncated = append_capped(stderr_path, chunk, stderr_written, stderr_limit)
                    stderr_truncated = stderr_truncated or truncated

        if timed_out:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        else:
            exit_code = proc.wait(timeout=max(1, int(deadline - time.monotonic()) + 1))

    chmod_best_effort(stdout_path, 0o600)
    chmod_best_effort(stderr_path, 0o600)
    return {
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "stdout_chars": stdout_written,
        "stderr_chars": stderr_written,
        "stdout_limit": stdout_limit,
        "stderr_limit": stderr_limit,
        "stdout_diagnostic_tail": diagnostic_tails["stdout"],
        "stderr_diagnostic_tail": diagnostic_tails["stderr"],
    }

def build_prompt(task: str, context: str = "", output_contract: str = "") -> str:
    contract = output_contract.strip() or "Use the default JSON schema exactly."
    context_block = context.strip() or "(none provided)"
    return f"""You are being delegated a bounded task by another Hermes profile.

Return ONLY valid JSON matching this default schema unless the additional output contract below narrows it:
{{
  "status": "ok|blocked|failed",
  "summary": "concise summary string",
  "artifacts": ["absolute paths or URLs for files/artifacts created or relevant"],
  "errors": ["concise error strings"],
  "next_steps": ["concise next step strings"]
}}

Rules:
- Be concise.
- Include file paths in artifacts if you create, modify, or rely on files.
- Do not include markdown outside JSON.
- If blocked, set status="blocked" and explain exactly what is needed.
- Preserve your profile's normal policy and tool judgment.

Task:
{task.strip()}

Caller-provided context:
{context_block}

Additional output contract:
{contract}
"""


def _delegate_envelope_score(obj: Any) -> int:
    """Rank JSON objects by how likely they are to be the child profile's final result.

    Child Hermes stdout can contain warnings or nested JSON. Returning the last
    raw-decodable object is unsafe because a nested dict such as a rating
    distribution may be the final decodable object. Keep this generic: score
    profile_delegate-style envelopes highest, then known structured profile
    envelopes, and treat small nested placeholder/config maps as non-results.
    """
    if not isinstance(obj, dict):
        return 0

    keys = set(obj.keys())
    status = str(obj.get("status") or "").strip().lower()
    valid_status = status in VALID_RESULT_STATUSES
    has_summary = "summary" in keys
    has_delegate_arrays = bool({"artifacts", "errors", "next_steps"} & keys)

    score = 0
    if valid_status:
        score += 20
    elif "status" in keys:
        score += 5
    if has_summary:
        score += 10
    if has_delegate_arrays:
        score += 10
    if {"artifacts", "errors", "next_steps"}.issubset(keys):
        score += 15

    # Generic structured-profile envelope signals. These are not SSR-only;
    # profiles may return richer contracts while still using profile_delegate.
    if "ssr_status" in keys:
        score += 15
    if "normalized_input" in keys:
        score += 8
    if "evaluation_design" in keys:
        score += 8
    if "personas" in keys:
        score += 5

    # "mode" is too generic to score by itself, but it strengthens an already
    # plausible result envelope.
    if "mode" in keys and score >= 20:
        score += 3

    # A bare map like {"1": "placeholder", ...} is usually nested schema data,
    # not the final delegated result.
    if not valid_status and not has_summary and not has_delegate_arrays:
        return 0
    return score


def _iter_json_candidates(text: str) -> Iterable[Tuple[Any, int]]:
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, end = decoder.raw_decode(text[idx:])
        except Exception:
            continue
        yield obj, idx + end


def _select_json_candidate(candidates: Iterable[Tuple[Any, int]]) -> Optional[Any]:
    best_obj: Optional[Any] = None
    best_score = -1
    best_end = -1
    for obj, end in candidates:
        score = _delegate_envelope_score(obj)
        if score <= 0:
            continue
        # Prefer stronger envelopes. For same confidence, prefer the later one:
        # this preserves final-result-after-progress-JSON behavior without
        # allowing low-confidence nested objects to beat a complete envelope.
        if score > best_score or (score == best_score and end >= best_end):
            best_obj = obj
            best_score = score
            best_end = end
    return best_obj


def extract_json_object(text: str) -> Optional[Any]:
    stripped = (text or "").strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except Exception:
        pass

    fence_matches = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    fenced = []
    for candidate in fence_matches:
        try:
            fenced.append((json.loads(candidate), len(candidate)))
        except Exception:
            continue
    selected = _select_json_candidate(fenced)
    if selected is not None:
        return selected

    selected = _select_json_candidate(_iter_json_candidates(stripped))
    if selected is not None:
        return selected

    return None


def coerce_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [ensure_text(item) for item in value]
    return [ensure_text(value)]


def summarize_unstructured_output(raw_output: str, limit: int = 500) -> str:
    text = (raw_output or "").strip()
    if not text:
        return ""
    text = re.sub(r"^```(?:\w+)?\s*|\s*```$", "", text, flags=re.DOTALL).strip()
    for line in text.splitlines():
        candidate = line.strip(" \t`*-_")
        if candidate:
            return candidate[:limit]
    return text[:limit]


def normalize_result(parsed: Any, stdout_path: str, raw_output: str = "") -> Dict[str, Any]:
    if not isinstance(parsed, dict):
        summary = summarize_unstructured_output(raw_output)
        if summary:
            return {
                "status": "ok",
                "summary": summary,
                "artifacts": [],
                "errors": [],
                "next_steps": [],
                "structured": False,
                "error_code": "unstructured_output",
                "raw_output_path": stdout_path,
            }
        return {
            "status": "failed",
            "summary": "Delegated profile returned empty or non-JSON output.",
            "artifacts": [],
            "errors": ["parse_failed"],
            "next_steps": [],
            "structured": False,
            "error_code": "parse_failed",
            "raw_output_path": stdout_path,
        }

    raw_status = ensure_text(parsed.get("status") or "ok").strip().lower()
    errors = coerce_list(parsed.get("errors"))
    if raw_status not in VALID_RESULT_STATUSES:
        errors.append(f"invalid_status:{raw_status or '<empty>'}")
        raw_status = "failed"

    summary = ensure_text(parsed.get("summary") or "")
    result = dict(parsed)
    result.update(
        {
            "status": raw_status,
            "summary": summary,
            "artifacts": coerce_list(parsed.get("artifacts")),
            "errors": errors,
            "next_steps": coerce_list(parsed.get("next_steps")),
            "structured": True,
        }
    )
    if errors and "error_code" not in result:
        result["error_code"] = "target_reported_errors"
    return result


def base_paths(run_dir: Path) -> Dict[str, str]:
    return {
        "run_dir": str(run_dir),
        "request": str(run_dir / "request.json"),
        "status": str(run_dir / "status.json"),
        "prompt": str(run_dir / "prompt.txt"),
        "stdout": str(run_dir / "stdout.txt"),
        "stderr": str(run_dir / "stderr.txt"),
        "approval_events": str(run_dir / "approval_events.jsonl"),
        "worker_stdout": str(run_dir / "worker_stdout.txt"),
        "worker_stderr": str(run_dir / "worker_stderr.txt"),
        "result": str(run_dir / "result.json"),
    }


def split_session_id_footer(text: str) -> Tuple[str, str]:
    lines = (text or "").splitlines()
    idx = len(lines) - 1
    while idx >= 0 and not lines[idx].strip():
        idx -= 1
    if idx < 0:
        return "", ""
    match = re.match(r"^session_id:\s*(\S+)\s*$", lines[idx].strip())
    if not match:
        return (text or "").strip(), ""
    return "\n".join(lines[:idx]).strip(), match.group(1)


def extract_session_id_footer(text: str) -> str:
    return split_session_id_footer(text)[1]


def strip_session_id_footer(text: str) -> str:
    return split_session_id_footer(text)[0]


def _bounded_diagnostic_lines(text: str) -> List[str]:
    lines = [line.strip() for line in strip_session_id_footer(text)[-DIAGNOSTIC_TAIL_CHARS:].splitlines() if line.strip()]
    return lines[-DIAGNOSTIC_TAIL_LINES:]


def classify_transient_failure(
    *, exit_code: Optional[int], timed_out: bool, stdout: str, stderr: str,
    parsed_result: Optional[Dict[str, Any]], stdout_truncated: bool = False,
    stderr_truncated: bool = False,
) -> Optional[str]:
    if timed_out or exit_code in {None, 0, -9, 137}:
        return None
    if isinstance(parsed_result, dict) and ensure_text(parsed_result.get("status")).lower() in VALID_RESULT_STATUSES:
        return None
    lines = _bounded_diagnostic_lines(stdout) + _bounded_diagnostic_lines(stderr)
    joined = "\n".join(lines)
    exclusions = (
        r"\bHTTP\s+(?:400|401|403|404)\b", r"\b(?:quota|billing|credential|invalid model|invalid provider)\b",
        r"\b(?:context length|context window|approval|policy|validation|SIGKILL|out of memory|OOM)\b",
    )
    if any(re.search(pattern, joined, re.I) for pattern in exclusions):
        return None
    for reason, pattern in TRANSIENT_PATTERNS:
        if any(pattern.fullmatch(line) for line in lines):
            return reason
    return None


def build_recovery_prompt(attempt_number: int) -> str:
    prompt = (
        "The previous delegated run ended because of a transient connection or stream failure.\n"
        "Continue exactly where you left off in this same session. Do not restart the original task or repeat work/actions already completed.\n"
        "Finish the original task and return the requested final JSON result.\n"
    )
    if attempt_number >= 3:
        prompt += "This is the final automatic recovery attempt.\n"
    return prompt


def rename_session(hermes_bin: str, profile: str, session_id: str, title: str, cwd: Path, env: Dict[str, str], timeout: int = 30) -> Dict[str, Any]:
    if not session_id:
        return {"session_renamed": False, "rename_error": "child_session_id_missing"}
    cmd = [hermes_bin, "-p", profile, "sessions", "rename", session_id, title]
    completed = subprocess.run(cmd, cwd=str(cwd), env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    return {
        "session_renamed": completed.returncode == 0,
        "rename_exit_code": completed.returncode,
        "rename_error": None if completed.returncode == 0 else (completed.stderr or completed.stdout).strip()[:500],
    }


def child_environment(parent_depth: int, child_approval_mode: str = DEFAULT_CHILD_APPROVAL_MODE) -> Dict[str, str]:
    mode = coerce_child_approval_mode(child_approval_mode)
    env = os.environ.copy()
    env["PROFILE_DELEGATE_DEPTH"] = str(parent_depth + 1)

    # The delegated Hermes subprocess is intentionally non-interactive: there
    # is no approval callback wired for the child process, and inheriting the
    # caller gateway/session env makes tools like execute_code emit approval
    # prompts back to the user instead of just completing the bounded run.
    for key in list(env):
        if key.startswith("HERMES_SESSION_") or key in {
            "HERMES_GATEWAY_SESSION",
            "HERMES_EXEC_ASK",
            "HERMES_INTERACTIVE",
            "HERMES_CRON_SESSION",
            "HERMES_YOLO_MODE",
            "HERMES_ACCEPT_HOOKS",
        }:
            env.pop(key, None)

    if mode == "approve_yolo":
        # Explicit trusted mode: match Hermes -z/script semantics.
        env["HERMES_YOLO_MODE"] = "1"
        env["HERMES_ACCEPT_HOOKS"] = "1"
    # Approval is owned by child_bootstrap.py in both modes. Do not simulate a
    # cron run: quiet chat may re-enable interactivity, and cron state is not an
    # approval contract for delegated subprocesses.
    return env


def _make_profile_delegate_summary(result: Dict[str, Any], paths: Dict[str, str]) -> str:
    payload = {
        "status": result.get("status"),
        "summary": result.get("summary", ""),
        "artifacts": result.get("artifacts", []),
        "errors": result.get("errors", []),
        "next_steps": result.get("next_steps", []),
        "session_id": result.get("session_id", ""),
        "paths": paths,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    limit = env_int("PROFILE_DELEGATE_NOTIFY_MAX_SUMMARY_CHARS", 4000, 500, 50000)
    return text[:limit] + ("\n…[truncated]" if len(text) > limit else "")


def _push_profile_delegate_completion(run_dir: Path, final: Dict[str, Any]) -> None:
    """Best-effort notify-on-complete via Hermes' native async-delegation queue."""
    try:
        status = read_json_file(run_dir / "status.json")
        request = read_json_file(run_dir / "request.json")
        if not bool(request.get("notify_on_complete", True)):
            status["notification_status"] = "disabled"
            json_safe_write(run_dir / "status.json", status)
            return
        session_key = str(request.get("origin_session_key") or "").strip()
        if not session_key:
            status["notification_status"] = "skipped_no_origin_session_key"
            json_safe_write(run_dir / "status.json", status)
            return
        result = final.get("result") if isinstance(final.get("result"), dict) else {}
        paths = final.get("paths") if isinstance(final.get("paths"), dict) else base_paths(run_dir)
        from tools.process_registry import process_registry
        completed_at = time.time()
        dispatched_at = float(request.get("dispatched_at_epoch") or completed_at)
        evt_status = "completed" if final.get("success") else "error"
        evt = {
            "type": "async_delegation",
            "delegation_id": request.get("task_id", run_dir.name),
            "session_key": session_key,
            "goal": f"profile_delegate to {request.get('profile')}: {request.get('session_title')}",
            "context": (
                f"Profile Delegate task_id={request.get('task_id', run_dir.name)}; "
                f"run_dir={run_dir}; session_mode={request.get('session_mode', 'new')}"
            ),
            "toolsets": ["profile_delegate"],
            "role": "profile",
            "model": request.get("profile"),
            "status": evt_status,
            "summary": _make_profile_delegate_summary(result, paths),
            "error": final.get("error_code") or result.get("error_code"),
            "api_calls": 0,
            "duration_seconds": round(completed_at - dispatched_at, 2),
            "dispatched_at": dispatched_at,
            "completed_at": completed_at,
            "exit_reason": final.get("status"),
        }
        process_registry.completion_queue.put(evt)
        status["notified_at"] = now_iso()
        status["notification_status"] = "queued"
        json_safe_write(run_dir / "status.json", status)
    except Exception as exc:
        try:
            status = read_json_file(run_dir / "status.json")
            status["notification_status"] = "failed"
            status["notification_error"] = f"{type(exc).__name__}: {exc}"[:500]
            json_safe_write(run_dir / "status.json", status)
        except Exception:
            pass


def _execute_delegate_run(run_dir: Path) -> Dict[str, Any]:
    request = read_json_file(run_dir / "request.json")
    status = read_json_file(run_dir / "status.json")
    profile = ensure_text(request.get("profile"))
    timeout = int(request.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)
    cwd = Path(ensure_text(request.get("workdir"))).resolve()
    hermes_bin = ensure_text(request.get("hermes_bin"))
    mode = ensure_text(request.get("session_mode") or "new")
    resume_id = ensure_text(request.get("requested_session_id") or "")
    title_text = ensure_text(request.get("session_title") or "")
    depth = int(request.get("delegate_depth") or 0)
    child_approval_mode = coerce_child_approval_mode(request.get("child_approval_mode", DEFAULT_CHILD_APPROVAL_MODE))
    env = child_environment(depth, child_approval_mode)
    requested_execution = request.get("effective_execution") or request.get("requested_execution") or {}
    reasoning_effort = requested_execution.get("reasoning_effort")
    if reasoning_effort:
        profile_home = Path(ensure_text(request.get("profile_home"))).resolve()
        existing_managed_dir = discover_managed_scope(env)
        if existing_managed_dir is not None:
            raise ProfileDelegateError(f"reasoning_effort cannot replace existing Hermes managed scope: {existing_managed_dir}", "reasoning_managed_scope_conflict")
        env["HERMES_HOME"] = str(profile_home)
        env["HERMES_MANAGED_DIR"] = str(prepare_reasoning_config(run_dir, ensure_text(reasoning_effort)))

    deadline = time.monotonic() + timeout
    max_resumes = env_int("PROFILE_DELEGATE_MAX_TRANSIENT_RESUMES", DEFAULT_MAX_TRANSIENT_RESUMES, 0, 2)
    history: List[Dict[str, Any]] = []
    stable_session_id = resume_id
    run_meta: Dict[str, Any] = {}
    exit_code: Optional[int] = None
    timed_out = False
    integrity_error = ""

    with acquire_concurrency_slot() as slot:
        status["concurrency_slot"] = slot.slot
        json_safe_write(run_dir / "status.json", status)
        for attempt_index in range(max_resumes + 1):
            attempt = attempt_index + 1
            remaining = int(deadline - time.monotonic())
            if remaining < 1:
                timed_out = True
                break
            prompt_path = run_dir / ("prompt.txt" if attempt == 1 else f"recovery_prompt_{attempt}.txt")
            if attempt > 1:
                text_safe_write(prompt_path, build_recovery_prompt(attempt))
            stdout_path = run_dir / ("stdout.txt" if attempt == 1 else f"attempt_{attempt}_stdout.txt")
            stderr_path = run_dir / ("stderr.txt" if attempt == 1 else f"attempt_{attempt}_stderr.txt")
            cmd = build_child_command(request, run_dir, prompt_path=prompt_path, resume_session_id=stable_session_id if attempt > 1 else None)
            started = time.monotonic()
            run_meta = run_capped_subprocess(cmd, cwd=cwd, env=env, timeout=remaining, stdout_path=stdout_path, stderr_path=stderr_path)
            exit_code = run_meta["exit_code"]
            timed_out = bool(run_meta["timed_out"])
            stdout_attempt = tail_text(stdout_path, run_meta["stdout_limit"])
            stderr_attempt = tail_text(stderr_path, run_meta["stderr_limit"])
            footer_id = extract_session_id_footer(stdout_attempt) or extract_session_id_footer(stderr_attempt)
            if footer_id:
                if stable_session_id and footer_id != stable_session_id:
                    integrity_error = "resume_session_mismatch"
                else:
                    stable_session_id = footer_id
            parsed_attempt = extract_json_object(strip_session_id_footer(stdout_attempt))
            transient = None if integrity_error else classify_transient_failure(
                exit_code=exit_code, timed_out=timed_out,
                stdout=run_meta.get("stdout_diagnostic_tail", stdout_attempt),
                stderr=run_meta.get("stderr_diagnostic_tail", stderr_attempt),
                parsed_result=parsed_attempt,
                stdout_truncated=bool(run_meta.get("stdout_truncated")),
                stderr_truncated=bool(run_meta.get("stderr_truncated")),
            )
            history.append({"attempt": attempt, "exit_code": exit_code, "timed_out": timed_out, "transient_reason": transient, "session_id": stable_session_id, "duration_seconds": round(time.monotonic() - started, 3), "stdout": str(stdout_path), "stderr": str(stderr_path)})
            if integrity_error or not transient or attempt_index >= max_resumes:
                break
            if not stable_session_id:
                integrity_error = "transient_resume_session_missing"
                break
            if deadline - time.monotonic() < TRANSIENT_RESUME_DELAY_SECONDS + 10:
                integrity_error = "transient_resume_budget_exhausted"
                break
            time.sleep(TRANSIENT_RESUME_DELAY_SECONDS)

    if history and history[-1]["attempt"] > 1:
        shutil.copyfile(history[-1]["stdout"], run_dir / "stdout.txt")
        shutil.copyfile(history[-1]["stderr"], run_dir / "stderr.txt")
    stdout = tail_text(run_dir / "stdout.txt", int(run_meta.get("stdout_limit", DEFAULT_MAX_STDOUT_CHARS)))
    stderr = tail_text(run_dir / "stderr.txt", int(run_meta.get("stderr_limit", DEFAULT_MAX_STDERR_CHARS)))
    parse_stdout = strip_session_id_footer(stdout)
    approval_timeout_marker = next((marker for marker in APPROVAL_TIMEOUT_MARKERS if marker in stdout or marker in stderr), None)

    if timed_out:
        error_code, final_status = "timeout", "timed_out"
        result = {"status": "failed", "summary": f"Delegated profile timed out after {timeout} seconds.", "artifacts": [], "errors": ["timeout"], "next_steps": [], "structured": True, "error_code": error_code}
    elif integrity_error:
        error_code, final_status = integrity_error, "failed"
        result = {"status": "failed", "summary": f"Automatic recovery stopped safely: {integrity_error}.", "artifacts": [], "errors": [integrity_error], "next_steps": [], "structured": True, "error_code": error_code}
    elif approval_timeout_marker:
        error_code, final_status = "approval_timeout", "failed"
        result = {"status": "failed", "summary": "Delegated child reached an approval timeout.", "artifacts": [str(run_dir / "approval_events.jsonl")], "errors": ["approval_timeout_marker"], "next_steps": [], "structured": True, "error_code": error_code}
    else:
        result = normalize_result(extract_json_object(parse_stdout), str(run_dir / "stdout.txt"), raw_output=parse_stdout)
        error_code = result.get("error_code") if isinstance(result.get("error_code"), str) else None
        if exit_code != 0:
            result["status"] = "failed"
            result["errors"] = coerce_list(result.get("errors")) + [f"hermes_exit_code_{exit_code}"]
            error_code = "transient_resume_exhausted" if history and history[-1].get("transient_reason") else "nonzero_exit"
            result["error_code"] = error_code
        final_status = "completed" if exit_code == 0 else "failed"

    child_session_id = stable_session_id
    rename_meta: Dict[str, Any] = {"session_renamed": False}
    if mode == "new" and final_status == "completed" and result.get("status") != "failed":
        remaining = int(deadline - time.monotonic())
        if remaining >= 1:
            try:
                rename_meta = rename_session(hermes_bin, profile, child_session_id, title_text, cwd, env, timeout=min(30, remaining))
            except Exception as exc:
                rename_meta = {"session_renamed": False, "rename_error": f"{type(exc).__name__}: {exc}"}
        else:
            rename_meta["rename_skipped"] = "deadline_exhausted"
    if child_session_id:
        result["session_id"] = child_session_id
    result.update({"requested_execution": request.get("requested_execution") or {}, "effective_execution": request.get("effective_execution") or {}, "effective_capabilities": request.get("effective_capabilities") or {}, "approval_policy": request.get("approval_policy") or {}, "recovery_history": history})
    json_safe_write(run_dir / "result.json", result)
    status.update({"status": final_status, "ended_at": now_iso(), "exit_code": exit_code, "timed_out": timed_out, "error_code": error_code, "stdout_truncated": bool(run_meta.get("stdout_truncated")), "stderr_truncated": bool(run_meta.get("stderr_truncated")), "stdout_chars": run_meta.get("stdout_chars"), "stderr_chars": run_meta.get("stderr_chars"), "stdout_limit": run_meta.get("stdout_limit"), "stderr_limit": run_meta.get("stderr_limit"), "child_session_id": child_session_id, "recovery_history": history, **rename_meta})
    json_safe_write(run_dir / "status.json", status)
    return {"success": final_status == "completed" and result.get("status") != "failed", "mode": "sync", "task_id": request.get("task_id", run_dir.name), "profile": profile, "status": final_status, "error_code": error_code, "session_title": title_text, "session_mode": mode, "requested_session_id": resume_id, "child_approval_mode": child_approval_mode, "requested_execution": request.get("requested_execution") or {}, "effective_execution": request.get("effective_execution") or {}, "effective_capabilities": request.get("effective_capabilities") or {}, "approval_policy": request.get("approval_policy") or {}, "child_session_id": child_session_id, "recovery_history": history, **rename_meta, "result": result, "paths": base_paths(run_dir), "exit_code": exit_code, "timed_out": timed_out, "stdout_truncated": run_meta.get("stdout_truncated"), "stderr_truncated": run_meta.get("stderr_truncated")}


_async_lock = threading.Lock()
_async_running = 0


def _mark_background_worker_failure(run_dir: Path, exc: Exception) -> Dict[str, Any]:
    code = getattr(exc, "code", "background_worker_error")
    result = {
        "status": "failed",
        "summary": f"Profile Delegate background worker failed: {type(exc).__name__}: {exc}",
        "artifacts": [],
        "errors": [f"{type(exc).__name__}: {exc}"],
        "next_steps": [],
        "structured": True,
        "error_code": code,
    }
    json_safe_write(run_dir / "result.json", result)
    try:
        status = read_json_file(run_dir / "status.json")
    except Exception:
        status = {"task_id": run_dir.name}
    status.update({"status": "failed", "ended_at": now_iso(), "error_code": code})
    json_safe_write(run_dir / "status.json", status)
    return {"success": False, "mode": "async", "task_id": run_dir.name, "status": "failed", "error_code": code, "result": result, "paths": base_paths(run_dir)}


def _background_mode() -> str:
    mode = os.getenv("PROFILE_DELEGATE_BACKGROUND_MODE", "detached").strip().lower()
    if mode in {"thread", "inprocess", "in-process"}:
        return "thread"
    return "detached"


def _start_background_thread(run_dir: Path) -> None:
    global _async_running
    max_async = env_int("PROFILE_DELEGATE_MAX_ASYNC", DEFAULT_MAX_ASYNC, 1, 20)
    with _async_lock:
        if _async_running >= max_async:
            raise ProfileDelegateError(
                f"profile_delegate background capacity reached ({max_async} running)",
                "async_concurrency_limit",
            )
        _async_running += 1

    def _worker() -> None:
        global _async_running
        final: Dict[str, Any]
        try:
            final = _execute_delegate_run(run_dir)
            final["mode"] = "async"
        except Exception as exc:
            final = _mark_background_worker_failure(run_dir, exc)
        try:
            _push_profile_delegate_completion(run_dir, final)
        finally:
            with _async_lock:
                _async_running = max(0, _async_running - 1)

    thread = threading.Thread(target=_worker, name=f"profile-delegate-{run_dir.name}", daemon=True)
    thread.start()


def _start_detached_background_worker(run_dir: Path) -> None:
    """Start a durable worker process that owns the child Hermes subprocess.

    Gateway/model-call processes may finish or restart while a delegated profile
    keeps running. A daemon thread in that short-lived process can leave the
    child Hermes session alive but stop updating status.json/result.json. The
    detached worker makes the run artifact itself the source of truth.
    """
    stdout_path = run_dir / "worker_stdout.txt"
    stderr_path = run_dir / "worker_stderr.txt"
    text_safe_write(stdout_path, "")
    text_safe_write(stderr_path, "")
    cmd = [sys.executable, str(Path(__file__).resolve()), "--background-worker", str(run_dir)]
    env = os.environ.copy()
    with stdout_path.open("a", encoding="utf-8") as out, stderr_path.open("a", encoding="utf-8") as err:
        proc = subprocess.Popen(
            cmd,
            cwd=str(Path.cwd()),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            close_fds=True,
            start_new_session=True,
        )
    status = read_json_file(run_dir / "status.json")
    status.update(
        {
            "background_worker_mode": "detached",
            "worker_pid": proc.pid,
            "worker_started_at": now_iso(),
            "worker_stdout": str(stdout_path),
            "worker_stderr": str(stderr_path),
        }
    )
    json_safe_write(run_dir / "status.json", status)

    def _watch_for_notification() -> None:
        try:
            proc.wait()
            status_after = read_json_file(run_dir / "status.json")
            result_after = read_json_file(run_dir / "result.json") if (run_dir / "result.json").exists() else {}
            final_status = str(status_after.get("status") or "unknown")
            final = {
                "success": final_status == "completed" and result_after.get("status") != "failed",
                "mode": "async",
                "task_id": run_dir.name,
                "status": final_status,
                "error_code": status_after.get("error_code") or result_after.get("error_code"),
                "result": result_after,
                "paths": base_paths(run_dir),
            }
            _push_profile_delegate_completion(run_dir, final)
        except Exception:
            # Artifact persistence is owned by the detached worker; notification is best effort.
            pass

    threading.Thread(target=_watch_for_notification, name=f"profile-delegate-notify-{run_dir.name}", daemon=True).start()


def _start_background_run(run_dir: Path) -> None:
    if _background_mode() == "thread":
        _start_background_thread(run_dir)
    else:
        _start_detached_background_worker(run_dir)


def _background_worker_main(run_dir_arg: str) -> int:
    run_dir = Path(run_dir_arg).expanduser().resolve()
    try:
        final = _execute_delegate_run(run_dir)
        final["mode"] = "async"
        try:
            status = read_json_file(run_dir / "status.json")
            if bool(status.get("notify_on_complete", True)) and not status.get("notification_status"):
                status["notification_status"] = "detached_worker_completed_no_live_queue"
                json_safe_write(run_dir / "status.json", status)
        except Exception:
            pass
        return 0
    except Exception as exc:
        _mark_background_worker_failure(run_dir, exc)
        return 1


def delegate_profile(
    profile: str,
    task: str,
    context: str = "",
    timeout_seconds: Any = DEFAULT_TIMEOUT_SECONDS,
    output_contract: str = "",
    workdir: str = "",
    session_title: str = "",
    session_mode: str = "new",
    session_id: str = "",
    background: bool = False,
    notify_on_complete: bool = True,
    origin_session_key: str = "",
    origin: Optional[Dict[str, Any]] = None,
    child_approval_mode: Any = None,
    model: Any = None,
    provider: Any = None,
    reasoning_effort: Any = None,
    max_turns: Any = None,
    toolsets: Any = None,
    skills: Any = None,
    capability_preset: Any = DEFAULT_CAPABILITY_PRESET,
) -> Dict[str, Any]:
    depth, max_depth = enforce_depth_policy()
    validated = validate_profile(profile)
    task_text = bounded_text("task", task, MAX_TASK_CHARS).strip()
    if not task_text:
        raise ProfileDelegateError("task must be non-empty", "validation_error")
    context_text = bounded_text("context", context, MAX_CONTEXT_CHARS)
    contract_text = bounded_text("output_contract", output_contract, MAX_OUTPUT_CONTRACT_CHARS)
    title_text = normalize_session_title(session_title)
    mode = coerce_session_mode(session_mode)
    resume_id = validate_session_id(session_id, required=(mode == "resume"))
    resolved_child_approval_mode = coerce_child_approval_mode(
        child_approval_mode if child_approval_mode not in {None, ""} else plugin_config_child_approval_mode()
    )
    timeout = coerce_timeout(timeout_seconds)
    requested_execution = normalize_requested_execution(
        model=model, provider=provider, reasoning_effort=reasoning_effort,
        max_turns=max_turns, toolsets=toolsets, skills=skills,
    )
    effective_execution, effective_capabilities = resolve_capability_preset(
        capability_preset, requested_execution
    )
    if requested_execution["reasoning_effort"] and validated.canonical == "default":
        raise ProfileDelegateError(
            "reasoning_effort override is not supported for the default profile",
            "validation_error",
        )
    cwd = resolve_workdir(workdir)
    hermes_bin = resolve_hermes_bin()
    normalized_origin = normalize_origin(origin, origin_session_key)
    normalized_origin_session_key = normalized_origin["session_key"]

    task_id = make_task_id()
    run_dir = get_runs_root() / task_id
    run_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    chmod_best_effort(run_dir, 0o700)

    prompt = build_prompt(task_text, context_text, contract_text)
    request = {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "task_id": task_id,
        "profile": validated.canonical,
        "requested_profile": validated.requested,
        "profile_home": validated.home,
        "created_at": now_iso(),
        "dispatched_at_epoch": time.time(),
        "timeout_seconds": timeout,
        "workdir": str(cwd),
        "task_chars": len(task_text),
        "context_chars": len(context_text),
        "output_contract_chars": len(contract_text),
        "session_title": title_text,
        "session_mode": mode,
        "requested_session_id": resume_id,
        "runs_root": str(get_runs_root()),
        "hermes_bin": hermes_bin,
        "delegate_depth": depth,
        "delegate_max_depth": max_depth,
        "child_approval_mode": resolved_child_approval_mode,
        "approval_policy": {
            "requested": ensure_text(child_approval_mode) or "config/default",
            "effective": resolved_child_approval_mode,
            "owner": "profile-delegate-child-bootstrap",
            "interactive": False,
        },
        "capability_preset": effective_capabilities["preset"],
        "effective_capabilities": effective_capabilities,
        "requested_execution": requested_execution,
        "effective_execution": effective_execution,
        "background": bool(background),
        "notify_on_complete": bool(notify_on_complete),
        "origin": normalized_origin,
        "origin_session_key": normalized_origin_session_key,
    }
    status = {
        **request,
        "status": "running",
        "started_at": now_iso(),
        "ended_at": None,
        "exit_code": None,
        "error_code": None,
        "concurrency_slot": None,
        "notified_at": None,
        "notification_status": None,
    }

    json_safe_write(run_dir / "request.json", {**request, "task": task_text, "context": context_text, "output_contract": contract_text})
    text_safe_write(run_dir / "prompt.txt", prompt)
    json_safe_write(run_dir / "status.json", status)
    text_safe_write(run_dir / "stdout.txt", "")
    text_safe_write(run_dir / "stderr.txt", "")

    if background:
        try:
            _start_background_run(run_dir)
        except ProfileDelegateError as exc:
            status.update({"status": "failed", "ended_at": now_iso(), "error_code": exc.code})
            json_safe_write(run_dir / "status.json", status)
            json_safe_write(run_dir / "result.json", {
                "status": "failed",
                "summary": str(exc),
                "artifacts": [],
                "errors": [exc.code],
                "next_steps": ["Wait for another background profile_delegate run to finish or raise PROFILE_DELEGATE_MAX_ASYNC."],
                "structured": True,
                "error_code": exc.code,
            })
            raise
        except Exception as exc:
            status.update({"status": "failed", "ended_at": now_iso(), "error_code": "background_start_failed"})
            json_safe_write(run_dir / "status.json", status)
            json_safe_write(run_dir / "result.json", {
                "status": "failed",
                "summary": f"Failed to start background profile_delegate run: {type(exc).__name__}: {exc}",
                "artifacts": [],
                "errors": ["background_start_failed"],
                "next_steps": [],
                "structured": True,
                "error_code": "background_start_failed",
            })
            raise ProfileDelegateError(f"failed to start background run: {type(exc).__name__}: {exc}", "background_start_failed") from exc
        return {
            "success": True,
            "mode": "async",
            "task_id": task_id,
            "profile": validated.canonical,
            "status": "running",
            "error_code": None,
            "session_title": title_text,
            "session_mode": mode,
            "requested_session_id": resume_id,
            "child_approval_mode": resolved_child_approval_mode,
            "requested_execution": requested_execution,
            "effective_execution": effective_execution,
            "effective_capabilities": effective_capabilities,
            "approval_policy": request["approval_policy"],
            "notify_on_complete": bool(notify_on_complete),
            "origin_session_key_present": bool(normalized_origin_session_key),
            "paths": base_paths(run_dir),
        }

    final = _execute_delegate_run(run_dir)
    final["notify_on_complete"] = False
    return final

def resolve_run_dir(task_id: str) -> Path:
    if not isinstance(task_id, str) or not task_id.strip():
        raise ProfileDelegateError("task_id must be a non-empty string", "validation_error")
    clean = task_id.strip()
    if not re.fullmatch(r"pd_\d{8}_\d{6}_[a-z0-9]{6,12}", clean):
        raise ProfileDelegateError("invalid task_id format", "validation_error")
    run_dir = (get_runs_root() / clean).resolve()
    root = get_runs_root().resolve()
    try:
        run_dir.relative_to(root)
    except ValueError as exc:
        raise ProfileDelegateError("task_id escapes runs root", "validation_error") from exc
    if not run_dir.is_dir():
        raise ProfileDelegateError(f"run not found: {clean}", "run_not_found")
    return run_dir


def profile_delegate_status(
    task_id: str,
    tail_chars: Any = 4000,
    caller_origin: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    run_dir = resolve_run_dir(task_id)
    try:
        max_tail = max(0, min(int(tail_chars or 4000), 20_000))
    except Exception as exc:
        raise ProfileDelegateError("tail_chars must be an integer", "validation_error") from exc
    status = read_json_file(run_dir / "status.json")
    result = read_json_file(run_dir / "result.json") if (run_dir / "result.json").exists() else None
    persisted_origin = normalize_persisted_origin(status)
    normalized_caller = normalize_origin(caller_origin)
    belongs, matched_by = origin_match(persisted_origin, normalized_caller, "current_session")
    caller_available = any(normalized_caller.values())
    run_available = any(persisted_origin.values())
    ownership: Optional[bool] = belongs if caller_available and run_available and matched_by else None
    activity = derive_activity(status)
    return {
        "success": True,
        "task_id": status.get("task_id", task_id),
        "profile": status.get("profile"),
        "session_title": status.get("session_title"),
        "status": status.get("status", "unknown"),
        "error_code": status.get("error_code"),
        "exit_code": status.get("exit_code"),
        "timed_out": bool(status.get("timed_out", False)),
        "stdout_truncated": bool(status.get("stdout_truncated", False)),
        "stderr_truncated": bool(status.get("stderr_truncated", False)),
        "created_at": status.get("created_at"),
        "started_at": status.get("started_at"),
        "ended_at": status.get("ended_at"),
        "requested_execution": status.get("requested_execution") or {},
        "origin": persisted_origin,
        "belongs_to_current_session": ownership,
        "origin_match_by": matched_by,
        "background_worker_mode": status.get("background_worker_mode"),
        "worker_pid": status.get("worker_pid"),
        "worker_alive": activity["worker_alive"],
        "activity": activity["activity"],
        "notification_status": status.get("notification_status"),
        "result": result,
        "stdout_tail": tail_text(run_dir / "stdout.txt", max_tail),
        "stderr_tail": tail_text(run_dir / "stderr.txt", max_tail),
        "paths": base_paths(run_dir),
    }


def iter_run_dirs() -> Iterable[Path]:
    root = get_runs_root()
    if not root.exists():
        return []
    return sorted((p for p in root.iterdir() if p.is_dir() and p.name.startswith("pd_")), key=lambda p: p.name, reverse=True)


def profile_delegate_list(
    limit: Any = 20,
    scope: str = "current_session",
    statuses: Optional[List[str]] = None,
    profile: str = "",
    caller_origin: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        max_items = max(1, min(int(limit or 20), 100))
    except Exception as exc:
        raise ProfileDelegateError("limit must be an integer", "validation_error") from exc
    requested_scope = ensure_text(scope or "current_session").strip().lower()
    if requested_scope not in VALID_INSPECTION_SCOPES:
        raise ProfileDelegateError(
            "scope must be one of: current_session, current_lane, all",
            "validation_error",
        )
    if statuses is None:
        normalized_statuses: Optional[set[str]] = None
    elif not isinstance(statuses, list):
        raise ProfileDelegateError("status must be an array", "validation_error")
    else:
        normalized_statuses = {ensure_text(item).strip().lower() for item in statuses}
        if normalized_statuses - VALID_RUN_STATUSES:
            raise ProfileDelegateError(
                "status entries must be one of: running, completed, failed, corrupt",
                "validation_error",
            )
    profile_filter = ensure_text(profile).strip()
    normalized_caller = normalize_origin(caller_origin)
    required_caller_field = (
        "session_key"
        if requested_scope == "current_lane" and normalized_caller["session_key"]
        else None
    )
    if requested_scope == "current_session":
        required_caller_field = next(
            (field for field in ("ui_session_id", "session_id", "session_key") if normalized_caller[field]),
            None,
        )
    if requested_scope != "all" and not required_caller_field:
        return {
            "success": True,
            "runs_root": str(get_runs_root()),
            "scope_requested": requested_scope,
            "scope_effective": "unresolved",
            "origin_match_by": None,
            "warning": "current caller origin is unavailable; pass scope='all' explicitly for global inspection",
            "count": 0,
            "runs": [],
        }

    runs = []
    match_by_values: set[str] = set()
    for run_dir in iter_run_dirs():
        try:
            status = read_json_file(run_dir / "status.json")
        except ProfileDelegateError:
            status = {"task_id": run_dir.name, "status": "corrupt"}
        lifecycle = ensure_text(status.get("status") or "corrupt").strip().lower()
        if normalized_statuses is not None and lifecycle not in normalized_statuses:
            continue
        if profile_filter and ensure_text(status.get("profile")).strip() != profile_filter:
            continue
        persisted_origin = normalize_persisted_origin(status)
        matches, matched_by = origin_match(persisted_origin, normalized_caller, requested_scope)
        if not matches:
            continue
        if matched_by:
            match_by_values.add(matched_by)
        activity = derive_activity(status)
        runs.append(
            {
                "task_id": status.get("task_id", run_dir.name),
                "profile": status.get("profile"),
                "session_title": status.get("session_title"),
                "status": lifecycle,
                "activity": activity["activity"],
                "worker_alive": activity["worker_alive"],
                "error_code": status.get("error_code"),
                "created_at": status.get("created_at"),
                "ended_at": status.get("ended_at"),
                "origin": persisted_origin,
                "run_dir": str(run_dir),
            }
        )
        if len(runs) >= max_items:
            break
    origin_match_by = None
    if len(match_by_values) == 1:
        origin_match_by = next(iter(match_by_values))
    elif requested_scope != "all":
        origin_match_by = required_caller_field
    return {
        "success": True,
        "runs_root": str(get_runs_root()),
        "scope_requested": requested_scope,
        "scope_effective": requested_scope,
        "origin_match_by": origin_match_by,
        "count": len(runs),
        "runs": runs,
    }


def profile_delegate_prune(max_age_days: Any = 14, dry_run: bool = True) -> Dict[str, Any]:
    try:
        days = int(max_age_days if max_age_days is not None else 14)
    except Exception as exc:
        raise ProfileDelegateError("max_age_days must be an integer", "validation_error") from exc
    if days < 1:
        raise ProfileDelegateError("max_age_days must be >= 1", "validation_error")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    candidates = []
    for run_dir in iter_run_dirs():
        created = None
        status_path = run_dir / "status.json"
        if status_path.exists():
            try:
                created = parse_iso(read_json_file(status_path).get("created_at", ""))
            except ProfileDelegateError:
                created = None
        if created is None:
            created = datetime.fromtimestamp(run_dir.stat().st_mtime, timezone.utc)
        if created < cutoff:
            candidates.append(str(run_dir))

    if not dry_run:
        for item in candidates:
            shutil.rmtree(item, ignore_errors=False)
    return {
        "success": True,
        "dry_run": bool(dry_run),
        "max_age_days": days,
        "runs_root": str(get_runs_root()),
        "matched_count": len(candidates),
        "removed_count": 0 if dry_run else len(candidates),
        "runs": candidates,
    }


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--background-worker":
        raise SystemExit(_background_worker_main(sys.argv[2]))
    print("Usage: python core.py --background-worker <run_dir>", file=sys.stderr)
    raise SystemExit(2)
