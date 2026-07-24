"""Focused synchronous lifecycle regressions. Usage: pytest test_sync_lifecycle.py -q"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

import core


def _wait_for(path: Path, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert path.exists()


def _process_gone(pid: int, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        stat_path = Path(f"/proc/{pid}/stat")
        if not stat_path.exists():
            return True
        try:
            state = stat_path.read_text().split()[2]
        except FileNotFoundError:
            return True
        if state == "Z":
            return True
        time.sleep(0.03)
    return not Path(f"/proc/{pid}").exists()


def _status_fixture(run_dir: Path, *, origin: dict[str, str] | None = None) -> None:
    run_dir.mkdir(parents=True)
    core.json_safe_write(run_dir / "status.json", {
        "task_id": run_dir.name,
        "status": "running",
        "phase": "starting",
        "background": False,
        "transport": "cli",
        "origin": origin or {"session_key": "origin-lane"},
    })


@pytest.mark.parametrize("exit_code", [0, 7])
def test_sync_child_emits_content_free_heartbeats_and_stops(tmp_path, exit_code):
    labels: list[str] = []

    def touch(state: dict, label: str) -> None:
        now = time.monotonic()
        if now - state["last_touch"] >= state["interval"]:
            state["last_touch"] = now
            labels.append(f"{label} ({int(now - state['start'])}s elapsed)")

    result = core.run_capped_subprocess(
        [sys.executable, "-c", f"import sys,time; time.sleep(.35); sys.exit({exit_code})"],
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout=3,
        stdout_path=tmp_path / "stdout.txt",
        stderr_path=tmp_path / "stderr.txt",
        activity_touch=touch,
        activity_interval=0.05,
    )

    count_at_exit = len(labels)
    time.sleep(0.12)
    assert result["stop_reason"] == "exited"
    assert result["exit_code"] == exit_code
    assert count_at_exit >= 3
    assert len(labels) == count_at_exit
    assert all(label.startswith("profile_delegate child running (") for label in labels)
    assert all("PRIVATE" not in label for label in labels)


@pytest.mark.parametrize("trigger", ["interrupt", "cancel"])
def test_interrupt_or_cancel_reaps_complete_process_group(tmp_path, trigger, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path))
    run_dir = tmp_path / "pd_20260724_120000_abcdef"
    _status_fixture(run_dir)
    grandchild_marker = tmp_path / "grandchild.pid"
    code = (
        "import pathlib,subprocess,sys,time; "
        f"p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
        f"pathlib.Path({str(grandchild_marker)!r}).write_text(str(p.pid)); "
        "print('ready', flush=True); time.sleep(30)"
    )
    interrupted = threading.Event()
    outcome: dict = {}

    def worker() -> None:
        outcome.update(core.run_capped_subprocess(
            [sys.executable, "-c", code], cwd=tmp_path, env=os.environ.copy(), timeout=20,
            stdout_path=tmp_path / "stdout.txt", stderr_path=tmp_path / "stderr.txt",
            run_dir=run_dir, interrupt_check=interrupted.is_set,
            activity_interval=0.05, status_interval=0.05, termination_grace=0.2,
        ))

    thread = threading.Thread(target=worker)
    thread.start()
    _wait_for(grandchild_marker)
    grandchild_pid = int(grandchild_marker.read_text())
    if trigger == "interrupt":
        interrupted.set()
    else:
        core.profile_delegate_cancel(run_dir.name, caller_origin={"session_key": "origin-lane"})
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert outcome["stop_reason"] == ("interrupted" if trigger == "interrupt" else "cancelled")
    assert _process_gone(grandchild_pid)
    status = json.loads((run_dir / "status.json").read_text())
    assert status["worker_alive"] is False
    assert status["interrupted"] is (trigger == "interrupt")
    assert status["cancellation_requested"] is (trigger == "cancel")


def test_foreground_cancel_is_exact_origin_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    run_dir = tmp_path / "runs" / "pd_20260724_120000_abcdef"
    _status_fixture(run_dir, origin={"session_key": "right-origin"})

    with pytest.raises(core.ProfileDelegateError, match="exact originating session"):
        core.profile_delegate_cancel(run_dir.name, caller_origin={"session_key": "wrong-origin"})
    assert not (run_dir / "control").exists()

    first = core.profile_delegate_cancel(run_dir.name, caller_origin={"session_key": "right-origin"})
    second = core.profile_delegate_cancel(run_dir.name, caller_origin={"session_key": "right-origin"})

    assert first["success"] is True and first["idempotent"] is False
    assert second["success"] is True and second["idempotent"] is True
    assert first["command_id"] == second["command_id"]


def test_concurrent_foreground_cancel_creates_one_marker(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    run_dir = tmp_path / "runs" / "pd_20260724_120000_abcdef"
    _status_fixture(run_dir, origin={"session_key": "right-origin"})
    barrier = threading.Barrier(8)
    results: list[dict] = []

    def cancel() -> None:
        barrier.wait()
        results.append(core.profile_delegate_cancel(
            run_dir.name, caller_origin={"session_key": "right-origin"},
        ))

    threads = [threading.Thread(target=cancel) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    commands = list((run_dir / "control" / "commands").glob("*.json"))
    assert len(commands) == 1
    assert len({item["command_id"] for item in results}) == 1
    assert sum(not item["idempotent"] for item in results) == 1


def test_timeout_remains_timed_out_and_reaps_group(tmp_path):
    run_dir = tmp_path / "pd_20260724_120000_abcdef"
    _status_fixture(run_dir)
    result = core.run_capped_subprocess(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=tmp_path, env=os.environ.copy(), timeout=1,
        stdout_path=tmp_path / "stdout.txt", stderr_path=tmp_path / "stderr.txt",
        run_dir=run_dir, termination_grace=0.2,
    )
    assert result["stop_reason"] == "timed_out"
    assert result["timed_out"] is True
    assert result["cancelled"] is False
    assert result["interrupted"] is False


def test_timeout_kills_group_when_leader_exits_but_grandchild_holds_pipes(tmp_path):
    marker = tmp_path / "grandchild.pid"
    code = (
        "import pathlib,subprocess,sys; "
        f"p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
        f"pathlib.Path({str(marker)!r}).write_text(str(p.pid))"
    )
    result = core.run_capped_subprocess(
        [sys.executable, "-c", code], cwd=tmp_path, env=os.environ.copy(), timeout=1,
        stdout_path=tmp_path / "stdout.txt", stderr_path=tmp_path / "stderr.txt",
        termination_grace=0.2,
    )
    grandchild_pid = int(marker.read_text())
    assert result["stop_reason"] == "timed_out"
    assert _process_gone(grandchild_pid)


def test_natural_exit_wins_over_late_interrupt_while_pipes_drain(tmp_path):
    marker = tmp_path / "leader-exited"
    interrupted = threading.Event()
    code = (
        "import pathlib,subprocess,sys; "
        f"subprocess.Popen([sys.executable,'-c','import time; time.sleep(.3)']); "
        f"pathlib.Path({str(marker)!r}).write_text('done')"
    )

    def late_interrupt() -> None:
        _wait_for(marker)
        time.sleep(0.05)
        interrupted.set()

    thread = threading.Thread(target=late_interrupt)
    thread.start()
    result = core.run_capped_subprocess(
        [sys.executable, "-c", code], cwd=tmp_path, env=os.environ.copy(), timeout=3,
        stdout_path=tmp_path / "stdout.txt", stderr_path=tmp_path / "stderr.txt",
        interrupt_check=interrupted.is_set,
    )
    thread.join(timeout=1)
    assert result["stop_reason"] == "exited"
    assert result["interrupted"] is False


def test_closed_pipes_do_not_escape_deadline_or_leave_child(tmp_path):
    result = core.run_capped_subprocess(
        [sys.executable, "-c", "import os,time; os.close(1); os.close(2); time.sleep(30)"],
        cwd=tmp_path, env=os.environ.copy(), timeout=1,
        stdout_path=tmp_path / "stdout.txt", stderr_path=tmp_path / "stderr.txt",
        termination_grace=0.2,
    )
    assert result["stop_reason"] == "timed_out"
    assert result["timed_out"] is True
    assert _process_gone(result["worker_pid"])


def test_callback_failure_still_reaps_owned_process_group(tmp_path):
    def broken_interrupt() -> bool:
        raise RuntimeError("callback failed")

    started = time.monotonic()
    with pytest.raises(RuntimeError, match="callback failed"):
        core.run_capped_subprocess(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cwd=tmp_path, env=os.environ.copy(), timeout=10,
            stdout_path=tmp_path / "stdout.txt", stderr_path=tmp_path / "stderr.txt",
            interrupt_check=broken_interrupt, termination_grace=0.2,
        )
    assert time.monotonic() - started < 3


def test_sync_status_is_throttled_atomic_and_contains_no_output(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path))
    run_dir = tmp_path / "pd_20260724_120000_abcdef"
    _status_fixture(run_dir)
    writes = 0
    original = core.merge_run_status_best_effort

    def counted(*args, **kwargs):
        nonlocal writes
        writes += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(core, "merge_run_status_best_effort", counted)
    secret = "PRIVATE_CHILD_OUTPUT_SENTINEL"
    result = core.run_capped_subprocess(
        [sys.executable, "-c", f"import time; print('{secret}', flush=True); time.sleep(.35)"],
        cwd=tmp_path, env=os.environ.copy(), timeout=3,
        stdout_path=tmp_path / "stdout.txt", stderr_path=tmp_path / "stderr.txt",
        run_dir=run_dir, status_interval=0.1,
    )
    status_text = (run_dir / "status.json").read_text()
    status = json.loads(status_text)

    assert result["stop_reason"] == "exited"
    assert 2 <= writes <= 8
    assert secret not in status_text
    assert status["worker_pid"] == result["worker_pid"]
    assert status["worker_alive"] is False
    assert status["latest_activity"]
    assert status["process_identity"]
    public = core.profile_delegate_status(run_dir.name, tail_chars=0)
    assert public["worker_pid"] == result["worker_pid"]
    assert public["process_identity"] == status["process_identity"]
    assert public["activity"] == "stale"
    assert public["timeout_seconds"] == 3
    assert not (run_dir / "status.json.tmp").exists()


def test_tool_guidance_is_advisory_only():
    schema = __import__("__init__")._schema()
    background = schema["parameters"]["properties"]["background"]["description"]
    description = schema["description"]
    combined = f"{description} {background}".lower()
    assert "originating turn" in combined
    assert "prefer background" in combined
    assert "short bounded" in combined
    assert "advisory" in combined
    assert schema["parameters"]["properties"]["background"]["default"] is False


def test_activity_and_status_helpers_are_defensive_without_hermes(monkeypatch):
    real_import = __import__

    def blocked_import(name, *args, **kwargs):
        if name.startswith("tools."):
            raise ImportError("Hermes runtime unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked_import)
    assert core._runtime_activity_touch() is None
    assert core._runtime_interrupt_check()() is False


def test_terminal_cancel_status_cannot_be_overwritten(tmp_path):
    run_dir = tmp_path / "pd_20260724_120000_abcdef"
    _status_fixture(run_dir)
    core.merge_run_status(run_dir, {
        "status": "cancelled", "phase": "cancelled", "ended_at": core.now_iso(),
        "terminal_reason": "parent_interrupt", "exit_code": -15,
    }, terminal=True)
    core.merge_run_status(run_dir, {
        "status": "completed", "phase": "completed", "ended_at": core.now_iso(),
        "terminal_reason": "natural_exit", "exit_code": 0,
    }, terminal=True)
    status = json.loads((run_dir / "status.json").read_text())
    assert status["status"] == "cancelled"
    assert status["phase"] == "cancelled"
    assert status["terminal_reason"] == "parent_interrupt"
    assert status["exit_code"] == -15


def test_cancelled_attempt_is_never_classified_transient():
    assert core.classify_transient_failure(
        exit_code=-15,
        timed_out=False,
        stdout="",
        stderr="RemoteProtocolError: incomplete chunked read",
        parsed_result=None,
        interrupted=True,
    ) is None

def test_delegate_interrupt_finalizes_cancelled_without_resume(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setattr(core.shutil, "which", lambda _name: "/usr/bin/hermes")
    monkeypatch.setattr(core.os, "access", lambda _path, _mode: True)
    monkeypatch.setattr(
        core, "validate_profile",
        lambda profile, policy=None: core.ValidatedProfile(profile, profile, str(tmp_path / profile)),
    )
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)
    attempts = 0

    def fake_run(_cmd, **kwargs):
        nonlocal attempts
        attempts += 1
        core.text_safe_write(kwargs["stdout_path"], "")
        core.text_safe_write(kwargs["stderr_path"], "RemoteProtocolError: incomplete chunked read")
        return {
            "exit_code": -15, "timed_out": False, "cancelled": False,
            "interrupted": True, "stop_reason": "interrupted",
            "stdout_truncated": False, "stderr_truncated": False,
            "stdout_chars": 0, "stderr_chars": 43,
            "stdout_limit": 200000, "stderr_limit": 100000,
            "stdout_diagnostic_tail": "",
            "stderr_diagnostic_tail": "RemoteProtocolError: incomplete chunked read",
        }

    monkeypatch.setattr(core, "run_capped_subprocess", fake_run)
    final = core.delegate_profile("reviewer", "task", session_title="interrupt lifecycle")
    run_dir = Path(final["paths"]["run_dir"])
    saved_status = json.loads((run_dir / "status.json").read_text())
    saved_result = json.loads((run_dir / "result.json").read_text())

    assert attempts == 1
    assert final["status"] == "cancelled"
    assert final["success"] is False
    assert saved_status["status"] == "cancelled"
    assert saved_status["terminal_reason"] == "interrupted"
    assert saved_result["execution_status"] == "cancelled"
    core.merge_run_status(run_dir, {
        "status": "completed", "phase": "completed", "terminal_reason": "natural_exit",
    }, terminal=True)
    assert json.loads((run_dir / "status.json").read_text())["status"] == "cancelled"


def test_interrupt_during_transient_retry_delay_prevents_resume(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setattr(core.shutil, "which", lambda _name: "/usr/bin/hermes")
    monkeypatch.setattr(core.os, "access", lambda _path, _mode: True)
    monkeypatch.setattr(
        core, "validate_profile",
        lambda profile, policy=None: core.ValidatedProfile(profile, profile, str(tmp_path / profile)),
    )
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)
    monkeypatch.setattr(core, "TRANSIENT_RESUME_DELAY_SECONDS", 0.5)
    interrupted = threading.Event()
    monkeypatch.setattr(core, "_runtime_interrupt_check", lambda: interrupted.is_set)
    attempts = 0

    def fake_run(_cmd, **kwargs):
        nonlocal attempts
        attempts += 1
        core.text_safe_write(kwargs["stdout_path"], "session_id: stable_session")
        error = "RemoteProtocolError: incomplete chunked read"
        core.text_safe_write(kwargs["stderr_path"], error)
        threading.Timer(0.05, interrupted.set).start()
        return {
            "exit_code": 1, "timed_out": False, "cancelled": False,
            "interrupted": False, "stop_reason": "exited",
            "stdout_truncated": False, "stderr_truncated": False,
            "stdout_chars": 0, "stderr_chars": len(error),
            "stdout_limit": 200000, "stderr_limit": 100000,
            "stdout_diagnostic_tail": "", "stderr_diagnostic_tail": error,
        }

    monkeypatch.setattr(core, "run_capped_subprocess", fake_run)
    final = core.delegate_profile("reviewer", "task", session_title="interrupt retry delay")
    assert attempts == 1
    assert final["status"] == "cancelled"
    assert final["result"]["execution_status"] == "cancelled"
