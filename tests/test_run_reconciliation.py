"""Regression coverage for bounded, locked operator repair."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import pytest
PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))
import core


def run_fixture(tmp_path: Path, *, status: str = "running", result: dict | None = None,
                worker_pid: int = 113903) -> Path:
    run = tmp_path / "pd_20260927_220206_aokwr9"
    run.mkdir()
    core.json_safe_write(run / "status.json", {"task_id": run.name, "status": status,
                                                "background_worker_mode": "detached", "worker_pid": worker_pid})
    if result is not None:
        core.write_result_artifact(run, result)
    return run


def replace_run_on_lock(tmp_path, monkeypatch, run, replace):
    """Replace the lock inode or run directory on the first exclusive lock."""
    original = core.fcntl.flock
    switched = False

    def flock(fd, operation):
        nonlocal switched
        if operation == core.fcntl.LOCK_EX and not switched:
            switched = True
            if replace == "lock":
                (run / "status.lock").unlink()
                (run / "status.lock").touch()
            else:
                run.rename(tmp_path / "retired")
        return original(fd, operation)

    monkeypatch.setattr(core.fcntl, "flock", flock)


@pytest.mark.parametrize("alive,reason", [(True, "worker_alive"), (None, "liveness_unverifiable")])
def test_unverified_worker_never_publishes(tmp_path, monkeypatch, alive, reason):
    run = run_fixture(tmp_path)
    original = (run / "status.json").read_bytes()
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task_id: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: alive)
    first = core._operator_reconcile(run.name)
    second = core._operator_reconcile(run.name)
    assert first == second
    assert first["reason"] == reason and first["reconciled"] is False
    assert (run / "status.json").read_bytes() == original
    assert not (run / "result.json").exists()


def test_dead_worker_synthesizes_conservative_result_and_idempotence(tmp_path, monkeypatch):
    run = run_fixture(tmp_path)
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task_id: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: False)
    first = core._operator_reconcile(run.name)
    assert first["status"] == "failed" and first["reconciled"] is True
    assert first["reason"] == "worker_died"
    result = core.operator_read_json(run / "result.json")
    assert result["status"] == "unknown" and result["execution_status"] == "failed"
    original = ((run / "status.json").read_bytes(), (run / "result.json").read_bytes())
    assert core._operator_reconcile(run.name)["reason"] == "already_terminal"
    assert original == ((run / "status.json").read_bytes(), (run / "result.json").read_bytes())


@pytest.mark.parametrize("task,execution", [("ok", "completed"), ("blocked", "completed"),
                                            ("failed", "failed"), ("unknown", "timed_out")])
def test_crash_intermediate_preserves_authoritative_worker_result(tmp_path, monkeypatch, task, execution):
    result = {"status": task, "execution_status": execution, "contract_status": "valid",
              "summary": "done", "artifacts": [], "errors": [], "next_steps": [], "structured": True}
    run = run_fixture(tmp_path, result=result)
    original_result = (run / "result.json").read_bytes()
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task_id: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: False)
    repaired = core._operator_reconcile(run.name)
    assert repaired["reason"] == "terminal_result_projected"
    assert repaired["status"] == execution and repaired["reconciled"] is True
    assert (run / "result.json").read_bytes() == original_result
    assert core._operator_reconcile(run.name)["reconciled"] is False
    assert (run / "result.json").read_bytes() == original_result


def test_invalid_result_evidence_fails_closed(tmp_path, monkeypatch):
    run = run_fixture(tmp_path)
    core.json_safe_write(run / "result.json", {"status": "ok", "execution_status": "completed"})
    original = (run / "result.json").read_bytes()
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task_id: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: False)
    with pytest.raises(core.ProfileDelegateError, match="invalid terminal result evidence"):
        core._operator_reconcile(run.name)
    assert (run / "result.json").read_bytes() == original
    assert json.loads((run / "status.json").read_text())["status"] == "running"


def test_terminal_status_is_idempotent_read_only(tmp_path, monkeypatch):
    run = run_fixture(tmp_path, status="failed")
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task_id: run)
    assert core._operator_reconcile(run.name)["reason"] == "already_terminal"
    assert core._operator_reconcile(run.name)["reconciled"] is False
    assert not (run / "result.json").exists()


def test_acknowledged_cancel_only(tmp_path, monkeypatch):
    run = run_fixture(tmp_path, status="cancelling")
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task_id: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: False)
    monkeypatch.setattr(core, "_cancel_evidence", lambda _run: (True, True))
    assert core._operator_reconcile(run.name)["status"] == "cancelled"
    assert core.operator_read_json(run / "result.json")["status"] == "unknown"


def test_mismatched_terminal_evidence_refused(tmp_path, monkeypatch):
    result = {"status": "ok", "execution_status": "completed", "contract_status": "valid"}
    run = run_fixture(tmp_path, status="failed", result=result)
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task_id: run)
    with pytest.raises(core.ProfileDelegateError, match="conflicting terminal evidence"):
        core._operator_reconcile(run.name)
