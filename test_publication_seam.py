"""Deterministic cooperative terminal-publication race and crash tests."""
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
from test_run_reconciliation import replace_run_on_lock, run_fixture


def success():
    return {"status": "ok", "execution_status": "completed", "contract_status": "valid",
            "summary": "worker", "artifacts": [], "errors": [], "next_steps": []}


def publish(run):
    return core.publish_terminal_run(run, success(), {"status": "completed", "phase": "completed", "ended_at": "worker"})


def test_failure_cannot_replace_worker_result_or_terminal_fields(tmp_path):
    run = run_fixture(tmp_path, worker_pid=-1)
    publish(run)
    original = (run / "result.json").read_bytes()
    final = core._mark_background_worker_failure(run, RuntimeError("late"))
    assert final["status"] == "completed" and final["success"] is True
    assert (run / "result.json").read_bytes() == original
    assert core.merge_run_status(run, {"status": "failed", "phase": "failed", "ended_at": "late",
                                      "error_code": "late", "notification_status": "queued"})["status"] == "completed"
    assert core.read_json_file(run / "status.json")["ended_at"] == "worker"


def test_result_before_status_crash_preserves_authority(tmp_path, monkeypatch):
    run = run_fixture(tmp_path, worker_pid=-1)
    real = core._write_locked_status_snapshot
    def crash(path, snapshot):
        if snapshot["status"] == "completed":
            raise RuntimeError("simulated crash after result rename")
        return real(path, snapshot)
    monkeypatch.setattr(core, "_write_locked_status_snapshot", crash)
    with pytest.raises(RuntimeError):
        publish(run)
    assert core.read_json_file(run / "status.json")["status"] == "running"
    monkeypatch.setattr(core, "_write_locked_status_snapshot", real)
    with pytest.raises(core.ProfileDelegateError, match="operator repair required"):
        core._mark_background_worker_failure(run, RuntimeError("late"))
    assert core.read_json_file(run / "status.json")["status"] == "running"
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task_id: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: False)
    core.json_safe_write(run / "status.json", {"task_id": run.name, "status": "running",
                                                "background_worker_mode": "detached", "worker_pid": 113903})
    assert core._operator_reconcile(run.name)["reason"] == "terminal_result_projected"
    assert core.read_json_file(run / "result.json")["summary"] == "worker"
    assert core.read_json_file(run / "status.json")["status"] == "completed"


def test_invalid_result_never_overwritten(tmp_path):
    run = run_fixture(tmp_path, worker_pid=-1)
    core.json_safe_write(run / "result.json", {"status": "ok"})
    original = (run / "result.json").read_bytes()
    with pytest.raises(core.ProfileDelegateError, match="invalid terminal result evidence"):
        publish(run)
    assert (run / "result.json").read_bytes() == original
    assert core.read_json_file(run / "status.json")["status"] == "running"


@pytest.mark.parametrize("replace", ["lock", "run"])
def test_waiting_publication_rejects_replaced_lock_or_run(tmp_path, monkeypatch, replace):
    run = run_fixture(tmp_path, worker_pid=-1)
    replace_run_on_lock(tmp_path, monkeypatch, run, replace)
    with pytest.raises(core.ProfileDelegateError):
        publish(run)
    assert not (run / "result.json").exists()


def test_paired_read_waits_for_publication(tmp_path, monkeypatch):
    run = run_fixture(tmp_path, worker_pid=-1)
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path))
    inside = threading.Event()
    proceed = threading.Event()
    original = core._write_locked_status_snapshot
    def block(run_dir, status):
        if status["status"] == "completed":
            inside.set()
            assert proceed.wait(5)
        return original(run_dir, status)
    monkeypatch.setattr(core, "_write_locked_status_snapshot", block)
    read_result = core.operator_read_json
    result_reads = []
    def replace_after_read(path, *args, **kwargs):
        result = read_result(path, *args, **kwargs)
        if path == run / "result.json":
            result_reads.append(result)
            if len(result_reads) == 1:
                core.json_safe_write(path, {**result, "status": "blocked", "summary": "replacement"})
        return result
    monkeypatch.setattr(core, "operator_read_json", replace_after_read)
    writer = threading.Thread(target=lambda: publish(run))
    writer.start()
    assert inside.wait(5)
    observed = []
    reader = threading.Thread(target=lambda: observed.append(core._read_run_status(run.name, operator=True)))
    reader.start()
    reader.join(0.05)
    assert not observed
    proceed.set()
    writer.join(5)
    reader.join(5)
    assert not writer.is_alive() and not reader.is_alive()
    assert observed[0]["status"] == observed[0]["result"]["execution_status"] == "completed"
    assert observed[0]["task_status"] == observed[0]["result"]["status"] == "ok"
    assert observed[0]["task_success"] is True
    assert len(result_reads) == 1
