"""Status projection and detached completion must not trust mixed/legacy evidence."""
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core


def run_fixture(tmp_path, status="completed"):
    run = tmp_path / "pd_20260927_220206_aokwr9"
    run.mkdir()
    core.json_safe_write(run / "status.json", {"task_id": run.name, "status": status,
                                                 "background_worker_mode": "detached", "worker_pid": 113903})
    return run


@pytest.mark.parametrize("schema", [None, "bad", 1])
@pytest.mark.parametrize("operator", [False, True])
def test_unverified_result_never_projects_task_success(tmp_path, monkeypatch, schema, operator):
    run = run_fixture(tmp_path)
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path))
    candidate = {"status": "ok", "execution_status": "completed", "contract_status": "valid"}
    if schema is not None:
        candidate["result_schema_version"] = schema
    core.json_safe_write(run / "result.json", candidate)
    if not operator:
        # Exact-origin authorization is a separate, earlier gate.
        core.merge_run_status(run, {"origin": {"session_key": "lane"}})
    if schema is not None:
        with pytest.raises(core.ProfileDelegateError, match="invalid terminal result evidence"):
            core._read_run_status(run.name, operator=operator, caller_origin={"session_key": "lane"})
        return

    observed = core._read_run_status(run.name, operator=operator, caller_origin={"session_key": "lane"})
    assert observed["lookup_success"] is True
    assert observed["result"] == candidate  # Historical operator inspection survives.
    assert observed["result_verification"] == "legacy_unverified"
    assert observed["task_status"] == "unknown"
    assert observed["contract_status"] == "not_evaluated"
    assert observed["task_success"] is False


def test_detached_watcher_snapshots_repair_pair_before_native_notification(tmp_path, monkeypatch):
    run = run_fixture(tmp_path, "running")
    core.json_safe_write(run / "request.json", {"effective_policy": {"limits": {"max_async": 4}},
                                                   "notify_on_complete": True, "origin_session_key": "lane"})
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path))
    monkeypatch.setattr(core, "child_environment", lambda _depth: {})
    monkeypatch.setattr(core, "_process_identity", lambda _pid: {})
    monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: False)
    monkeypatch.setattr(core, "resolve_run_dir", lambda _task: run)
    exited = threading.Event()
    class Process:
        pid = 113903
        def wait(self):
            exited.wait(5)
            return 0
    monkeypatch.setattr(core.subprocess, "Popen", lambda *args, **kwargs: Process())
    before_lock, release = threading.Event(), threading.Event()
    original = core._locked_run_status
    @contextmanager
    def barrier(path):
        if threading.current_thread().name.startswith("profile-delegate-notify-"):
            before_lock.set()
            assert release.wait(5)
        with original(path) as status:
            yield status
    monkeypatch.setattr(core, "_locked_run_status", barrier)
    ledger = []
    queued = []
    notified = threading.Event()
    queued_event = threading.Event()
    def persist(event, result):
        ledger.append((event, result))
        notified.set()
    monkeypatch.setitem(sys.modules, "tools.async_delegation", SimpleNamespace(
        get_durable_delegation=lambda _task: ({"state": "completed", "delivery_state": "pending"}
                                                if ledger else {"state": "running"}),
        _persist_completion=persist,
    ))
    def queue(event):
        queued.append(event)
        queued_event.set()
    monkeypatch.setitem(sys.modules, "tools.process_registry", SimpleNamespace(
        process_registry=SimpleNamespace(completion_queue=SimpleNamespace(put=queue)),
    ))
    core._start_detached_background_worker(run)
    exited.set()
    try:
        assert before_lock.wait(5)
        repaired = core._operator_reconcile(run.name)
        assert repaired["reconciled"] is True
    finally:
        release.set()
    assert notified.wait(5)
    assert queued_event.wait(5)
    assert len(ledger) == 1
    event, result = ledger[0]
    persisted_status = core.operator_read_json(run / "status.json")
    persisted_result = core.operator_read_json(run / "result.json")
    assert event["exit_reason"] == persisted_status["status"] == persisted_result["execution_status"] == "failed"
    assert result == persisted_result
    assert event["status"] != "completed"
    assert len(queued) == 1
    assert queued[0]["delegation_id"] == event["delegation_id"]
    assert queued[0]["exit_reason"] == event["exit_reason"]
    assert queued[0]["status"] == event["status"]


@pytest.mark.parametrize("terminal", [False, True])
def test_detached_watcher_refuses_nonterminal_or_incoherent_pair(tmp_path, monkeypatch, terminal):
    run = run_fixture(tmp_path, "completed" if terminal else "running")
    core.json_safe_write(run / "request.json", {"effective_policy": {"limits": {"max_async": 4}}})
    if terminal:
        core.write_result_artifact(run, {"status": "ok", "execution_status": "failed",
                                         "contract_status": "valid"})
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path))
    monkeypatch.setattr(core, "child_environment", lambda _depth: {})
    monkeypatch.setattr(core, "_process_identity", lambda _pid: {})
    done = threading.Event()
    class Process:
        pid = 113903
        def wait(self):
            done.set()
            return 0
    monkeypatch.setattr(core.subprocess, "Popen", lambda *args, **kwargs: Process())
    notifications = []
    monkeypatch.setattr(core, "_push_profile_delegate_completion", lambda _run, final: notifications.append(final))
    watched = threading.Event()
    original = core._locked_run_status
    @contextmanager
    def observed_lock(path):
        with original(path) as status:
            yield status
        if threading.current_thread().name.startswith("profile-delegate-notify-"):
            watched.set()
    monkeypatch.setattr(core, "_locked_run_status", observed_lock)
    core._start_detached_background_worker(run)
    assert done.wait(5)
    assert watched.wait(5)
    assert notifications == []
