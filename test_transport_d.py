"""Steer-first transport selection and owned detached CLI cancellation regressions."""
import os
import subprocess
import sys
import threading
import time

import pytest

import core


def _run(tmp_path, *, transport="cli", group=None):
    run = tmp_path / "pd_20260927_150000_steerd"
    run.mkdir()
    core.json_safe_write(run / "status.json", {
        "task_id": run.name, "status": "running", "transport": transport,
        "background": True, "background_worker_mode": "detached",
        "worker_pid": os.getpid(), "process_group_identity": group,
    })
    return run


def test_detached_simple_refuses_unverifiable_identity_before_enqueue(tmp_path, monkeypatch):
    run = _run(tmp_path, group="linux-group:wrong")
    monkeypatch.setattr(core, "authorize_run", lambda *args: "test")
    with pytest.raises(core.ProfileDelegateError) as exc:
        core._write_control_command(run, "cancel", {}, None)
    assert exc.value.code == "control_identity_unverifiable"
    assert not (run / "control" / "commands" / "next_seq.json").exists()


def test_detached_simple_identity_pending_refuses_without_enqueuing(tmp_path, monkeypatch):
    run = _run(tmp_path)
    monkeypatch.setattr(core, "authorize_run", lambda *args: "test")
    with pytest.raises(core.ProfileDelegateError) as exc:
        core._write_control_command(run, "cancel", {}, None)
    assert exc.value.code == "control_identity_pending"
    assert not (run / "control" / "commands" / "next_seq.json").exists()


def test_detached_simple_worker_death_or_changed_identity_refuses(tmp_path, monkeypatch):
    run = _run(tmp_path)
    monkeypatch.setattr(core, "authorize_run", lambda *args: "test")
    core.merge_run_status(run, {"process_group_identity": "linux-group:changed"})
    for _ in range(2):
        with pytest.raises(core.ProfileDelegateError) as exc:
            core._write_control_command(run, "cancel", {}, None)
        assert exc.value.code == "control_identity_unverifiable"
    assert not (run / "control" / "commands" / "next_seq.json").exists()


def test_detached_spawn_to_identity_barrier_refuses_without_signal(tmp_path, monkeypatch):
    run = _run(tmp_path)
    monkeypatch.setattr(core, "authorize_run", lambda *args: "test")
    entered, release = threading.Event(), threading.Event()
    actual_popen = core.subprocess.Popen

    def blocked_spawn(*args, **kwargs):
        proc = actual_popen(*args, **kwargs)
        entered.set()
        assert release.wait(3)
        return proc

    monkeypatch.setattr(core.subprocess, "Popen", blocked_spawn)
    results = []
    thread = threading.Thread(target=lambda: results.append(core.run_capped_subprocess(
        [sys.executable, "-c", "import time; time.sleep(10)"], tmp_path,
        os.environ.copy(), 2, run / "stdout.txt", run / "stderr.txt",
        run_dir=run, termination_grace=0.1,
    )))
    thread.start()
    try:
        assert entered.wait(3)
        with pytest.raises(core.ProfileDelegateError) as exc:
            core._write_control_command(run, "cancel", {}, None)
        assert exc.value.code == "control_identity_pending"
        assert not (run / "control" / "commands" / "next_seq.json").exists()
    finally:
        release.set()
        thread.join(timeout=6)
    assert not thread.is_alive()
    assert results[0]["timed_out"] is True


def test_detached_worker_spawn_barrier_refuses_preidentity_cancel(tmp_path, monkeypatch):
    run = _run(tmp_path)
    monkeypatch.setattr(core, "authorize_run", lambda *args: "test")
    core.json_safe_write(run / "request.json", {
        "delegate_depth": 0, "effective_policy": {"limits": {"max_async": 2}},
    })
    monkeypatch.setattr(core, "iter_run_dirs", lambda: [run])
    monkeypatch.setattr(core, "get_runs_root", lambda: tmp_path)
    monkeypatch.setattr(core, "get_hermes_home_path", lambda: tmp_path)
    monkeypatch.setattr(core, "child_environment", lambda *args: os.environ.copy())
    entered, release = threading.Event(), threading.Event()
    actual_popen = core.subprocess.Popen

    def blocked_spawn(*args, **kwargs):
        proc = actual_popen(*args, **kwargs)
        entered.set()
        assert release.wait(3)
        return proc

    monkeypatch.setattr(core.subprocess, "Popen", blocked_spawn)
    thread = threading.Thread(target=core._start_detached_background_worker, args=(run,))
    thread.start()
    try:
        assert entered.wait(3)
        with pytest.raises(core.ProfileDelegateError) as exc:
            core._write_control_command(run, "cancel", {}, None)
        assert exc.value.code == "control_identity_pending"
        assert not (run / "control" / "commands" / "next_seq.json").exists()
    finally:
        release.set()
        thread.join(timeout=5)
    assert not thread.is_alive()


def test_detached_simple_cancel_reaps_child_and_ack_is_not_terminal(tmp_path, monkeypatch):
    run = _run(tmp_path)
    monkeypatch.setattr(core, "authorize_run", lambda *args: "test")
    results = []

    def worker():
        results.append(core.run_capped_subprocess(
            [sys.executable, "-c", "import time; time.sleep(15)"], tmp_path,
            os.environ.copy(), 12, run / "stdout.txt", run / "stderr.txt",
            run_dir=run, termination_grace=0.15,
        ))

    thread = threading.Thread(target=worker)
    thread.start()
    try:
        for _ in range(200):
            state = core.read_json_file(run / "status.json")
            if state.get("process_group_identity") and state.get("transport_alive"):
                break
            time.sleep(0.01)
        else:
            pytest.fail("owned child did not start")
        path, command = core._write_control_command(run, "cancel", {}, None)
        thread.join(timeout=8)
        assert not thread.is_alive()
        assert results[0]["stop_reason"] == "cancelled"
        assert results[0]["cancelled"] is True
        ack = core.read_json_file(run / "control" / "acks" / path.name)
        assert ack["command_id"] == command["command_id"]
        assert ack["state"] == "accepted"
        assert core.probe_worker_alive(results[0]["worker_pid"]) is False
        final = core.read_json_file(run / "status.json")
        assert final["worker_pid"] == os.getpid() and final["transport_alive"] is False
        assert final["status"] == "running"
    finally:
        if thread.is_alive():
            thread.join(timeout=15)


def test_control_write_refuses_terminal_race(tmp_path, monkeypatch):
    run = _run(tmp_path, transport="tui_stdio")
    monkeypatch.setattr(core, "authorize_run", lambda *args: "test")
    original = core._locked_run_status

    from contextlib import contextmanager

    @contextmanager
    def terminal_between_reads(path):
        with original(path) as status:
            status["status"] = "completed"
            yield status

    monkeypatch.setattr(core, "_locked_run_status", terminal_between_reads)
    with pytest.raises(core.ProfileDelegateError) as exc:
        core._write_control_command(run, "steer", {"text": "late"}, None)
    assert exc.value.code == "run_terminal"
    assert not list((run / "control" / "commands").glob("*.json"))


def test_group_identity_rejects_other_process_and_is_start_sensitive():
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        assert os.getpgid(other.pid) != other.pid
        assert core._owned_group_identity(other.pid) is None
    finally:
        other.terminate()
        other.wait(timeout=5)
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"], start_new_session=True)
    try:
        identity = core._owned_group_identity(proc.pid)
        assert identity and identity.startswith(f"linux-group:{proc.pid}:")
    finally:
        proc.terminate()
        proc.wait(timeout=5)
    assert core._owned_group_identity(proc.pid) is None
