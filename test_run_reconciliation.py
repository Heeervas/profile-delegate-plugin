"""Regression coverage for conservative dead-worker reconciliation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import core


def _write_run(tmp_path: Path, status: dict, result: dict | None = None) -> Path:
    run = tmp_path / status["task_id"]
    run.mkdir()
    core.json_safe_write(run / "status.json", status)
    if result is not None:
        core.write_result_artifact(run, result)
    return run


def _modern_status(task_id: str = "pd_20260727_220206_aokwr9") -> dict:
    return {
        "artifact_schema_version": 3,
        "task_id": task_id,
        "status": "running",
        "phase": "model_running",
        "background": True,
        "background_worker_mode": "detached",
        "transport": "tui_stdio",
        "worker_pid": 113903,
        "transport_pid": 113906,
        "transport_alive": True,
        "created_at": "2026-07-27T22:02:06+00:00",
    }


def test_reconcile_dead_modern_worker_without_result_fails_worker_died(tmp_path, monkeypatch):
    run = _write_run(tmp_path, _modern_status())
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task_id: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: False)

    outcome = core.profile_delegate_reconcile(run.name)

    assert outcome["reconciled"] is True
    assert outcome["status"] == "failed"
    assert outcome["reason"] == "worker_died"
    saved_status = json.loads((run / "status.json").read_text())
    saved_result = json.loads((run / "result.json").read_text())
    assert saved_status["error_code"] == "worker_died"
    assert saved_status["transport_alive"] is False
    assert saved_result["status"] == "unknown"
    assert saved_result["execution_status"] == "failed"
    assert saved_result["error_code"] == "worker_died"


def test_pending_cancel_does_not_reclassify_dead_worker_as_cancelled(tmp_path, monkeypatch):
    run = _write_run(tmp_path, _modern_status())
    command = run / "control" / "commands" / "000000000002-deadbeef.json"
    core.json_safe_write(command, {
        "schema_version": 1, "task_id": run.name, "type": "cancel",
        "command_id": "deadbeef", "seq": 2,
    })
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task_id: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: False)

    outcome = core.profile_delegate_reconcile(run.name)

    assert outcome["status"] == "failed"
    assert outcome["reason"] == "worker_died"
    assert outcome["pending_cancel"] is True


def test_reconcile_never_mutates_live_worker(tmp_path, monkeypatch):
    run = _write_run(tmp_path, _modern_status())
    before = (run / "status.json").read_bytes()
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task_id: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: True)

    outcome = core.profile_delegate_reconcile(run.name)

    assert outcome["reconciled"] is False
    assert outcome["reason"] == "worker_alive"
    assert (run / "status.json").read_bytes() == before
    assert not (run / "result.json").exists()


def test_reconcile_live_worker_with_terminal_result_still_does_not_mutate(tmp_path, monkeypatch):
    status = _modern_status("pd_20260727_220212_live")
    result = {
        "status": "ok", "execution_status": "completed", "contract_status": "valid",
        "summary": "done", "artifacts": [], "errors": [], "next_steps": [],
        "structured": True,
    }
    run = _write_run(tmp_path, status, result)
    before = (run / "status.json").read_bytes()
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task_id: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: True)

    outcome = core.profile_delegate_reconcile(run.name)

    assert outcome["reconciled"] is False
    assert outcome["reason"] == "worker_alive"
    assert (run / "status.json").read_bytes() == before


def test_reconcile_unverifiable_worker_with_terminal_result_is_noop(tmp_path, monkeypatch):
    status = _modern_status("pd_20260727_220212_unknown")
    result = {
        "status": "ok", "execution_status": "completed", "contract_status": "valid",
        "summary": "done", "artifacts": [], "errors": [], "next_steps": [],
        "structured": True,
    }
    run = _write_run(tmp_path, status, result)
    before = (run / "status.json").read_bytes()
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task_id: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: None)

    outcome = core.profile_delegate_reconcile(run.name)

    assert outcome["reconciled"] is False
    assert outcome["reason"] == "liveness_unverifiable"
    assert (run / "status.json").read_bytes() == before


def test_reconcile_legacy_unknown_without_worker_evidence_is_noop(tmp_path, monkeypatch):
    status = {
        "task_id": "pd_20260618_064147_nrl7k0",
        "status": "running",
        "created_at": "2026-06-18T06:41:47+00:00",
    }
    run = _write_run(tmp_path, status)
    before = (run / "status.json").read_bytes()
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task_id: run)

    outcome = core.profile_delegate_reconcile(run.name)

    assert outcome["reconciled"] is False
    assert outcome["reason"] == "liveness_unverifiable"
    assert (run / "status.json").read_bytes() == before


def test_valid_terminal_result_is_authoritative_over_stale_status(tmp_path, monkeypatch):
    status = _modern_status("pd_20260727_220207_result")
    result = {
        "status": "unknown", "execution_status": "completed",
        "contract_status": "drifted", "summary": "useful Markdown",
        "artifacts": [], "errors": [], "next_steps": [], "structured": False,
    }
    run = _write_run(tmp_path, status, result)
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task_id: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: False)

    outcome = core.profile_delegate_reconcile(run.name)

    assert outcome["reconciled"] is True
    assert outcome["status"] == "completed"
    assert outcome["reason"] == "terminal_result_authority"
    saved = json.loads((run / "status.json").read_text())
    assert saved["status"] == "completed"
    assert saved["error_code"] is None


def test_acknowledged_cancel_is_authoritative(tmp_path, monkeypatch):
    run = _write_run(tmp_path, _modern_status("pd_20260727_220208_cancel"))
    command = run / "control" / "commands" / "000000000001-deadbeef.json"
    ack = run / "control" / "acks" / command.name
    core.json_safe_write(command, {"type": "cancel", "command_id": "deadbeef", "seq": 1})
    core.json_safe_write(ack, {"type": "cancel", "command_id": "deadbeef", "seq": 1, "state": "accepted"})
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task_id: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: False)

    outcome = core.profile_delegate_reconcile(run.name)

    assert outcome["status"] == "cancelled"
    assert outcome["reason"] == "cancel_acknowledged"
    result = json.loads((run / "result.json").read_text())
    assert result["status"] == "unknown"
    assert result["execution_status"] == "cancelled"


def test_mismatched_cancel_ack_is_not_authoritative(tmp_path, monkeypatch):
    run = _write_run(tmp_path, _modern_status("pd_20260727_220208_mismatch"))
    command = run / "control" / "commands" / "000000000001-deadbeef.json"
    ack = run / "control" / "acks" / command.name
    core.json_safe_write(command, {
        "type": "cancel", "command_id": "deadbeef", "seq": 1,
    })
    core.json_safe_write(ack, {
        "type": "cancel", "command_id": "wrong", "seq": 1, "state": "accepted",
    })
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task_id: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: False)

    outcome = core.profile_delegate_reconcile(run.name)

    assert outcome["status"] == "failed"
    assert outcome["reason"] == "worker_died"
    assert outcome["cancel_acknowledged"] is False


def test_invalid_terminal_result_cannot_override_stale_status(tmp_path, monkeypatch):
    status = _modern_status("pd_20260727_220208_badresult")
    run = _write_run(tmp_path, status)
    core.json_safe_write(run / "result.json", {
        "status": "unknown", "execution_status": "completed", "summary": "not authoritative",
    })
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task_id: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: False)

    outcome = core.profile_delegate_reconcile(run.name)

    assert outcome["status"] == "failed"
    assert outcome["reason"] == "worker_died"
    saved = json.loads((run / "result.json").read_text())
    assert saved["execution_status"] == "failed"
    assert saved["result_schema_version"] == core.RESULT_SCHEMA_VERSION


def test_reconcile_terminal_run_is_idempotent(tmp_path, monkeypatch):
    status = _modern_status("pd_20260727_220209_done")
    status.update({"status": "failed", "phase": "failed", "error_code": "worker_died"})
    run = _write_run(tmp_path, status)
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task_id: run)

    outcome = core.profile_delegate_reconcile(run.name)

    assert outcome["reconciled"] is False
    assert outcome["reason"] == "already_terminal"
    assert outcome["status"] == "failed"


def test_duplicate_guard_reconciles_recent_dead_match(tmp_path, monkeypatch):
    status = _modern_status("pd_20260727_220210_dupe")
    status["request_fingerprint"] = "abc"
    status["created_at"] = core.now_iso()
    run = _write_run(tmp_path, status)
    monkeypatch.setattr(core, "iter_run_dirs", lambda: [run])
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task_id: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: False)

    assert core._active_matching_run("abc", 120) is None
    saved = json.loads((run / "status.json").read_text())
    assert saved["status"] == "failed"
    assert saved["error_code"] == "worker_died"


def test_reconcile_does_not_delete_artifacts(tmp_path, monkeypatch):
    run = _write_run(tmp_path, _modern_status("pd_20260727_220211_keep"))
    evidence = run / "events.jsonl"
    evidence.write_text('{"type":"tool.complete"}\n', encoding="utf-8")
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task_id: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: False)

    core.profile_delegate_reconcile(run.name)

    assert evidence.read_text(encoding="utf-8") == '{"type":"tool.complete"}\n'
    assert run.is_dir()
