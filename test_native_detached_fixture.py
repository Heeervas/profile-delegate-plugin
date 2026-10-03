"""Explicit detached test shim stays fixture-only."""
import json
import os
import sqlite3
import time
from pathlib import Path
from contextlib import closing
import core
import pytest


@pytest.fixture
def native_caller(tmp_path, monkeypatch):
    from hermes_state import SessionDB
    from tools import async_delegation
    caller = tmp_path / "caller"
    caller.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(caller))
    assert async_delegation._db_path() == caller / "state.db"
    store = SessionDB(db_path=caller / "state.db")
    try:
        yield caller
    finally:
        store.close()


@pytest.mark.parametrize("notify", [True, False])
def test_detached_background_worker_finalizes_completed_run(tmp_path, monkeypatch, native_caller, notify):
    caller = native_caller
    launched = []
    original_popen = core.subprocess.Popen
    def launch(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        launched.append(process)
        return process
    monkeypatch.setattr(core.subprocess, "Popen", launch)
    original_write = core.json_safe_write

    def explicit_test_write(path, value):
        if Path(path).name == "request.json":
            value = {**value, "test_shim": True}
        return original_write(path, value)

    # Explicit persisted fixture-only bypass for the detached test worker.
    monkeypatch.setattr(core, "json_safe_write", explicit_test_write)
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setenv("PROFILE_DELEGATE_BACKGROUND_TRANSPORT", "cli")
    monkeypatch.delenv("PROFILE_DELEGATE_BACKGROUND_MODE", raising=False)
    monkeypatch.setattr(core, "validate_profile", lambda profile, policy=None: core.ValidatedProfile(profile, profile, str(tmp_path / profile)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)
    monkeypatch.setenv("PROFILE_DELEGATE_HERMES_BIN", "/bin/echo")

    result = core.delegate_profile("reviewer", "task", session_title="detached", background=True, notify_on_complete=notify, origin_session_key="fixture:lane", transport_mode="simple")
    assert result["mode"] == "async"
    run_dir = Path(result["paths"]["run_dir"])

    status = {}
    for _ in range(100):
        status = json.loads((run_dir / "status.json").read_text())
        if status.get("status") == "completed":
            break
        time.sleep(0.05)
    assert status["status"] == "completed"
    assert status["background_worker_mode"] == "detached"
    assert status["ended_at"]
    saved = json.loads((run_dir / "result.json").read_text())
    assert saved["status"] == "unknown"
    assert saved["execution_status"] == "completed"
    assert saved["structured"] is False
    assert saved["contract_status"] == "drifted"
    assert (run_dir / "result.json").exists()

    with closing(sqlite3.connect(caller / "state.db")) as conn:
        row = conn.execute("SELECT owner_pid FROM async_delegations WHERE delegation_id=?", (run_dir.name,)).fetchone()
    if notify:
        assert row[0] == launched[0].pid and row[0] != os.getpid()
    else:
        assert row is None and status["notification_status"] == "disabled"
    launched[0].wait(timeout=5)


def test_native_completion_survives_launcher_exit(tmp_path, monkeypatch, native_caller):
    import queue
    import subprocess
    import sys
    from tools import async_delegation

    caller = native_caller
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setenv("PROFILE_DELEGATE_BACKGROUND_MODE", "detached")
    monkeypatch.setenv("PROFILE_DELEGATE_HERMES_BIN", "/bin/echo")
    assert async_delegation._db_path() == caller / "state.db"
    # Real launcher/worker/native ledger; only the provider workload is replaced.
    child_code = '''
import pathlib,sys,time
sys.path.insert(0, "/opt/hermes")
sys.path.insert(0, sys.argv[1])
import core
run = pathlib.Path(sys.argv[2])
def execute(path):
    (run / "ready").touch()
    deadline = time.monotonic() + 10
    while not (run / "release").exists():
        if time.monotonic() > deadline:
            raise RuntimeError("fixture release deadline")
        time.sleep(.01)
    return core.finish_run(run, core.read_json_file(run / "request.json"),
                           {"status": "ok", "execution_status": "completed", "contract_status": "valid", "summary": "done"},
                           {"status": "completed", "phase": "completed", "ended_at": core.now_iso()}, mode="async")
core._execute_delegate_run = execute
raise SystemExit(core._background_worker_main(str(run)))
'''
    launcher_code = '''
import json,pathlib,sys
sys.path.insert(0, "/opt/hermes")
sys.path.insert(0, sys.argv[1])
import core
root = pathlib.Path(sys.argv[2])
core.validate_profile = lambda profile, policy=None: core.ValidatedProfile(profile, profile, str(root / "target"))
core.resolve_workdir = lambda workdir="", policy=None: root
original = core.subprocess.Popen
def spawn(command, *args, **kwargs):
    if "--background-worker" in command:
        command = [sys.executable, "-c", sys.argv[3], sys.argv[1], command[-1]]
    return original(command, *args, **kwargs)
core.subprocess.Popen = spawn
response = core.delegate_profile("reviewer", "fixture", session_title="owner exit", background=True,
                                 notify_on_complete=True, origin_session_key="fixture:lane", transport_mode="simple")
print(json.dumps(response))
'''
    launcher = subprocess.run([sys.executable, "-c", launcher_code, str(Path(core.__file__).parent), str(tmp_path), child_code],
                              capture_output=True, text=True, timeout=10)
    assert launcher.returncode == 0, launcher.stderr
    response = json.loads(launcher.stdout)
    run = Path(response["paths"]["run_dir"])
    deadline = time.monotonic() + 10
    try:
        while not (run / "ready").exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert (run / "ready").exists()
        assert async_delegation.recover_abandoned_delegations() == 0
        assert async_delegation.get_durable_delegation(run.name)["state"] == "running"
    finally:
        (run / "release").touch()
    while time.monotonic() < deadline:
        row = async_delegation.get_durable_delegation(run.name)
        if row["state"] == "completed":
            break
        time.sleep(.01)
    assert row["state"] == "completed" and row["result"]["status"] == "ok"
    completions = queue.Queue()
    assert async_delegation.restore_undelivered_completions(completions) == 1
    assert completions.get_nowait()["status"] == "completed"


def test_background_thread_preserves_native_caller_home(tmp_path, monkeypatch):
    import threading
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from tools import async_delegation
    run = tmp_path / "run"
    run.mkdir()
    core.json_safe_write(run / "request.json", {})
    seen, threads = [], []
    real_thread = threading.Thread
    def thread(*args, **kwargs):
        worker = real_thread(*args, **kwargs)
        threads.append(worker)
        return worker
    monkeypatch.setattr(core.threading, "Thread", thread)
    monkeypatch.setattr(core, "_register_durable_notification", lambda path: seen.append(async_delegation._db_path()))
    monkeypatch.setattr(core, "_execute_delegate_run", lambda path: {})
    monkeypatch.setattr(core, "_push_profile_delegate_completion", lambda *args: None)
    monkeypatch.setattr(core, "_async_running", 0)
    token = set_hermes_home_override(tmp_path / "context-caller")
    try:
        core._start_background_thread(run)
        threads[0].join(timeout=5)
        assert not threads[0].is_alive()
        assert seen == [tmp_path / "context-caller" / "state.db"]
        assert core._async_running == 0
    finally:
        reset_hermes_home_override(token)
