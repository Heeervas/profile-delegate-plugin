"""Behavioral contract for the read-only Profile Delegate spectator."""
from __future__ import annotations

import argparse
import builtins
import importlib
import io
import json
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import cli
import event_journal
import spectator

TASK_ID = "pd_20260721_085059_dzk2o9"


def _write_fixture(
    root: Path, *, status: str = "completed", events: list[dict] | None = None,
    persist_message_text: bool = False,
) -> Path:
    run = root / TASK_ID
    run.mkdir(parents=True, mode=0o700)
    (run / "status.json").write_text(json.dumps({
        "task_id": TASK_ID, "status": status, "phase": status,
        "delegated_profile": "reviewer", "turn_count": 1, "tool_calls": 1,
    }), encoding="utf-8")
    if events is not None:
        lines = "".join(json.dumps(event) + "\n" for event in events)
        (run / "events.jsonl").write_text(lines, encoding="utf-8")
    (run / "request.json").write_text(
        json.dumps({"persist_message_text": persist_message_text}), encoding="utf-8",
    )
    if status in {"completed", "failed", "cancelled", "timed_out"}:
        (run / "result.json").write_text(json.dumps({
            "result_schema_version": 1, "task_id": TASK_ID,
            "status": "ok" if status == "completed" else "failed",
            "execution_status": status, "contract_status": "valid",
            "summary": "assistant summary", "error_code": "terminal-code",
            "session_id": "child-session", "artifacts": ["/private/artifact"],
            "errors": ["assistant error"], "next_steps": ["assistant next step"],
        }), encoding="utf-8")
    return run


def _event(seq: int, event_type: str = "lifecycle", **payload) -> dict:
    defaults = {
        "lifecycle": {"status": "running", "phase": "model_running"},
        "message.start": {"message_id": "m1", "role": "assistant"},
        "message.delta": {"message_id": "m1", "text": "visible"},
        "message.complete": {"message_id": "m1", "status": "complete"},
        "tool.start": {"tool_id": "t1", "tool": "terminal", "tool_class": "shell"},
        "tool.complete": {
            "tool_id": "t1", "tool": "terminal", "tool_class": "shell",
            "duration_s": 0.1, "outcome": "complete",
        },
        "session.info": {"profile": "reviewer"},
        "status.update": {"kind": "running"},
        "journal.truncated": {"reason": "limit", "dropped_after_seq": seq - 1},
        "terminal": {"status": "completed", "error_code": "", "child_session_id": "child"},
        "event.dropped": {"reason": "record_too_large"},
    }
    event_payload = dict(defaults[event_type])
    event_payload.update(payload)
    return {
        "schema_version": 1, "task_id": TASK_ID, "seq": seq,
        "at": "2026-07-21T08:53:10+00:00", "type": event_type,
        "phase": "model_running", "payload": event_payload, "redacted": False,
        "dropped_fields": [],
    }


def test_resolve_root_precedence_and_no_home_scan(tmp_path, monkeypatch):
    env_root = tmp_path / "env-runs"
    home = tmp_path / "caller-home"
    explicit = tmp_path / "explicit-runs"
    for root in (env_root, explicit, home / "profile_delegate" / "runs"):
        _write_fixture(root)
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(env_root))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "wrong-active-home"))

    assert spectator.resolve_spectator_run(TASK_ID) == env_root / TASK_ID
    assert spectator.resolve_spectator_run(TASK_ID, hermes_home=str(home)) == env_root / TASK_ID
    assert spectator.resolve_spectator_run(TASK_ID, runs_root=str(explicit)) == explicit / TASK_ID

    monkeypatch.delenv("PROFILE_DELEGATE_RUNS_ROOT")
    assert spectator.resolve_spectator_run(TASK_ID, hermes_home=str(home)) == home / "profile_delegate" / "runs" / TASK_ID


def test_resolve_rejects_invalid_missing_and_symlink(tmp_path, monkeypatch):
    monkeypatch.delenv("PROFILE_DELEGATE_RUNS_ROOT", raising=False)
    with pytest.raises(spectator.SpectatorError) as exc:
        spectator.resolve_spectator_run("../../etc/passwd", runs_root=str(tmp_path))
    assert exc.value.exit_code == 2
    with pytest.raises(spectator.SpectatorError) as exc:
        spectator.resolve_spectator_run(TASK_ID, runs_root=str(tmp_path))
    assert exc.value.exit_code == 2

    real = _write_fixture(tmp_path / "real")
    links = tmp_path / "links"
    links.mkdir()
    (links / TASK_ID).symlink_to(real, target_is_directory=True)
    with pytest.raises(spectator.SpectatorError) as exc:
        spectator.resolve_spectator_run(TASK_ID, runs_root=str(links))
    assert exc.value.exit_code == 3


def test_iter_events_reconnect_and_partial_tail(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(json.dumps(_event(1)) + "\n" + json.dumps(_event(2)) + "\n{\"seq\":3", encoding="utf-8")
    assert [event["seq"] for event in spectator.iter_events(path, after_seq=1)] == [2]


def test_iter_events_rejects_corrupt_complete_record(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text("not json\n", encoding="utf-8")
    with pytest.raises(spectator.SpectatorError) as exc:
        list(spectator.iter_events(path))
    assert exc.value.exit_code == 4


@pytest.mark.parametrize(
    "mutate",
    [
        lambda item: item.update({"prompt": "private"}),
        lambda item: item["payload"].update({"args": {"secret": "private"}}),
        lambda item: item.update({"redacted": "false"}),
        lambda item: item.update({"type": "unknown.event"}),
        lambda item: item.update({"phase": "unknown_phase"}),
        lambda item: item.update({"dropped_fields": ["private-secret"]}),
    ],
)
def test_iter_events_rejects_unknown_forbidden_or_invalid_schema_keys(tmp_path, mutate):
    item = _event(1, "tool.start")
    mutate(item)
    path = tmp_path / "events.jsonl"
    path.write_text(json.dumps(item) + "\n", encoding="utf-8")
    with pytest.raises(spectator.SpectatorError) as exc:
        list(spectator.iter_events(path))
    assert exc.value.exit_code == 4


def test_iter_events_requires_frozen_opt_in_before_exposing_message_text(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(json.dumps(_event(1, "message.delta", text="private")) + "\n", encoding="utf-8")
    with pytest.raises(spectator.SpectatorError) as exc:
        list(spectator.iter_events(path))
    assert exc.value.exit_code == 4
    assert [item["seq"] for item in spectator.iter_events(path, allow_message_text=True)] == [1]


def test_inspect_is_bounded_machine_readable_and_neutralizes_controls(tmp_path):
    run = _write_fixture(
        tmp_path, events=[_event(1, "message.delta", text="safe\x1b]8;;bad\x07link")],
        persist_message_text=True,
    )
    snapshot = spectator.inspect_run(run)
    encoded = json.dumps(snapshot)
    assert snapshot["task_id"] == TASK_ID
    assert snapshot["status"] == "completed"
    assert len(encoded) < 65536
    assert "\u001b" not in encoded and "\u0007" not in encoded
    assert "reasoning" not in encoded.lower()


def test_inspect_default_exposes_only_terminal_result_metadata(tmp_path):
    run = _write_fixture(tmp_path, events=[])
    snapshot = spectator.inspect_run(run)
    encoded = json.dumps(snapshot)
    assert snapshot["result"] == {
        "status": "ok", "execution_status": "completed", "contract_status": "valid",
        "error_code": "terminal-code", "session_id": "child-session",
    }
    for private in ("assistant summary", "/private/artifact", "assistant error", "assistant next step"):
        assert private not in encoded


def test_inspect_preserves_result_schema_v1_compatibility_without_new_orthogonal_fields(tmp_path):
    run = _write_fixture(tmp_path, events=[])
    result_path = run / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["status"] = "completed"
    result.pop("execution_status")
    result.pop("contract_status")
    result_path.write_text(json.dumps(result), encoding="utf-8")
    assert spectator.inspect_run(run)["result"]["status"] == "completed"


def test_inspect_frozen_opt_in_exposes_bounded_assistant_result_fields(tmp_path):
    run = _write_fixture(tmp_path, events=[], persist_message_text=True)
    result = spectator.inspect_run(run)["result"]
    assert result["summary"] == "assistant summary"
    assert result["artifacts"] == ["/private/artifact"]
    assert result["errors"] == ["assistant error"]
    assert result["next_steps"] == ["assistant next step"]


@pytest.mark.parametrize("mutation", ["empty", "missing_task_id", "missing_status", "mismatch"])
def test_inspect_rejects_invalid_current_result_identity_or_status_with_exit_4(
    tmp_path, capsys, mutation,
):
    run = _write_fixture(tmp_path, events=[])
    path = run / "result.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "empty":
        value = {}
    elif mutation == "missing_task_id":
        value.pop("task_id")
    elif mutation == "missing_status":
        value.pop("status")
    else:
        value["task_id"] = "pd_20260721_085059_other1"
    path.write_text(json.dumps(value), encoding="utf-8")
    parser = argparse.ArgumentParser(prog="hermes profile-delegate")
    cli.register_cli(parser)
    args = parser.parse_args(["inspect", TASK_ID, "--runs-root", str(tmp_path), "--json"])
    with pytest.raises(SystemExit) as exc:
        cli.profile_delegate_cli(args)
    assert exc.value.code == 4
    assert "corrupt result.json" in capsys.readouterr().err


def test_inspect_accepts_only_explicit_bounded_legacy_result_compatibility(tmp_path):
    run = _write_fixture(tmp_path, events=None)
    path = run / "result.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value.pop("result_schema_version")
    value.pop("task_id")
    path.write_text(json.dumps(value), encoding="utf-8")
    assert spectator.inspect_run(run)["result"]["status"] == "ok"


@pytest.mark.parametrize(
    ("artifact", "field", "bad_value"),
    [
        *(
            ("status.json", field, bad_value)
            for field, bad_value in {
                "task_id": [TASK_ID], "status": ["completed"], "phase": {"name": "completed"},
                "created_at": [], "started_at": {}, "ended_at": [], "delegated_profile": {},
                "profile": ["reviewer"], "model": {}, "provider": [], "turn_count": "1",
                "api_calls": {}, "tool_calls": [], "usage": {"input": "one"},
                "event_seq": "1", "event_schema_version": [], "event_stream_truncated": 1,
                "observability_degraded": "false", "error_code": {"secret": "nested"},
                "child_session_id": [], "worker_pid": "123",
            }.items()
        ),
        *(
            ("result.json", field, bad_value)
            for field, bad_value in {
                "status": ["ok"], "error_code": {"secret": "nested"},
                "session_id": ["child"], "summary": {},
                "artifacts": ["ok", {"secret": "nested"}], "errors": {},
                "next_steps": [1],
            }.items()
        ),
    ],
)
def test_inspect_rejects_wrong_typed_surfaced_status_and_result_fields(
    tmp_path, artifact, field, bad_value,
):
    run = _write_fixture(tmp_path, events=[], persist_message_text=True)
    path = run / artifact
    value = json.loads(path.read_text(encoding="utf-8"))
    value[field] = bad_value
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(spectator.SpectatorError) as exc:
        spectator.inspect_run(run)
    assert exc.value.exit_code == 4


@pytest.mark.parametrize("artifact", ["status.json", "events.jsonl"])
def test_inspect_rejects_artifact_task_identity_mismatch(tmp_path, artifact):
    run = _write_fixture(tmp_path, events=[_event(1)])
    path = run / artifact
    if artifact == "status.json":
        value = json.loads(path.read_text(encoding="utf-8"))
        value["task_id"] = "pd_20260721_085059_other1"
        path.write_text(json.dumps(value), encoding="utf-8")
    else:
        item = _event(1)
        item["task_id"] = "pd_20260721_085059_other1"
        path.write_text(json.dumps(item) + "\n", encoding="utf-8")
    with pytest.raises(spectator.SpectatorError) as exc:
        spectator.inspect_run(run)
    assert exc.value.exit_code == 4


@pytest.mark.parametrize("size", [8192, 8193, 32768])
def test_event_journal_message_text_boundaries_roundtrip_through_spectator(tmp_path, size):
    run = tmp_path / TASK_ID
    journal = event_journal.EventJournal(
        run, task_id=TASK_ID, ui_session_id="ui-1", persist_message_text=True,
        max_record_bytes=65536,
    )
    assert journal.ingest({
        "method": "event",
        "params": {
            "type": "message.complete", "session_id": "ui-1",
            "payload": {"message_id": "m1", "status": "complete", "text": "x" * size},
        },
    })
    journal.close()
    events = list(spectator.iter_events(
        run / "events.jsonl", allow_message_text=True, expected_task_id=TASK_ID,
    ))
    assert len(events[0]["payload"]["text"]) == size


def test_inspect_legacy_run_is_clearly_limited(tmp_path):
    run = _write_fixture(tmp_path, events=None)
    snapshot = spectator.inspect_run(run)
    assert snapshot["limited_observability"] is True
    assert "events.jsonl" in snapshot["observation_note"]


def test_watch_plain_emits_incremental_records_and_terminal_code(tmp_path):
    run = _write_fixture(tmp_path, events=[_event(1, "tool.start", tool="search_files", tool_id="t1")])
    out = io.StringIO()
    code = spectator.watch_run(run, output_mode="plain", poll_interval=0.01, stdout=out)
    text = out.getvalue()
    assert code == 0
    assert "search_files" in text
    assert "completed" in text
    assert "\x1b" not in text


@pytest.mark.parametrize(("status", "expected"), [("failed", 1), ("cancelled", 1), ("timed_out", 1)])
def test_watch_terminal_failure_codes(tmp_path, status, expected):
    run = _write_fixture(tmp_path, status=status, events=[])
    assert spectator.watch_run(run, output_mode="plain", poll_interval=0.01, stdout=io.StringIO()) == expected


def test_watch_jsonl_emits_sanitized_records_unchanged(tmp_path):
    event = _event(1, "tool.complete", tool="web_search", outcome="complete")
    run = _write_fixture(tmp_path, events=[event])
    out = io.StringIO()
    assert spectator.watch_run(run, output_mode="jsonl", poll_interval=0.01, stdout=out) == 0
    assert json.loads(out.getvalue().strip()) == event


def test_watch_tty_renders_bounded_event_ring_and_final_status(tmp_path, monkeypatch):
    events = [_event(index, "tool.start", tool=f"tool-{index}") for index in range(1, 30)]
    run = _write_fixture(tmp_path, status="running", events=events)
    statuses = iter([
        {"task_id": TASK_ID, "status": "running", "phase": "model_running", "tool_calls": 29},
        {"task_id": TASK_ID, "status": "completed", "phase": "completed", "tool_calls": 29},
    ])
    monkeypatch.setattr(spectator, "_status", lambda _run: next(statuses))
    monkeypatch.setattr(spectator.time, "sleep", lambda _interval: None)
    out = io.StringIO()
    assert spectator.watch_run(run, output_mode="tty", poll_interval=0.01, stdout=out) == 0
    rendered = out.getvalue()
    assert "Recent events" in rendered and "tool-29" in rendered
    assert "tool-1\n" not in rendered
    assert "status=completed" in rendered
    assert rendered.count("\x1b[2J\x1b[H") >= 2


@pytest.mark.parametrize("bad_status", [None, "", "unknown", "corrupt"])
def test_watch_and_inspect_reject_missing_or_unknown_status_without_looping(tmp_path, bad_status):
    run = _write_fixture(tmp_path, events=[])
    raw = {"task_id": TASK_ID, "phase": "running"}
    if bad_status is not None:
        raw["status"] = bad_status
    (run / "status.json").write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(spectator.SpectatorError) as inspect_exc:
        spectator.inspect_run(run)
    with pytest.raises(spectator.SpectatorError) as watch_exc:
        spectator.watch_run(run, output_mode="plain", poll_interval=0.01, stdout=io.StringIO())
    assert inspect_exc.value.exit_code == watch_exc.value.exit_code == 4


def test_spectator_opens_no_file_for_writing(tmp_path, monkeypatch):
    run = _write_fixture(tmp_path, events=[_event(1)])
    original_open = builtins.open
    original_path_open = Path.open

    def guarded_open(file, mode="r", *args, **kwargs):
        assert not any(flag in mode for flag in "wax+")
        return original_open(file, mode, *args, **kwargs)

    def guarded_path_open(self, mode="r", *args, **kwargs):
        assert not any(flag in mode for flag in "wax+")
        return original_path_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(Path, "open", guarded_path_open)
    spectator.inspect_run(run)
    spectator.watch_run(run, output_mode="plain", poll_interval=0.01, stdout=io.StringIO())


def test_spectator_has_no_transport_or_control_imports():
    source = (PLUGIN_DIR / "spectator.py").read_text(encoding="utf-8")
    assert "tui_rpc" not in source
    assert "session.resume" not in source
    assert "session.steer" not in source
    assert "control/" not in source


def test_register_cli_help_contract_and_only_v1_commands(capsys):
    parser = argparse.ArgumentParser(prog="hermes profile-delegate")
    cli.register_cli(parser)
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    for text in ("read-only", "watch", "inspect", "--jsonl", "inspect --json", "0..4", "Ctrl+C", "no assistant text"):
        assert text in help_text
    assert "list" not in parser._subparsers._group_actions[0].choices


def test_leaf_help_documents_options_and_dispatch_always_exits(capsys, tmp_path):
    _write_fixture(tmp_path, events=[])
    parser = argparse.ArgumentParser(prog="hermes profile-delegate")
    cli.register_cli(parser)
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["watch", "--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    for option in ("--runs-root", "--hermes-home", "--jsonl", "--poll-interval"):
        assert option in help_text

    args = parser.parse_args(["inspect", TASK_ID, "--runs-root", str(tmp_path), "--json"])
    with pytest.raises(SystemExit) as exc:
        cli.profile_delegate_cli(args)
    assert exc.value.code == 0
    assert json.loads(capsys.readouterr().out)["task_id"] == TASK_ID


def test_cli_errors_use_stderr_and_documented_code(tmp_path, capsys):
    parser = argparse.ArgumentParser(prog="hermes profile-delegate")
    cli.register_cli(parser)
    args = parser.parse_args(["inspect", TASK_ID, "--runs-root", str(tmp_path), "--json"])
    with pytest.raises(SystemExit) as exc:
        cli.profile_delegate_cli(args)
    captured = capsys.readouterr()
    assert exc.value.code == 2
    assert captured.out == ""
    assert "not found" in captured.err.lower()


@pytest.mark.parametrize("status", ["failed", "cancelled", "timed_out"])
def test_cli_inspect_uses_terminal_failure_exit_code(tmp_path, capsys, status):
    _write_fixture(tmp_path, status=status, events=[])
    parser = argparse.ArgumentParser(prog="hermes profile-delegate")
    cli.register_cli(parser)
    args = parser.parse_args(["inspect", TASK_ID, "--runs-root", str(tmp_path), "--json"])
    with pytest.raises(SystemExit) as exc:
        cli.profile_delegate_cli(args)
    assert exc.value.code == 1
    assert json.loads(capsys.readouterr().out)["status"] == status


def test_default_output_mode_uses_plain_when_not_tty(tmp_path):
    run = _write_fixture(tmp_path, events=[])

    class NonTTY(io.StringIO):
        def isatty(self):
            return False

    out = NonTTY()
    assert spectator.watch_run(run, output_mode="auto", poll_interval=0.01, stdout=out) == 0
    assert "\x1b" not in out.getvalue()


def test_module_is_python_310_compatible_surface():
    # Guard the most common accidental 3.11+ dependency for this stdlib-only module.
    assert not hasattr(importlib.import_module("spectator"), "tomllib")
