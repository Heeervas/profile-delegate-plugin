"""Privacy-first, bounded derived event journal for Profile Delegate runs."""
from __future__ import annotations

import json
import os
import re
import stat
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    import fcntl
except Exception:  # pragma: no cover - fail closed on unsupported platforms
    fcntl = None  # type: ignore[assignment]

try:
    from .event_schema import (
        EVENT_JOURNAL_MAX_BYTES, EVENT_MESSAGE_MAX_CHARS, EVENT_METADATA_MAX_CHARS,
        EVENT_RECORD_MAX_BYTES, EVENT_SCHEMA_VERSION, EVENT_TEXT_FRAGMENT_MAX_CHARS,
    )
except ImportError:
    from event_schema import (  # type: ignore[no-redef]
        EVENT_JOURNAL_MAX_BYTES, EVENT_MESSAGE_MAX_CHARS, EVENT_METADATA_MAX_CHARS,
        EVENT_RECORD_MAX_BYTES, EVENT_SCHEMA_VERSION, EVENT_TEXT_FRAGMENT_MAX_CHARS,
    )

SCHEMA_VERSION = EVENT_SCHEMA_VERSION
TERMINAL_STATUSES = {"completed", "failed", "cancelled", "timed_out"}
LIFECYCLE_STATUSES = TERMINAL_STATUSES | {"running", "cancelling"}
KNOWN_PHASES = {
    "starting", "transport_starting", "gateway_starting", "transport_ready", "session_creating",
    "session_ready", "agent_initializing", "model_running",
    "tool_running", "message_complete", "interrupting", "completed", "failed", "cancelled",
    "timed_out", "running",
}
MESSAGE_STATUSES = {"complete", "error", "interrupted", "cancelled"}
STATUS_KINDS = {
    "compacting", "retrying", "waiting", "streaming", "queued", "running", "idle",
    "rate_limited", "context_compacted",
}
USAGE_KEYS = {"input", "output", "reasoning", "total", "calls"}
COMMON_KEYS = {
    "schema_version", "task_id", "seq", "at", "type", "phase", "payload", "redacted",
    "dropped_fields",
}

# ECMA-48 CSI and OSC, including unterminated OSC to end of fragment.
_OSC_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\|$)")
_CSI_RE = re.compile(r"(?:\x1b\[|\x9b)[0-?]*[ -/]*[@-~]")
_ESC_RE = re.compile(r"\x1b(?:[@-_]|.)")
_SECRET_RE = re.compile(
    r"(?i)\b(token|api[_-]?key|secret|password|authorization)\s*[:=]\s*([^\s,;]+)"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded(value: Any, limit: int = 128) -> str:
    return str(value or "")[:limit]


def sanitize_text(value: Any, limit: int) -> str:
    """Neutralize terminal controls and invalid Unicode, preserving newline/tab."""
    text = str(value or "").encode("utf-8", "replace").decode("utf-8", "replace")
    text = _OSC_RE.sub("", text)
    text = _CSI_RE.sub("", text)
    text = _ESC_RE.sub("", text)
    text = "".join(
        char for char in text
        if char in "\n\t" or (ord(char) >= 0x20 and not 0x7F <= ord(char) <= 0x9F)
    )
    return text[:limit]


def _redact(text: str) -> tuple[str, bool]:
    redacted, count = _SECRET_RE.subn(lambda match: f"{match.group(1)}=[REDACTED]", text)
    return redacted, bool(count)


def _tool_class(name: str) -> str:
    lowered = name.lower()
    if any(part in lowered for part in ("browser", "vision")):
        return "browser"
    if any(part in lowered for part in ("web", "http", "search")):
        return "web"
    if any(part in lowered for part in ("terminal", "shell", "process", "exec")):
        return "shell"
    if any(part in lowered for part in ("file", "patch", "read", "write")):
        return "file"
    if "delegate" in lowered:
        return "delegate"
    return "other"


class EventJournal:
    """Project raw gateway events into a durable allowlisted JSONL stream."""

    def __init__(
        self, run_dir: Path, *, task_id: str = "", ui_session_id: str = "",
        persist_message_text: bool = False, max_bytes: int = EVENT_JOURNAL_MAX_BYTES,
        terminal_reserve_bytes: int = 4_096, max_events: int = 10_000,
        max_record_bytes: int = EVENT_RECORD_MAX_BYTES,
        max_text_fragment_chars: int = EVENT_TEXT_FRAGMENT_MAX_CHARS,
        max_message_chars: int = EVENT_MESSAGE_MAX_CHARS, flush_interval_s: float = 0.1,
        coalesce_chars: int = 4_096, max_pre_session_events: int = 32,
        max_pre_session_bytes: int = 65_536,
    ) -> None:
        self.run_dir = Path(run_dir)
        self.task_id = task_id or self.run_dir.name
        self.ui_session_id = ui_session_id
        self.persist_message_text = bool(persist_message_text)
        self.max_bytes = max(256, int(max_bytes))
        self.terminal_reserve_bytes = max(0, min(int(terminal_reserve_bytes), self.max_bytes))
        self.max_events = max(1, int(max_events))
        self.max_record_bytes = max(128, int(max_record_bytes))
        self.max_text_fragment_chars = max(1, int(max_text_fragment_chars))
        self.max_message_chars = max(1, int(max_message_chars))
        self.flush_interval_s = max(0.0, float(flush_interval_s))
        self.coalesce_chars = max(1, int(coalesce_chars))
        self.max_pre_session_events = max(0, int(max_pre_session_events))
        self.max_pre_session_bytes = max(0, int(max_pre_session_bytes))
        self.path = self.run_dir / "events.jsonl"
        self.lock_path = self.run_dir / "events.lock"
        self.fd: Optional[int] = None
        self.lock_fd: Optional[int] = None
        self.seq = 0
        self.event_count = 0
        self.bytes_written = 0
        self.truncated = False
        self.truncation_marker_written = False
        self.degraded = False
        self.disabled = False
        self.degradation_reason = ""
        self.turn_count = 0
        self.tool_ids: Set[str] = set()
        self.api_calls: Optional[int] = None
        self.usage: Dict[str, int] = {}
        self.profile = ""
        self.model = ""
        self.provider = ""
        self.phase = "running"
        self.pending_message_id = ""
        self.pending_text = ""
        self.pending_started = 0.0
        self.redaction_context = ""
        self.message_had_delta: Set[str] = set()
        self.pre_session: List[Dict[str, Any]] = []
        self.pre_session_bytes = 0
        self._open()

    def _degrade(self, reason: Any, *, disable: bool = True) -> None:
        self.degraded = True
        self.disabled = self.disabled or disable
        self.degradation_reason = _bounded(reason, 200)

    def _open(self) -> None:
        try:
            if fcntl is None:
                raise OSError("fcntl unavailable")
            self.run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.run_dir, 0o700)
            flags = os.O_RDWR | os.O_APPEND | os.O_CREAT
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            lock_flags = os.O_RDWR | os.O_CREAT
            if hasattr(os, "O_NOFOLLOW"):
                lock_flags |= os.O_NOFOLLOW
            self.lock_fd = os.open(self.lock_path, lock_flags, 0o600)
            os.fchmod(self.lock_fd, 0o600)
            lock_stat = os.fstat(self.lock_fd)
            if not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_uid != os.getuid():
                raise OSError("unsafe journal lock")
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX)
            try:
                self.fd = os.open(self.path, flags, 0o600)
                os.fchmod(self.fd, 0o600)
                file_stat = os.fstat(self.fd)
                if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_uid != os.getuid():
                    raise OSError("unsafe journal destination")
                self._recover_locked()
            finally:
                fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
        except Exception as exc:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
            if self.lock_fd is not None:
                os.close(self.lock_fd)
                self.lock_fd = None
            self._degrade(f"open:{type(exc).__name__}")

    def _recover_locked(self) -> None:
        assert self.fd is not None
        self.seq = 0
        self.event_count = 0
        self.bytes_written = 0
        self.truncated = False
        self.truncation_marker_written = False
        size = os.fstat(self.fd).st_size
        self.bytes_written = size
        if size == 0:
            return
        os.lseek(self.fd, 0, os.SEEK_SET)
        data = b""
        remaining = size
        while remaining:
            chunk = os.read(self.fd, min(65_536, remaining))
            if not chunk:
                break
            data += chunk
            remaining -= len(chunk)
        last_newline = data.rfind(b"\n")
        if last_newline < len(data) - 1:
            os.ftruncate(self.fd, last_newline + 1 if last_newline >= 0 else 0)
            data = data[:last_newline + 1] if last_newline >= 0 else b""
            self.bytes_written = len(data)
        lines = data.splitlines()
        if not lines:
            return
        try:
            parsed = [json.loads(line) for line in lines]
            if any(not isinstance(item, dict) or set(item) != COMMON_KEYS for item in parsed):
                raise ValueError("invalid record schema")
            seqs = [int(item["seq"]) for item in parsed]
            if seqs != list(range(1, len(seqs) + 1)):
                raise ValueError("invalid sequence")
            self.seq = seqs[-1]
            self.event_count = sum(
                item["type"] not in {"journal.truncated", "terminal"} for item in parsed
            )
            self.truncation_marker_written = any(item["type"] == "journal.truncated" for item in parsed)
            self.truncated = self.truncation_marker_written
        except Exception:
            self._degrade("corrupt_complete_record")

    def set_session(self, session_id: str) -> None:
        if self.ui_session_id:
            return
        self.ui_session_id = _bounded(session_id)
        buffered = self.pre_session
        self.pre_session = []
        self.pre_session_bytes = 0
        for frame in buffered:
            self.ingest(frame)

    def ingest(self, frame: Any) -> bool:
        if self.disabled or not isinstance(frame, dict):
            return False
        params = frame.get("params")
        if frame.get("method") != "event" or not isinstance(params, dict):
            return False
        kind = params.get("type")
        if kind == "gateway.ready":
            return False
        if not self.ui_session_id:
            try:
                encoded_size = len(json.dumps(frame, ensure_ascii=False).encode("utf-8"))
            except Exception:
                return False
            if len(self.pre_session) >= self.max_pre_session_events or self.pre_session_bytes + encoded_size > self.max_pre_session_bytes:
                self._degrade("pre_session_overflow", disable=False)
                return False
            self.pre_session.append(frame)
            self.pre_session_bytes += encoded_size
            return False
        if params.get("session_id") != self.ui_session_id:
            return False
        projected = self.project(frame)
        if projected is None:
            return False
        if projected["type"] == "message.delta":
            if len(self.pending_text) >= self.coalesce_chars:
                self.flush(force=True)
                return True
            self.flush()
            return False
        if self.pending_text:
            self.flush(force=True)
        return self._append_projected(projected)

    def project(self, frame: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        params = frame.get("params") if isinstance(frame.get("params"), dict) else {}
        payload = params.get("payload") if isinstance(params.get("payload"), dict) else {}
        kind = str(params.get("type") or "")
        allowed: Dict[str, Any]
        dropped: List[str] = []
        redacted = False
        phase = self.phase
        if kind == "message.start":
            if payload.get("role") not in (None, "", "assistant"):
                return None
            message_id = _bounded(payload.get("message_id") or payload.get("id"))
            allowed = {"role": "assistant"}
            if message_id:
                allowed["message_id"] = message_id
            self.turn_count += 1
            phase = "model_running"
        elif kind == "message.delta":
            if not self.persist_message_text:
                return None
            message_id = _bounded(payload.get("message_id") or payload.get("id"))
            fragment = sanitize_text(payload.get("text"), self.max_text_fragment_chars)
            if not fragment:
                return None
            if self.pending_message_id and self.pending_message_id != message_id:
                self.flush(force=True)
            self.pending_message_id = message_id
            self.pending_text = (self.pending_text + fragment)[:self.max_message_chars]
            self.pending_started = self.pending_started or time.monotonic()
            self.message_had_delta.add(message_id)
            if len(self.pending_text) >= self.coalesce_chars:
                self.flush(force=True)
            return None
        elif kind == "message.complete":
            message_id = _bounded(payload.get("message_id") or payload.get("id"))
            status_value = _bounded(payload.get("status") or "complete", 32).lower()
            if status_value not in MESSAGE_STATUSES:
                status_value = "error"
            allowed = {"status": status_value}
            if message_id:
                allowed["message_id"] = message_id
            clean_usage = self._clean_usage(payload.get("usage"))
            if clean_usage:
                allowed["usage"] = clean_usage
                self.usage = clean_usage
                self.api_calls = clean_usage.get("calls", self.api_calls)
            if self.persist_message_text and message_id not in self.message_had_delta and payload.get("text"):
                text, redacted = _redact(sanitize_text(payload.get("text"), self.max_message_chars))
                if text:
                    allowed["text"] = text
            dropped = [key for key in ("text", "reasoning", "rendered", "warning") if key in payload and key not in allowed]
            phase = "message_complete"
        elif kind in {"tool.start", "tool.complete"}:
            tool_id = _bounded(payload.get("tool_id") or payload.get("id"))
            tool = _bounded(payload.get("name") or payload.get("tool") or payload.get("tool_name"))
            allowed = {"tool_id": tool_id, "tool": tool, "tool_class": _tool_class(tool)}
            if kind == "tool.start":
                if tool_id:
                    self.tool_ids.add(tool_id)
                phase = "tool_running"
            else:
                duration = payload.get("duration_s")
                if duration is None:
                    try:
                        duration = float(payload.get("ended_at")) - float(payload.get("started_at"))
                    except Exception:
                        duration = 0.0
                try:
                    allowed["duration_s"] = round(max(0.0, min(float(duration), 86_400.0)), 3)
                except Exception:
                    allowed["duration_s"] = 0.0
                allowed["outcome"] = "complete" if tool_id and tool_id in self.tool_ids else "unknown"
                phase = "model_running"
            dropped = [key for key in ("args", "arguments", "result", "summary", "diff") if key in payload]
        elif kind == "session.info":
            allowed = {}
            for key in ("profile", "model", "provider"):
                source_key = "profile_name" if key == "profile" else key
                value = _bounded(payload.get(source_key), EVENT_METADATA_MAX_CHARS)
                if value:
                    allowed[key] = value
                    setattr(self, key, value)
            clean_usage = self._clean_usage(payload.get("usage"))
            if clean_usage:
                allowed["usage"] = clean_usage
                self.usage = clean_usage
                self.api_calls = clean_usage.get("calls", self.api_calls)
            phase = "session_ready"
        elif kind == "status.update":
            status_kind = _bounded(payload.get("kind"), 64).lower()
            if status_kind not in STATUS_KINDS:
                return None
            allowed = {"kind": status_kind}
            if "text" in payload:
                dropped.append("text")
        elif kind == "lifecycle":
            status_value = _bounded(payload.get("status"), 32).lower()
            phase_value = _bounded(payload.get("phase"), 64).lower()
            if status_value not in LIFECYCLE_STATUSES:
                return None
            allowed = {"status": status_value, "phase": phase_value if phase_value in KNOWN_PHASES else status_value}
            phase = allowed["phase"]
        else:
            return None
        self.phase = phase
        return {"type": kind, "phase": phase, "payload": allowed, "redacted": redacted, "dropped_fields": dropped}

    @staticmethod
    def _clean_usage(value: Any) -> Dict[str, int]:
        usage = value if isinstance(value, dict) else {}
        return {
            key: item for key, item in usage.items()
            if key in USAGE_KEYS and isinstance(item, int) and not isinstance(item, bool) and item >= 0
        }

    def _pending_projection(self) -> Optional[Dict[str, Any]]:
        if not self.pending_text:
            return None
        raw_text = sanitize_text(self.pending_text, self.max_message_chars)
        combined = self.redaction_context + raw_text
        boundary = len(self.redaction_context)
        pieces: List[str] = []
        cursor = boundary
        redacted = False
        for match in _SECRET_RE.finditer(combined):
            if match.end() <= boundary:
                continue
            redacted = True
            if match.start() >= boundary:
                pieces.append(combined[cursor:match.start()])
                pieces.append(f"{match.group(1)}=[REDACTED]")
            else:
                pieces.append("[REDACTED]")
            cursor = match.end()
        pieces.append(combined[max(cursor, boundary):])
        text = "".join(pieces)
        self.redaction_context = combined[-128:]
        projected = {"type": "message.delta", "phase": "model_running", "payload": {"message_id": self.pending_message_id, "text": text}, "redacted": redacted, "dropped_fields": []}
        self.pending_message_id = ""
        self.pending_text = ""
        self.pending_started = 0.0
        return projected

    def flush(self, *, force: bool = False) -> None:
        due = self.pending_text and self.pending_started and (
            time.monotonic() - self.pending_started >= self.flush_interval_s
        )
        # The aggregate buffer is sanitized/redacted as one unit so secrets split
        # across incoming deltas cannot bypass the pattern matcher.
        if force or due:
            projected = self._pending_projection()
            if projected is not None:
                self._append_projected(projected)
        if force and self.fd is not None and not self.disabled:
            try:
                os.fsync(self.fd)
            except Exception as exc:
                self._degrade(f"fsync:{type(exc).__name__}")

    def _record_bytes(self, projected: Dict[str, Any], seq: int) -> bytes:
        record = {"schema_version": SCHEMA_VERSION, "task_id": self.task_id, "seq": seq, "at": _now(), **projected}
        return (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8", "replace")

    def _append_projected(self, projected: Dict[str, Any], *, terminal: bool = False, internal: bool = False) -> bool:
        if self.disabled or self.fd is None or self.lock_fd is None:
            return False
        assert fcntl is not None
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX)
            try:
                self._recover_locked()
                if self.disabled or (self.truncated and not terminal):
                    return False
                encoded = self._record_bytes(projected, self.seq + 1)
                if len(encoded) > self.max_record_bytes:
                    projected = {
                        "type": "event.dropped", "phase": self.phase,
                        "payload": {"reason": "record_too_large"}, "redacted": False,
                        "dropped_fields": [],
                    }
                    encoded = self._record_bytes(projected, self.seq + 1)
                    if len(encoded) > self.max_record_bytes:
                        self._degrade("minimal_record_too_large")
                        return False
                counted = not terminal and projected["type"] != "journal.truncated"
                ordinary_limit = self.max_bytes - self.terminal_reserve_bytes
                exceeds = (
                    (counted and self.event_count >= self.max_events)
                    or self.bytes_written + len(encoded) > (
                        self.max_bytes if terminal else ordinary_limit
                    )
                )
                if exceeds and not terminal:
                    self._truncate_locked("limit")
                    return False
                if exceeds:
                    self._degrade("terminal_reserve_exhausted")
                    return False
                self._write_bytes(encoded)
                self.seq += 1
                self.event_count += 1 if counted else 0
                self.bytes_written += len(encoded)
                return True
            finally:
                fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
        except Exception as exc:
            self._degrade(f"write:{type(exc).__name__}")
            return False

    def _write_bytes(self, data: bytes) -> None:
        """Write one record while the caller holds ``events.lock``."""
        assert self.fd is not None
        written = os.write(self.fd, data)
        if written != len(data):
            raise OSError("short journal write")

    def _truncate(self, reason: str) -> None:
        if self.disabled or self.fd is None or self.lock_fd is None or fcntl is None:
            return
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX)
            try:
                self._recover_locked()
                self._truncate_locked(reason)
            finally:
                fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
        except Exception as exc:
            self._degrade(f"truncate:{type(exc).__name__}")

    def _truncate_locked(self, reason: str) -> None:
        """Append the unique marker while the caller holds ``events.lock``."""
        if self.truncation_marker_written:
            self.truncated = True
            return
        marker = {
            "type": "journal.truncated", "phase": self.phase,
            "payload": {"reason": _bounded(reason, 64), "dropped_after_seq": self.seq},
            "redacted": False, "dropped_fields": [],
        }
        encoded = self._record_bytes(marker, self.seq + 1)
        if len(encoded) <= self.max_record_bytes and self.bytes_written + len(encoded) <= self.max_bytes:
            self._write_bytes(encoded)
            self.seq += 1
            self.bytes_written += len(encoded)
            self.truncation_marker_written = True
        self.truncated = True

    def finalize(self, status: str, *, error_code: Any = "", child_session_id: Any = "") -> bool:
        self.flush(force=True)
        clean_status = _bounded(status, 32).lower()
        if clean_status not in TERMINAL_STATUSES:
            clean_status = "failed"
        payload = {"status": clean_status, "error_code": _bounded(error_code, 128), "child_session_id": _bounded(child_session_id, 128)}
        projected = {"type": "terminal", "phase": clean_status, "payload": payload, "redacted": False, "dropped_fields": []}
        result = self._append_projected(projected, terminal=True)
        self.flush(force=True)
        self.close()
        return result

    def close(self) -> None:
        self.flush(force=True)
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None

    def snapshot_fields(self) -> Dict[str, Any]:
        fields: Dict[str, Any] = {
            "event_schema_version": SCHEMA_VERSION, "event_seq": self.seq,
            "event_stream_truncated": self.truncated, "turn_count": self.turn_count,
            "tool_calls": len(self.tool_ids), "api_calls": self.api_calls,
        }
        if self.profile:
            fields["delegated_profile"] = self.profile
        if self.model:
            fields["model"] = self.model
        if self.provider:
            fields["provider"] = self.provider
        if self.usage:
            fields["usage"] = dict(self.usage)
        if self.degraded:
            fields["observability_degraded"] = True
            fields["observability_error"] = self.degradation_reason
        return fields
