"""Pure task/output contracts; independent of Hermes and artifact I/O."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

VALID_RESULT_STATUSES = {"ok", "blocked", "failed", "unknown"}

VALID_CONTRACT_STATUSES = {"valid", "recovered", "drifted", "empty", "not_evaluated"}

TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled", "timed_out"}

class ProfileDelegateError(Exception):
    """Expected profile-delegate failure with a stable machine-readable code."""

    def __init__(self, message: str, code: str = "profile_delegate_error", **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.details = details

def ensure_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)

def _candidate_score(obj: Any) -> int:
    """Score only generic terminal-envelope signals; never profile-specific keys."""
    if not isinstance(obj, dict):
        return 0
    status = ensure_text(obj.get("status")).strip().lower()
    if status not in VALID_RESULT_STATUSES or not isinstance(obj.get("summary"), str):
        return 0
    score = 100
    score += sum(5 for key in ("artifacts", "errors", "next_steps") if isinstance(obj.get(key), list))
    return score

def _top_level_json_candidates(
    text: str,
) -> Tuple[List[Tuple[Dict[str, Any], int, int, str]], int]:
    decoder = json.JSONDecoder()
    decoded: List[Tuple[Dict[str, Any], int, int, str]] = []
    depth = 0
    in_string = False
    escaped = False
    candidate_starts: List[int] = []
    for idx, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                candidate_starts.append(idx)
            depth += 1
        elif char == "}" and depth:
            depth -= 1
    for idx in candidate_starts:
        try:
            obj, end = decoder.raw_decode(text, idx)
        except Exception:
            continue
        if isinstance(obj, dict):
            decoded.append((obj, idx, end, "embedded_json"))
    # Starts are collected only at depth zero: successfully decoded spans
    # cannot contain or overlap another candidate. Avoid a quadratic rescan.
    return decoded, len(candidate_starts) - len(decoded)


def _parse_metadata(method: str, count: int = 0, *, span=None, error=None) -> Dict[str, Any]:
    return {"parse_method": method, "candidate_count": count, "selected_span": span, "parse_error": error}


def parse_json_result(text: str) -> Tuple[Optional[Any], Dict[str, Any]]:
    raw = text or ""
    stripped = raw.strip()
    empty = _parse_metadata('none', 0)
    if not stripped:
        return None, empty
    leading = len(raw) - len(raw.lstrip())
    try:
        obj = json.loads(stripped)
        return obj, _parse_metadata('whole_json', 1, span=[leading, leading + len(stripped)])
    except Exception:
        pass

    candidates: List[Tuple[Dict[str, Any], int, int, str]] = []
    fence_pattern = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
    for match in fence_pattern.finditer(raw):
        try:
            obj = json.loads(match.group(1))
        except Exception:
            continue
        if isinstance(obj, dict):
            candidates.append((obj, match.start(1), match.end(1), "json_fence"))
    embedded_candidates, malformed_candidate_count = _top_level_json_candidates(raw)
    candidates.extend(embedded_candidates)

    # Any malformed top-level JSON-like candidate makes structured parsing
    # unresolved. Do not let an adjacent valid object or textual OK hide it.
    if malformed_candidate_count:
        return None, _parse_metadata('malformed', len(candidates) + malformed_candidate_count, error='malformed_json_candidate')

    # Deduplicate a JSON object found both as fenced and embedded by exact span.
    unique: Dict[Tuple[int, int], Tuple[Dict[str, Any], int, int, str]] = {}
    for candidate in candidates:
        unique.setdefault((candidate[1], candidate[2]), candidate)
    candidates = list(unique.values())
    scored = [(candidate, _candidate_score(candidate[0])) for candidate in candidates]
    scored = [(candidate, score) for candidate, score in scored if score > 0]
    if not scored:
        # A single top-level custom object is useful structured output even when
        # it omitted our task-status envelope. Preserve it as task_status=unknown;
        # reject tiny numeric placeholder maps and multiple ambiguous objects.
        if len(candidates) == 1:
            obj, start, end, method = candidates[0]
            keys = [ensure_text(key) for key in obj]
            if len(keys) >= 2 and any(not key.isdigit() for key in keys):
                return obj, _parse_metadata(f'{method}_custom', 1, span=[start, end])
        if len(candidates) > 1:
            return None, _parse_metadata('ambiguous', len(candidates), error='ambiguous_json_candidates')
        return None, {**empty, "candidate_count": len(candidates)}
    best_score = max(score for _candidate, score in scored)
    best = [candidate for candidate, score in scored if score == best_score]
    if len(best) != 1:
        return None, _parse_metadata('ambiguous', len(best), error='ambiguous_json_candidates')
    obj, start, end, method = best[0]
    return obj, _parse_metadata(method, len(scored), span=[start, end])

def extract_json_object(text: str) -> Optional[Any]:
    """Backward-compatible object-only wrapper around deterministic parsing."""
    return parse_json_result(text)[0]

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

def _recover_text_status(raw_output: str, *, require_terminal: bool = False) -> Optional[str]:
    """Recover one non-negated verdict; new prose contracts require the terminal marker."""
    # Legacy first-line verdicts are accepted only when there is no terminal line.
    lines = (raw_output or "").splitlines()
    marker = re.compile(r"^PROFILE_DELEGATE_RESULT:\s*(ok|blocked|failed)$", re.I)
    marker_lines = [(index, marker.fullmatch(line.strip())) for index, line in enumerate(lines)
                    if "PROFILE_DELEGATE_RESULT:" in line.upper()]
    if marker_lines:
        if (len(marker_lines) != 1 or marker_lines[0][1] is None
                or marker_lines[0][0] != len(lines) - 1
                or sum(line.strip().startswith("```") for line in lines[:-1]) % 2):
            return None
        prefix = "\n".join(lines[:-1])
        legacy = _recover_legacy_text_status(prefix)
        if legacy and legacy != marker_lines[0][1].group(1).lower():
            return None
        if re.search(r"\b(?:not|never|without|isn't|wasn't|isnt|wasnt)\s+(?:PASS|OK|BLOCKED|FAILED)\b", prefix, re.I):
            return None
        return marker_lines[0][1].group(1).lower()
    if require_terminal:
        return None
    return _recover_legacy_text_status(raw_output)

def _recover_legacy_text_status(raw_output: str) -> Optional[str]:
    """Historical explicit first-line verdict recovery."""
    recovered: List[str] = []
    lines = (raw_output or "").splitlines()
    bounded_text = "\n".join(lines)
    status_token = r"(?:PASS|OK|BLOCKED|FAILED)(?:_[A-Z0-9_]+)?"
    if re.search(
        rf"\b(?:not|never|without|isn't|wasn't|isnt|wasnt)\s+{status_token}\b",
        bounded_text,
        re.I,
    ):
        return None
    for line in lines:
        candidate = line.strip()
        if not candidate:
            continue
        candidate = re.sub(r"^#{1,6}\s*", "", candidate).strip(" `*_: -")
        match = re.fullmatch(
            rf"(?:verdict|status)\s*[:=-]\s*(?P<label>{status_token})[.!]?|"
            rf"(?P<token>{status_token})(?:[.!]|\s+[—-]\s+(?P<detail>.{{1,300}}))?",
            candidate,
            re.I,
        )
        if not match:
            continue
        token = match.group("label") or match.group("token")
        detail = match.group("detail") or ""
        # A prose detail may describe evidence, but must not smuggle in a second
        # terminal token (for example "PASS — FAILED validation").
        if detail and re.search(rf"\b{status_token}\b", detail, re.I):
            return None
        base = token.split("_", 1)[0].lower()
        recovered.append(
            {"pass": "ok", "ok": "ok", "blocked": "blocked", "failed": "failed"}[base]
        )
    return recovered[0] if len(recovered) == 1 else None

def contract_status_for_parse(
    parsed: Any, meta: Dict[str, Any], *, raw_output: str = "",
) -> str:
    """Classify output-contract conformance independently from task outcome."""
    method = ensure_text(meta.get("parse_method")).strip().lower()
    if meta.get("parse_error"):
        return "drifted"
    if isinstance(parsed, dict):
        if method in {"", "whole_json"}:
            return "valid"
        if method.startswith(("json_fence", "embedded_json")):
            return "recovered"
        return "drifted"
    if method == "none" and not raw_output.strip():
        return "empty"
    return "drifted"

def apply_execution_status(result: Dict[str, Any], execution_status: str) -> Dict[str, Any]:
    """Apply the authoritative terminal execution outcome to a result."""
    normalized = ensure_text(execution_status).strip().lower()
    if normalized not in TERMINAL_RUN_STATUSES:
        raise ProfileDelegateError(
            f"invalid terminal execution_status: {normalized or '<empty>'}",
            "invalid_execution_status",
        )
    result["execution_status"] = normalized
    return result

def wrapper_success(execution_status: str, result: Dict[str, Any]) -> bool:
    """True only for completed execution and trustworthy explicit/recovered OK."""
    return (
        ensure_text(execution_status).strip().lower() == "completed"
        and result.get("execution_status") == "completed"
        and result.get("status") == "ok"
        and result.get("contract_status") in {"valid", "recovered"}
        and not result.get("parse_error")
    )

def normalize_result(
    parsed: Any, stdout_path: str, raw_output: str = "", *,
    parse_meta: Optional[Dict[str, Any]] = None, output_mode: str = "json",
    require_terminal_verdict: bool = False,
) -> Dict[str, Any]:
    meta = dict(parse_meta or {})
    if meta.get("parse_error") or output_mode in {"markdown", "text"}:
        parsed = None
    structured = isinstance(parsed, dict)
    result = dict(parsed) if structured else {}
    error_code = None
    if structured:
        status = ensure_text(parsed.get("status")).strip().lower() if "status" in parsed else "unknown"
        errors = coerce_list(parsed.get("errors"))
        if status not in VALID_RESULT_STATUSES:
            errors.append(f"invalid_status:{status or '<empty>'}")
            status = "failed"
        summary = ensure_text(parsed.get("summary") or "")
        contract = contract_status_for_parse(parsed, meta, raw_output=raw_output)
        if errors and "error_code" not in result:
            error_code = "target_reported_errors"
    else:
        summary = summarize_unstructured_output(raw_output)
        recovered = None if meta.get("parse_error") else _recover_text_status(
            raw_output, require_terminal=require_terminal_verdict)
        status = (recovered or "unknown") if summary else "failed"
        contract = "recovered" if recovered and summary else contract_status_for_parse(parsed, meta, raw_output=raw_output)
        errors = [] if status in {"ok", "unknown"} else [f"target_status:{status}"]
        if not summary:
            summary, contract, errors, error_code = "Delegated profile returned empty output.", "empty", ["parse_failed"], "parse_failed"
        elif meta.get("parse_error"):
            error_code = meta["parse_error"]
        elif require_terminal_verdict and not recovered:
            error_code = "missing_verdict"
        elif output_mode == "json":
            error_code = "unstructured_output"
    result.update(status=status, execution_status="completed", summary=summary,
                  artifacts=coerce_list(result.get("artifacts")), errors=errors,
                  next_steps=coerce_list(result.get("next_steps")), structured=structured,
                  contract_status=contract)
    if contract != "valid":
        result["raw_output_path"] = stdout_path
    if error_code:
        result["error_code"] = error_code
    result.update({key: value for key, value in meta.items() if value is not None})
    return result


def failure_result(summary: str, code: str, *, execution_status: str = "failed",
                   task_status: str = "failed", errors: Optional[List[str]] = None,
                   artifacts: Optional[List[str]] = None, next_steps: Optional[List[str]] = None,
                   **extra: Any) -> Dict[str, Any]:
    """A supervision failure is never a parsed task verdict."""
    result = dict(status=task_status, summary=summary, artifacts=artifacts or [],
                  errors=[code] if errors is None else errors, next_steps=next_steps or [],
                  structured=True, contract_status="not_evaluated", error_code=code, **extra)
    return apply_execution_status(result, execution_status)


def output_result(text: str, stdout_path: str, request: Dict[str, Any],
                  execution_status: str, *, error_code: Optional[str] = None,
                  errors: Optional[List[str]] = None) -> Dict[str, Any]:
    parsed, meta = parse_json_result(text)
    result = normalize_result(parsed, stdout_path, text, parse_meta=meta,
                              output_mode=ensure_text(request.get("resolved_output_mode") or "json"),
                              require_terminal_verdict=bool(request.get("require_terminal_verdict", False)))
    if execution_status != "completed" or error_code:
        result.update(status="failed", error_code=error_code)
        result["errors"] = coerce_list(result.get("errors")) + (errors if errors is not None else [error_code])
    return apply_execution_status(result, execution_status)


EVENT_SCHEMA_VERSION = 1
EVENT_JOURNAL_MAX_BYTES = 1_048_576
EVENT_RECORD_MAX_BYTES = 16_384
EVENT_TEXT_FRAGMENT_MAX_CHARS = 2_048
EVENT_MESSAGE_MAX_CHARS = 32_768
EVENT_IDENTIFIER_MAX_CHARS = 128
EVENT_METADATA_MAX_CHARS = 200
EVENT_TIMESTAMP_MAX_CHARS = 64


KNOWN_PHASES = {
    "starting", "transport_starting", "gateway_starting", "transport_ready", "session_creating",
    "session_ready", "agent_initializing", "model_running",
    "tool_running", "message_complete", "interrupting", "completed", "failed", "cancelled",
    "timed_out", "running", "child_running", "child_stopped", "cancellation_requested",
}


MESSAGE_STATUSES = {"complete", "error", "interrupted", "cancelled"}


STATUS_KINDS = {
    "compacting", "retrying", "waiting", "streaming", "queued", "running", "idle",
    "rate_limited", "context_compacted",
}


COMMON_KEYS = {
    "schema_version", "task_id", "seq", "at", "type", "phase", "payload", "redacted",
    "dropped_fields",
}


_OSC_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\|$)")
_CSI_RE = re.compile(r"(?:\x1b\[|\x9b)[0-?]*[ -/]*[@-~]")
_ESC_RE = re.compile(r"\x1b(?:[@-_]|.)")


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

LIFECYCLE_STATUSES = TERMINAL_RUN_STATUSES | {"running", "cancelling"}
