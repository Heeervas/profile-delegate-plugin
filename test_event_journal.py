"""Contract tests for the bounded Profile Delegate spectator event journal."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import event_journal
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
    assert sum(item["type"] == "journal.truncated" for item in saved) == 1
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


def test_gateway_shaped_sequence_reconciles_identity_turn_and_final_usage(tmp_path):
    journal = EventJournal(tmp_path, task_id="pd_test", ui_session_id="ui-1")
    journal.ingest(frame("message.start", {}))
    journal.ingest(frame("session.info", {
        "profile_name": "reviewer", "model": "model-x", "provider": "provider-y",
        "usage": {"input": 1, "output": 2, "total": 3, "calls": 1},
    }))
    journal.ingest(frame("message.complete", {
        "text": "private by default", "status": "complete", "rendered": ["private"],
        "reasoning": "hidden", "usage": {"input": 10, "output": 5, "reasoning": 2, "total": 17, "calls": 3},
    }))
    snapshot = journal.snapshot_fields()
    journal.close()
    saved = records(tmp_path / "events.jsonl")
    assert snapshot["turn_count"] == 1
    assert snapshot["delegated_profile"] == "reviewer"
    assert snapshot["model"] == "model-x" and snapshot["provider"] == "provider-y"
    assert snapshot["usage"] == {"input": 10, "output": 5, "reasoning": 2, "total": 17, "calls": 3}
    assert snapshot["api_calls"] == 3
    assert saved[0]["payload"] == {"role": "assistant"}
    assert saved[-1]["payload"] == {"status": "complete", "usage": snapshot["usage"]}
    assert set(saved[-1]["dropped_fields"]) == {"text", "reasoning", "rendered"}


def test_terminal_record_is_allowed_after_exact_ordinary_event_cap(tmp_path):
    journal = EventJournal(
        tmp_path, task_id="pd_test", ui_session_id="ui-1",
        max_events=2, max_bytes=4096, terminal_reserve_bytes=1024,
    )
    assert journal.ingest(frame("tool.start", {"tool_id": "one", "name": "terminal"}))
    assert journal.ingest(frame("tool.start", {"tool_id": "two", "name": "terminal"}))
    assert not journal.ingest(frame("tool.start", {"tool_id": "three", "name": "terminal"}))
    assert journal.finalize("completed", child_session_id="child")
    saved = records(tmp_path / "events.jsonl")
    assert sum(item["type"] not in {"terminal", "journal.truncated"} for item in saved) == 2
    assert sum(item["type"] == "journal.truncated" for item in saved) == 1
    assert saved[-1]["type"] == "terminal"
    assert (tmp_path / "events.jsonl").stat().st_size <= 4096


def _persisted_text(path):
    return "".join(
        item["payload"].get("text", "")
        for item in records(path)
        if item["type"] == "message.delta"
    )


@pytest.mark.parametrize("boundary", ["size", "timer", "intervening"])
def test_split_secret_is_not_emitted_raw_across_flush_boundaries(tmp_path, monkeypatch, boundary):
    clock = [0.0]
    monkeypatch.setattr(event_journal.time, "monotonic", lambda: clock[0])
    kwargs = {"coalesce_chars": 7} if boundary == "size" else {"flush_interval_s": 0.1}
    journal = EventJournal(
        tmp_path, task_id="pd_test", ui_session_id="ui-1",
        persist_message_text=True, **kwargs,
    )
    journal.ingest(frame("message.delta", {"text": "tok"}))
    if boundary == "timer":
        clock[0] = 1.0
        journal.flush()
    elif boundary == "intervening":
        journal.ingest(frame("tool.start", {"tool_id": "t", "name": "terminal"}))
    journal.ingest(frame("message.delta", {"text": "en=obvious-secret"}))
    journal.ingest(frame("message.complete", {"status": "complete"}))
    journal.close()
    persisted = _persisted_text(tmp_path / "events.jsonl")
    assert "obvious-secret" not in persisted
    assert "[REDACTED]" in persisted


def test_coalescing_flushes_on_char_and_timer_thresholds(tmp_path, monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(event_journal.time, "monotonic", lambda: clock[0])
    journal = EventJournal(
        tmp_path, task_id="pd_test", ui_session_id="ui-1",
        persist_message_text=True, coalesce_chars=5, flush_interval_s=0.1,
    )
    journal.ingest(frame("message.delta", {"message_id": "m", "text": "12345"}))
    assert [item["type"] for item in records(tmp_path / "events.jsonl")] == ["message.delta"]
    journal.ingest(frame("message.delta", {"message_id": "m", "text": "later"}))
    clock[0] += 0.2
    journal.flush()
    assert [item["type"] for item in records(tmp_path / "events.jsonl")] == [
        "message.delta", "message.delta",
    ]
    journal.close()


def test_non_delta_event_is_not_deferred_and_visible_order_is_preserved(tmp_path):
    journal = EventJournal(
        tmp_path, task_id="pd_test", ui_session_id="ui-1",
        persist_message_text=True, coalesce_chars=4096, flush_interval_s=10,
    )
    journal.ingest(frame("message.delta", {"message_id": "m", "text": "before tool"}))
    journal.ingest(frame("tool.start", {"tool_id": "t", "name": "terminal"}))
    assert [item["type"] for item in records(tmp_path / "events.jsonl")] == [
        "message.delta", "tool.start",
    ]
    journal.close()


def test_positive_short_write_degrades_and_reopen_recovers_partial_tail(tmp_path, monkeypatch):
    journal = EventJournal(tmp_path, task_id="pd_test", ui_session_id="ui-1")
    real_write = event_journal.os.write
    monkeypatch.setattr(event_journal.os, "write", lambda fd, data: real_write(fd, data[: max(1, len(data) // 2)]))
    assert journal.ingest(frame("tool.start", {"tool_id": "partial", "name": "terminal"})) is False
    assert journal.degraded
    journal.close()
    monkeypatch.setattr(event_journal.os, "write", real_write)
    reopened = EventJournal(tmp_path, task_id="pd_test", ui_session_id="ui-1")
    assert reopened.ingest(frame("tool.start", {"tool_id": "whole", "name": "terminal"}))
    reopened.close()
    assert [item["seq"] for item in records(tmp_path / "events.jsonl")] == [1]


def test_second_writer_refreshes_sequence_and_cap_state_under_lock(tmp_path):
    first = EventJournal(tmp_path, task_id="pd_test", ui_session_id="ui-1", max_events=2)
    second = EventJournal(tmp_path, task_id="pd_test", ui_session_id="ui-1", max_events=2)
    assert first.ingest(frame("tool.start", {"tool_id": "one", "name": "terminal"}))
    assert second.ingest(frame("tool.start", {"tool_id": "two", "name": "terminal"}))
    assert not first.ingest(frame("tool.start", {"tool_id": "three", "name": "terminal"}))
    first.close()
    second.close()
    saved = records(tmp_path / "events.jsonl")
    assert [item["seq"] for item in saved] == [1, 2]


def test_recovery_reads_only_bounded_tail_for_last_record(tmp_path, monkeypatch):
    journal = EventJournal(tmp_path, task_id="pd_test", ui_session_id="ui-1")
    for index in range(100):
        journal.ingest(frame("tool.start", {"tool_id": str(index), "name": "terminal"}))
    journal.close()
    read_sizes = []
    real_read = event_journal.os.read
    monkeypatch.setattr(event_journal.os, "read", lambda fd, size: (read_sizes.append(size), real_read(fd, size))[1])
    reopened = EventJournal(tmp_path, task_id="pd_test", ui_session_id="ui-1")
    assert reopened.seq == 100
    assert max(read_sizes, default=0) <= 65536
    reopened.close()
