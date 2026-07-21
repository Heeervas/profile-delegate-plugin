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
import spectator

TASK_ID = "pd_20260721_085059_dzk2o9"


def _write_fixture(root: Path, *, status: str = "completed", events: list[dict] | None = None) -> Path:
    run = root / TASK_ID
    run.mkdir(parents=True, mode=0o700)
    (run / "status.json").write_text(json.dumps({
        "task_id": TASK_ID, "status": status, "phase": status,
        "delegated_profile": "reviewer", "turn_count": 1, "tool_calls": 1,
    }), encoding="utf-8")
    if events is not None:
        lines = "".join(json.dumps(event) + "\n" for event in events)
        (run / "events.jsonl").write_text(lines, encoding="utf-8")
    if status in {"completed", "failed", "cancelled", "timed_out"}:
        (run / "result.json").write_text(json.dumps({"status": status, "summary": "done"}), encoding="utf-8")
    return run


def _event(seq: int, event_type: str = "lifecycle", **payload) -> dict:
    return {
        "schema_version": 1, "task_id": TASK_ID, "seq": seq,
        "at": "2026-07-21T08:53:10+00:00", "type": event_type,
        "phase": "model_running", "payload": payload, "redacted": False,
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


def test_inspect_is_bounded_machine_readable_and_neutralizes_controls(tmp_path):
    run = _write_fixture(tmp_path, events=[_event(1, "message.delta", text="safe\x1b]8;;bad\x07link")])
    snapshot = spectator.inspect_run(run)
    encoded = json.dumps(snapshot)
    assert snapshot["task_id"] == TASK_ID
    assert snapshot["status"] == "completed"
    assert len(encoded) < 65536
    assert "\u001b" not in encoded and "\u0007" not in encoded
    assert "reasoning" not in encoded.lower()


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
