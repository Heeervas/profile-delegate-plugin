"""Profile Delegate core. Usage: imported by plugin; delegates bounded tasks to Hermes profiles."""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import string
import selectors
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:  # Unix-only; Hermes currently targets Linux/macOS/WSL for this plugin.
    import fcntl
except Exception:  # pragma: no cover - Windows fallback is conservative.
    fcntl = None  # type: ignore[assignment]

DEFAULT_TIMEOUT_SECONDS = 240
MAX_TIMEOUT_SECONDS = 900
MAX_TASK_CHARS = 30_000
MAX_CONTEXT_CHARS = 60_000
MAX_OUTPUT_CONTRACT_CHARS = 8_000
MAX_SESSION_TITLE_CHARS = 50
MAX_SESSION_ID_CHARS = 200
DEFAULT_MAX_STDOUT_CHARS = 200_000
DEFAULT_MAX_STDERR_CHARS = 100_000
DEFAULT_MAX_DEPTH = 1
DEFAULT_MAX_CONCURRENT = 1
VALID_RESULT_STATUSES = {"ok", "blocked", "failed"}
VALID_SESSION_MODES = {"new", "resume"}
TRUTHY = {"1", "true", "yes", "on"}


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
    if timeout > MAX_TIMEOUT_SECONDS:
        raise ProfileDelegateError(f"timeout_seconds must be <= {MAX_TIMEOUT_SECONDS}", "validation_error")
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
    mode = str(value or "new").strip().lower()
    if mode not in VALID_SESSION_MODES:
        raise ProfileDelegateError("session_mode must be 'new' or 'resume'", "validation_error")
    return mode


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

    with subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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
                proc.kill()
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
- Your session id is available in your system prompt because --pass-session-id is used. Include it in the JSON as "session_id" when possible.

Task:
{task.strip()}

Caller-provided context:
{context_block}

Additional output contract:
{contract}
"""


def extract_json_object(text: str) -> Optional[Any]:
    stripped = (text or "").strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except Exception:
        pass

    fence_matches = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    for candidate in reversed(fence_matches):
        try:
            return json.loads(candidate)
        except Exception:
            continue

    decoder = json.JSONDecoder()
    candidates = []
    for idx, ch in enumerate(stripped):
        if ch != "{":
            continue
        try:
            obj, _end = decoder.raw_decode(stripped[idx:])
            candidates.append(obj)
        except Exception:
            continue
    return candidates[-1] if candidates else None


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
        "result": str(run_dir / "result.json"),
    }


def extract_session_id(result: Dict[str, Any]) -> str:
    for key in ("session_id", "child_session_id"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


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


def child_environment(parent_depth: int) -> Dict[str, str]:
    env = os.environ.copy()
    env["PROFILE_DELEGATE_DEPTH"] = str(parent_depth + 1)
    return env


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
    timeout = coerce_timeout(timeout_seconds)
    cwd = resolve_workdir(workdir)
    hermes_bin = resolve_hermes_bin()

    task_id = make_task_id()
    run_dir = get_runs_root() / task_id
    run_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    chmod_best_effort(run_dir, 0o700)

    prompt = build_prompt(task_text, context_text, contract_text)
    request = {
        "task_id": task_id,
        "profile": validated.canonical,
        "requested_profile": validated.requested,
        "profile_home": validated.home,
        "created_at": now_iso(),
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
    }
    status = {
        **request,
        "status": "running",
        "started_at": now_iso(),
        "ended_at": None,
        "exit_code": None,
        "error_code": None,
        "concurrency_slot": None,
    }

    json_safe_write(run_dir / "request.json", {**request, "task": task_text, "context": context_text, "output_contract": contract_text})
    text_safe_write(run_dir / "prompt.txt", prompt)
    json_safe_write(run_dir / "status.json", status)

    # Pass the delegated prompt by file reference instead of argv. The argv is
    # visible to local process listings on many systems; prompt text may contain
    # private task context. Hermes expands @file:<path> inside the child process.
    cmd = [hermes_bin, "-p", validated.canonical]
    if mode == "resume":
        cmd += ["--resume", resume_id]
    cmd += ["--pass-session-id", "-z", f"@file:{run_dir / 'prompt.txt'}"]
    env = child_environment(depth)

    with acquire_concurrency_slot() as slot:
        status["concurrency_slot"] = slot.slot
        json_safe_write(run_dir / "status.json", status)
        run_meta = run_capped_subprocess(
            cmd,
            cwd=cwd,
            env=env,
            timeout=timeout,
            stdout_path=run_dir / "stdout.txt",
            stderr_path=run_dir / "stderr.txt",
        )
        exit_code = run_meta["exit_code"]
        timed_out = bool(run_meta["timed_out"])

    stdout = tail_text(run_dir / "stdout.txt", run_meta["stdout_limit"])
    stderr = tail_text(run_dir / "stderr.txt", run_meta["stderr_limit"])

    if timed_out:
        result = {
            "status": "failed",
            "summary": f"Delegated profile timed out after {timeout} seconds.",
            "artifacts": [],
            "errors": ["timeout"],
            "next_steps": ["Retry with a smaller task or larger timeout_seconds."],
            "structured": True,
            "error_code": "timeout",
        }
        final_status = "timed_out"
        error_code = "timeout"
    else:
        parsed = extract_json_object(stdout)
        result = normalize_result(parsed, str(run_dir / "stdout.txt"), raw_output=stdout)
        error_code = result.get("error_code") if isinstance(result.get("error_code"), str) else None
        if exit_code != 0:
            result["status"] = "failed"
            errors = coerce_list(result.get("errors"))
            errors.append(f"hermes_exit_code_{exit_code}")
            if run_meta.get("stdout_truncated"):
                errors.append("stdout_truncated")
            if run_meta.get("stderr_truncated"):
                errors.append("stderr_truncated")
            if stderr.strip():
                errors.append("stderr_nonempty")
            result["errors"] = errors
            result["error_code"] = "nonzero_exit"
            error_code = "nonzero_exit"
        final_status = "completed" if exit_code == 0 else "failed"

    child_session_id = resume_id if mode == "resume" else extract_session_id(result)
    rename_meta = {"session_renamed": False}
    if mode == "new" and final_status == "completed":
        try:
            rename_meta = rename_session(hermes_bin, validated.canonical, child_session_id, title_text, cwd, env)
        except Exception as exc:
            rename_meta = {"session_renamed": False, "rename_error": f"{type(exc).__name__}: {exc}"}
    result.setdefault("session_id", child_session_id)

    json_safe_write(run_dir / "result.json", result)
    status.update(
        {
            "status": final_status,
            "ended_at": now_iso(),
            "exit_code": exit_code,
            "timed_out": timed_out,
            "error_code": error_code,
            "stdout_truncated": run_meta.get("stdout_truncated"),
            "stderr_truncated": run_meta.get("stderr_truncated"),
            "stdout_chars": run_meta.get("stdout_chars"),
            "stderr_chars": run_meta.get("stderr_chars"),
            "stdout_limit": run_meta.get("stdout_limit"),
            "stderr_limit": run_meta.get("stderr_limit"),
            "child_session_id": child_session_id,
            **rename_meta,
        }
    )
    json_safe_write(run_dir / "status.json", status)

    return {
        "success": final_status == "completed" and result.get("status") not in {"failed"},
        "mode": "sync",
        "task_id": task_id,
        "profile": validated.canonical,
        "status": final_status,
        "error_code": error_code,
        "session_title": title_text,
        "session_mode": mode,
        "requested_session_id": resume_id,
        "child_session_id": child_session_id,
        **rename_meta,
        "result": result,
        "paths": base_paths(run_dir),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stdout_truncated": run_meta.get("stdout_truncated"),
        "stderr_truncated": run_meta.get("stderr_truncated"),
    }


def resolve_run_dir(task_id: str) -> Path:
    if not isinstance(task_id, str) or not task_id.strip():
        raise ProfileDelegateError("task_id must be a non-empty string", "validation_error")
    clean = task_id.strip()
    if not re.fullmatch(r"pd_\d{8}_\d{6}_[a-z0-9]{6}", clean):
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


def profile_delegate_status(task_id: str, tail_chars: Any = 4000) -> Dict[str, Any]:
    run_dir = resolve_run_dir(task_id)
    try:
        max_tail = max(0, min(int(tail_chars or 4000), 20_000))
    except Exception as exc:
        raise ProfileDelegateError("tail_chars must be an integer", "validation_error") from exc
    status = read_json_file(run_dir / "status.json")
    result = read_json_file(run_dir / "result.json") if (run_dir / "result.json").exists() else None
    return {
        "success": True,
        "task_id": status.get("task_id", task_id),
        "profile": status.get("profile"),
        "status": status.get("status", "unknown"),
        "error_code": status.get("error_code"),
        "exit_code": status.get("exit_code"),
        "timed_out": bool(status.get("timed_out", False)),
        "stdout_truncated": bool(status.get("stdout_truncated", False)),
        "stderr_truncated": bool(status.get("stderr_truncated", False)),
        "created_at": status.get("created_at"),
        "started_at": status.get("started_at"),
        "ended_at": status.get("ended_at"),
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


def profile_delegate_list(limit: Any = 20) -> Dict[str, Any]:
    try:
        max_items = max(1, min(int(limit or 20), 100))
    except Exception as exc:
        raise ProfileDelegateError("limit must be an integer", "validation_error") from exc
    runs = []
    for run_dir in list(iter_run_dirs())[:max_items]:
        try:
            status = read_json_file(run_dir / "status.json")
        except ProfileDelegateError:
            status = {"task_id": run_dir.name, "status": "corrupt"}
        runs.append(
            {
                "task_id": status.get("task_id", run_dir.name),
                "profile": status.get("profile"),
                "status": status.get("status"),
                "error_code": status.get("error_code"),
                "created_at": status.get("created_at"),
                "ended_at": status.get("ended_at"),
                "run_dir": str(run_dir),
            }
        )
    return {"success": True, "runs_root": str(get_runs_root()), "count": len(runs), "runs": runs}


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
