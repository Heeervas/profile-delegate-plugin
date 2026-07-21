"""Contract tests for the bounded Profile Delegate spectator event journal."""
from __future__ import annotations

import json
import os
from pathlib import Path

from event_journal import EventJournal, sanitize_text


def frame(kind, payload=None, session_id="ui-1", **extra):
    return {"jsonrpc": "2.0", "method": "event", "params": {"type": kind, "session_id": session_id, "payload": payload or {}, **extra}}


def records(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_tool_allowlist_bounds_and_default_privacy(tmp_path):
    journal = EventJournal(tmp_path, task_id="pd_test", ui_session_id="ui-1")
    journal.ingest(frame("tool.start", {"tool_id": "i" * 200, "name": "terminal" * 30, "arguments": {"command": "SUPER_SECRET /private/path"}, "prompt": "SUPER_SECRET", "reasoning": "SUPER_SECRET"}))
    journal.ingest(frame("tool.complete", {"tool_id": "i" * 200, "name": "terminal", "started_at": 10, "ended_at": 12.5, "result": "SUPER_SECRET /private/path", "success": True}))
    journal.ingest(frame("status.update", {"kind": "compacting", "text": "SUPER_SECRET"}))
    journal.ingest(frame("thinking.delta", {"text": "SUPER_SECRET"}))
    journal.ingest(frame("message.delta", {"message_id": "m1", "text": "SUPER_SECRET"}))
    journal.close()
    saved = records(tmp_path / "events.jsonl")
    raw = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    assert [item["type"] for item in saved] == ["tool.start", "tool.complete", "status.update"]
    assert set(saved[0]["payload"]) == {"tool_id", "tool", "tool_class"}
    assert len(saved[0]["payload"]["tool_id"]) == len(saved[0]["payload"]["tool"]) == 128
    assert set(saved[1]["payload"]) == {"tool_id", "tool", "tool_class", "duration_s", "outcome"}
    assert saved[1]["payload"]["outcome"] == "complete" and saved[1]["payload"]["duration_s"] == 2.5
    assert saved[2]["payload"] == {"kind": "compacting"}
    assert saved[0]["dropped_fields"] == ["arguments"]
    assert saved[1]["dropped_fields"] == ["result"]
    for forbidden in ("SUPER_SECRET", "/private/path", "reasoning", '"prompt"'):
        assert forbidden not in raw


def test_opt_in_text_is_aggregate_redacted_neutralized_bounded_and_ordered(tmp_path):
    journal = EventJournal(tmp_path, task_id="pd_test", ui_session_id="ui-1", persist_message_text=True, max_message_chars=40)
    journal.ingest(frame("message.start", {"message_id": "m1", "role": "assistant"}))
    journal.ingest(frame("message.delta", {"message_id": "m1", "text": "token=sec"}))
    journal.ingest(frame("message.delta", {"message_id": "m1", "text": "ret123\x1b[31mRED\x1b[0m\x1b]0;owned\x07\x00"}))
    journal.ingest(frame("tool.start", {"tool_id": "t1", "name": "web_search"}))
    journal.ingest(frame("message.complete", {"message_id": "m1", "status": "complete", "text": "duplicate"}))
    journal.close()
    saved = records(tmp_path / "events.jsonl")
    assert [item["type"] for item in saved] == ["message.start", "message.delta", "tool.start", "message.complete"]
    text = saved[1]["payload"]["text"]
    assert "secret123" not in text and "[REDACTED]" in text and "RED" in text
    assert "\x1b" not in text and "owned" not in text and "\x00" not in text
    assert "text" not in saved[-1]["payload"] and len(text) <= 40


def test_sanitize_text_removes_controls_and_replaces_invalid_unicode():
    assert sanitize_text("a\x00b\x1b[2Jc\x1b]0;owned\x07d\x85e\ud800f\n\t", 100) == "abcde?f\n\t"


def test_sequence_counters_dedupe_and_authoritative_usage(tmp_path):
    journal = EventJournal(tmp_path, task_id="pd_test", ui_session_id="ui-1")
    journal.ingest(frame("message.start", {"message_id": "m1", "role": "assistant"}))
    journal.ingest(frame("tool.start", {"tool_id": "t1", "name": "search_files"}))
    journal.ingest(frame("tool.start", {"tool_id": "t1", "name": "search_files"}))
    journal.ingest(frame("session.info", {"profile": "reviewer", "model": "model", "provider": "provider", "usage": {"input": 3, "output": 2, "reasoning": -1, "total": 5, "calls": 7, "junk": 9}}))
    snapshot = journal.snapshot_fields()
    assert (snapshot["turn_count"], snapshot["tool_calls"], snapshot["api_calls"]) == (1, 1, 7)
    journal.close()
    saved = records(tmp_path / "events.jsonl")
    assert [item["seq"] for item in saved] == list(range(1, len(saved) + 1))
    assert saved[-1]["payload"]["usage"] == {"input": 3, "output": 2, "total": 5, "calls": 7}


def test_unknown_malformed_wrong_role_and_wrong_session_are_dropped(tmp_path):
    journal = EventJournal(tmp_path, task_id="pd_test", ui_session_id="ui-1")
    for value in ({}, None, "bad", frame("unknown", {"secret": "x"}), frame("message.start", {"message_id": "m", "role": "user"}), frame("tool.start", {"tool_id": "x", "name": "terminal"}, session_id="other")):
        assert journal.ingest(value) is False
    journal.close()
    assert records(tmp_path / "events.jsonl") == []


def test_reopen_partial_tail_and_corrupt_complete_line(tmp_path):
    journal = EventJournal(tmp_path, task_id="pd_test", ui_session_id="ui-1")
    journal.ingest(frame("tool.start", {"tool_id": "t1", "name": "terminal"}))
    journal.close()
    path = tmp_path / "events.jsonl"
    path.write_bytes(path.read_bytes() + b'{"partial":')
    reopened = EventJournal(tmp_path, task_id="pd_test", ui_session_id="ui-1")
    reopened.ingest(frame("tool.complete", {"tool_id": "t1", "name": "terminal"}))
    reopened.close()
    assert [item["seq"] for item in records(path)] == [1, 2]
    path.write_bytes(path.read_bytes() + b"not-json\n")
    degraded = EventJournal(tmp_path, task_id="pd_test", ui_session_id="ui-1")
    before = path.read_bytes()
    assert degraded.degraded and degraded.ingest(frame("tool.start", {"tool_id": "t2", "name": "terminal"})) is False
    assert path.read_bytes() == before


def test_caps_marker_terminal_reserve_and_oversized_reduction(tmp_path):
    journal = EventJournal(tmp_path, task_id="pd_test", ui_session_id="ui-1", max_bytes=900, terminal_reserve_bytes=300, max_events=3, max_record_bytes=400)
    for index in range(10):
        journal.ingest(frame("tool.start", {"tool_id": str(index), "name": "x" * 500}))
    journal.finalize("completed", child_session_id="sid", error_code="code")
    saved = records(tmp_path / "events.jsonl")
    assert sum(item["type"] == "journal.truncated" for item in saved) <= 1
    assert saved[-1]["type"] == "terminal" and saved[-1]["payload"] == {"status": "completed", "error_code": "code", "child_session_id": "sid"}
    assert (tmp_path / "events.jsonl").stat().st_size <= 900 and journal.snapshot_fields()["event_stream_truncated"] is True
    other = tmp_path / "other"
    other.mkdir()
    oversized = EventJournal(other, task_id="pd_test", ui_session_id="ui-1", max_record_bytes=280)
    oversized.ingest(frame("tool.start", {"tool_id": "t", "name": "x" * 128}))
    oversized.close()
    assert records(other / "events.jsonl")[0]["type"] == "event.dropped"


def test_symlink_and_write_failure_degrade_without_raise(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.write_text("safe", encoding="utf-8")
    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / "events.jsonl").symlink_to(outside)
    journal = EventJournal(linked, task_id="pd_test", ui_session_id="ui-1")
    assert journal.degraded and journal.ingest(frame("tool.start", {"tool_id": "t", "name": "terminal"})) is False
    assert outside.read_text(encoding="utf-8") == "safe"
    healthy = EventJournal(tmp_path / "healthy", task_id="pd_test", ui_session_id="ui-1")
    monkeypatch.setattr(healthy, "_write_bytes", lambda data: (_ for _ in ()).throw(OSError("disk full")))
    assert healthy.ingest(frame("tool.start", {"tool_id": "t", "name": "terminal"})) is False
    assert healthy.snapshot_fields()["observability_degraded"] is True


def test_pre_session_buffer_bounded_matching_only(tmp_path):
    journal = EventJournal(tmp_path, task_id="pd_test", max_pre_session_events=2, max_pre_session_bytes=10000)
    assert journal.ingest(frame("gateway.ready", {}, session_id="")) is False
    journal.ingest(frame("tool.start", {"tool_id": "other", "name": "terminal"}, session_id="other"))
    journal.ingest(frame("tool.start", {"tool_id": "mine", "name": "terminal"}, session_id="ui-1"))
    journal.ingest(frame("tool.start", {"tool_id": "overflow", "name": "terminal"}, session_id="ui-1"))
    journal.set_session("ui-1")
    journal.close()
    assert [item["payload"]["tool_id"] for item in records(tmp_path / "events.jsonl")] == ["mine"]
    assert journal.degraded


def test_terminal_flush_fsync_and_private_permissions(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(os, "fsync", lambda fd: calls.append(fd))
    journal = EventJournal(tmp_path, task_id="pd_test", ui_session_id="ui-1", persist_message_text=True)
    journal.ingest(frame("message.delta", {"message_id": "m", "text": "pending"}))
    journal.finalize("failed", error_code="code")
    assert [item["type"] for item in records(tmp_path / "events.jsonl")] == ["message.delta", "terminal"] and calls
    assert (tmp_path.stat().st_mode & 0o777) == 0o700
    assert ((tmp_path / "events.jsonl").stat().st_mode & 0o777) == ((tmp_path / "events.lock").stat().st_mode & 0o777) == 0o600
