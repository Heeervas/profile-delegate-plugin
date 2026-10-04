"""Hermes native delivery seam; keep internal persistence dependencies here."""
from __future__ import annotations

import hashlib
import importlib
import inspect
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Dict

NATIVE_ASYNC_LEDGER_APIS = {
    "_persist_dispatch": ({},),
    "_persist_completion": ({}, {}),
    "get_durable_delegation": ("pd_compatibility_probe",),
}

NATIVE_ASYNC_LEDGER_COLUMNS = {
    "delegation_id", "origin_session", "parent_session_id", "state",
    "dispatched_at", "completed_at", "updated_at", "event_json", "result_json",
    "delivery_state", "delivery_attempts", "delivered_at",
}

def ledger_compatibility(hermes_home: Path) -> Dict[str, Any]:
    """Validate the native durable-delivery contract without mutating state.db."""
    report: Dict[str, Any] = {
        "compatible": False,
        "database_open_mode": "read_only",
        "database": str(hermes_home / "state.db"),
        "missing_apis": [],
        "incompatible_api_signatures": [],
        "missing_columns": [],
    }
    try:
        native = importlib.import_module("tools.async_delegation")
    except Exception as exc:
        report["reason"] = f"native async delegation import failed: {type(exc).__name__}: {exc}"
        return report

    for name, probe_args in NATIVE_ASYNC_LEDGER_APIS.items():
        function = getattr(native, name, None)
        if not callable(function):
            report["missing_apis"].append(name)
            continue
        try:
            inspect.signature(function).bind(*probe_args)
        except (TypeError, ValueError):
            report["incompatible_api_signatures"].append(name)
    if report["missing_apis"] or report["incompatible_api_signatures"]:
        report["reason"] = "required native async-delegation API is missing or incompatible"
        return report

    db_path = hermes_home / "state.db"
    if not db_path.is_file():
        report["reason"] = "Hermes state.db does not exist; refusing to initialize it from the plugin"
        return report
    try:
        uri = f"{db_path.as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=2)) as conn:
            conn.execute("PRAGMA query_only=ON")
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='async_delegations'"
            ).fetchone()
            if table is None:
                report["reason"] = "native async_delegations table is absent"
                return report
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(async_delegations)")}
    except Exception as exc:
        report["reason"] = f"read-only native ledger inspection failed: {type(exc).__name__}: {exc}"
        return report
    report["missing_columns"] = sorted(NATIVE_ASYNC_LEDGER_COLUMNS - columns)
    if report["missing_columns"]:
        report["reason"] = "native async_delegations schema is incompatible"
        return report
    report["compatible"] = True
    report["reason"] = "compatible"
    return report


def get_completion(task_id: str):
    from tools.async_delegation import get_durable_delegation
    return get_durable_delegation(task_id)


def persist_dispatch(event: Dict[str, Any]) -> None:
    from tools.async_delegation import _persist_dispatch
    _persist_dispatch(event)


def persist_completion(event: Dict[str, Any], result: Dict[str, Any]) -> None:
    from tools.async_delegation import _persist_completion
    _persist_completion(event, result)


def offer_completion(event: Dict[str, Any], result: Dict[str, Any]) -> bool:
    """Offer only an already-durable, same-lane completion still awaiting delivery."""
    row = get_completion(event["delegation_id"])
    if not row or (row.get("state"), row.get("result"), row.get("origin_session"), row.get("delivery_state")) != (
            event["status"], result, event["session_key"], "pending"):
        return False
    from tools.process_registry import process_registry
    process_registry.completion_queue.put(event)
    return True


# Match the installed native resume default; overflow only disables receipt proof.
STEER_SNAPSHOT_MAX_ROWS = 20_000


def steer_snapshot(
    home: Path, session_id: str, *, deadline: float, include_inactive: bool = False,
) -> dict[str, str | None] | None:
    """Read raw native occurrences without replay dedupe, mutation or future tips."""
    path = home / "state.db"
    if not path.is_file() or path.is_symlink() or time.monotonic() >= deadline:
        return None
    try:
        from hermes_state import SessionDB
        from agent.message_metadata import message_uid_or_none
        snapshot, total = {}, 0
        with closing(SessionDB(path, read_only=True)) as db:
            lineage = db.get_compression_lineage(session_id)
            if session_id not in lineage:
                return None
            for segment in lineage[:lineage.index(session_id) + 1]:
                offset = 0
                while True:
                    if time.monotonic() >= deadline:
                        return None
                    # Native raw per-segment reads keep inactive occurrences and
                    # clone UIDs; projected history can hide a stale occurrence.
                    rows = db.get_messages(segment, include_inactive=include_inactive,
                                           offset=offset, limit=min(128, STEER_SNAPSHOT_MAX_ROWS - total + 1))
                    total += len(rows)
                    if total > STEER_SNAPSHOT_MAX_ROWS:
                        return None
                    for message in rows:
                        uid = message_uid_or_none(message)
                        if uid is None:
                            return None
                        digest = None
                        if message.get("role") == "user" and message.get("display_kind") == "steer":
                            content = message.get("content")
                            if not isinstance(content, str):
                                return None
                            digest = hashlib.sha256(content.encode()).hexdigest()
                        if uid in snapshot and snapshot[uid] != digest:
                            return None
                        snapshot[uid] = digest
                    if not rows:
                        break
                    offset += len(rows)
        return snapshot if time.monotonic() < deadline else None
    except Exception:
        return None


def steers_consumed(
    before: dict[str, str | None] | None, after: dict[str, str | None] | None, texts: list[str],
) -> bool:
    """Match fresh native occurrences, including concatenated pending corrections."""
    if before is None or after is None or not texts:
        return False
    from agent.prompt_builder import format_steer_marker
    pending = list(texts)
    for uid, content in after.items():
        if uid in before or content is None:
            continue
        for count in range(1, len(pending) + 1):
            expected = format_steer_marker("\n".join(pending[:count])).lstrip()
            if content == hashlib.sha256(expected.encode()).hexdigest():
                del pending[:count]
                break
    return not pending
