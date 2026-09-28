"""Cooperative lock barriers for dead-worker repair and terminal producers."""
import sys
import threading
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent))
import core


def run_fixture(tmp_path):
    run = tmp_path / "pd_20260927_220206_aokwr9"
    run.mkdir()
    core.json_safe_write(run / "status.json", {"task_id": run.name, "status": "running",
                                                "background_worker_mode": "detached", "worker_pid": 113903})
    return run


def worker(run):
    return core.publish_terminal_run(run, {"status": "blocked", "execution_status": "completed",
                                           "contract_status": "valid", "summary": "actual worker"},
                                     {"status": "completed", "phase": "completed", "ended_at": "worker"})


@pytest.mark.parametrize("publisher_first", [True, False])
@pytest.mark.parametrize("producer", ["worker", "failure", "startup"])
def test_repair_and_publisher_barrier(tmp_path, monkeypatch, publisher_first, producer):
    run = run_fixture(tmp_path)
    monkeypatch.setattr(core, "resolve_run_dir", lambda _: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _: False)
    def publish_failure(path):
        return core._mark_background_worker_failure(path, RuntimeError("worker failure"))

    def publish_startup(path):
        return core.publish_terminal_run(path, {"status": "failed", "execution_status": "failed",
                                                "contract_status": "not_evaluated", "summary": "startup failure"},
                                         {"status": "failed", "phase": "failed", "ended_at": "startup"})

    publish = {"worker": worker, "failure": publish_failure, "startup": publish_startup}[producer]
    acquired, resume = threading.Event(), threading.Event()
    original = core._validated_terminal_result
    names = []

    def barrier(path):
        if threading.current_thread().name == ("worker" if publisher_first else "repair") and not acquired.is_set():
            acquired.set()
            assert resume.wait(5)
        return original(path)

    monkeypatch.setattr(core, "_validated_terminal_result", barrier)
    def invoke(name):
        try:
            publish(run) if name == "worker" else core._operator_reconcile(run.name)
        except Exception as exc:
            names.append(exc)

    first_name = "worker" if publisher_first else "repair"
    second_name = "repair" if publisher_first else "worker"
    first = threading.Thread(target=invoke, args=(first_name,), name=first_name)
    second = threading.Thread(target=invoke, args=(second_name,), name=second_name)
    first.start()
    assert acquired.wait(5)
    second.start()
    resume.set()
    first.join(5)
    second.join(5)
    assert not first.is_alive() and not second.is_alive()
    status, result = core.operator_read_json(run / "status.json"), core.operator_read_json(run / "result.json")
    assert status["status"] == result["execution_status"]
    if publisher_first:
        assert not names
        if producer == "worker":
            assert result["status"] == "blocked" and result["summary"] == "actual worker"
        else:
            assert result["status"] == "failed" and status["status"] == "failed"
    else:
        # A worker that somehow attempts to publish after independently proven
        # dead must not overwrite the operator's conservative result.
        assert not names
        assert result["status"] == "unknown" and status["status"] == "failed"


@pytest.mark.parametrize("replace", ["lock", "run"])
def test_repair_refuses_lock_identity_change_while_waiting(tmp_path, monkeypatch, replace):
    run = run_fixture(tmp_path)
    monkeypatch.setattr(core, "resolve_run_dir", lambda _: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _: False)
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
    with pytest.raises(core.ProfileDelegateError):
        core._operator_reconcile(run.name)
    assert not (run / "result.json").exists()


def test_live_worker_with_result_remains_nonterminal(tmp_path, monkeypatch):
    run = run_fixture(tmp_path)
    core.write_result_artifact(run, {"status": "blocked", "execution_status": "completed",
                                     "contract_status": "valid"})
    original = ((run / "status.json").read_bytes(), (run / "result.json").read_bytes())
    monkeypatch.setattr(core, "resolve_run_dir", lambda _: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _: True)
    assert core._operator_reconcile(run.name)["reason"] == "worker_alive"
    assert original == ((run / "status.json").read_bytes(), (run / "result.json").read_bytes())


def test_reused_pid_identity_is_unverifiable(tmp_path, monkeypatch):
    run = run_fixture(tmp_path)
    status = core.operator_read_json(run / "status.json")
    status["worker_identity"] = "linux-proc:113903:old"
    core.json_safe_write(run / "status.json", status)
    monkeypatch.setattr(core, "resolve_run_dir", lambda _: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _: True)
    monkeypatch.setattr(core, "_process_identity", lambda _: "linux-proc:113903:new")
    assert core._operator_reconcile(run.name)["reason"] == "liveness_unverifiable"
    assert not (run / "result.json").exists()


def test_repair_result_first_crash_is_recoverable(tmp_path, monkeypatch):
    run = run_fixture(tmp_path)
    monkeypatch.setattr(core, "resolve_run_dir", lambda _: run)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _: False)
    original = core._write_locked_status_snapshot
    def crash(_run, _status):
        raise RuntimeError("after result")
    monkeypatch.setattr(core, "_write_locked_status_snapshot", crash)
    with pytest.raises(RuntimeError, match="after result"):
        core._operator_reconcile(run.name)
    assert core.operator_read_json(run / "status.json")["status"] == "running"
    result_bytes = (run / "result.json").read_bytes()
    monkeypatch.setattr(core, "_write_locked_status_snapshot", original)
    assert core._operator_reconcile(run.name)["status"] == "failed"
    assert (run / "result.json").read_bytes() == result_bytes
