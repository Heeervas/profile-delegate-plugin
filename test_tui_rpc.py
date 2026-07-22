"""Focused tests for Profile Delegate's Hermes TUI JSON-RPC transport."""
from __future__ import annotations

import io
import json
import os
import queue
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import tui_rpc
import tui_runner
import core


class FakeProcess:
    def __init__(self, frames: list[dict | str]) -> None:
        raw = "".join(
            (frame if isinstance(frame, str) else json.dumps(frame)) + "\n"
            for frame in frames
        ).encode()
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO(raw)
        self.stderr = io.BytesIO(b"")
        self.pid = os.getpid()
        self.returncode = None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9


def test_gateway_command_uses_hermes_runtime_python(tmp_path):
    hermes_dir = tmp_path / "runtime"
    hermes_dir.mkdir()
    hermes = hermes_dir / "hermes"
    python = hermes_dir / "python"
    hermes.write_text("", encoding="utf-8")
    python.write_text("", encoding="utf-8")
    command = tui_runner._gateway_command(
        {"hermes_bin": str(hermes), "effective_capabilities": {}, "child_approval_mode": "deny"},
        tmp_path,
    )
    assert command[0] == str(python)


def test_cancel_deadline_is_bounded():
    # Keep the escalation contract explicit: accepted native interrupt gets a
    # short grace window, never the run's full timeout.
    source = Path(tui_runner.__file__).read_text(encoding="utf-8")
    assert "cancel_deadline = time.monotonic() + 5.0" in source
    assert "time.monotonic() >= cancel_deadline" in source


def test_rpc_correlates_response_and_delivers_interleaved_event():
    proc = FakeProcess([
        {"jsonrpc": "2.0", "method": "event", "params": {"type": "tool.start", "session_id": "ui-1", "payload": {"name": "terminal", "arguments": {"secret": "no"}}}},
        {"jsonrpc": "2.0", "id": 1, "result": {"session_id": "ui-1", "session_key": "durable-1"}},
    ])
    client = tui_rpc.TuiRpcClient(proc)
    events = []
    result = client.call("session.create", {"profile": "reviewer"}, timeout=1, on_event=events.append)
    assert result["session_id"] == "ui-1"
    request = json.loads(proc.stdin.getvalue().decode().strip())
    assert request == {"jsonrpc": "2.0", "id": 1, "method": "session.create", "params": {"profile": "reviewer"}}
    assert events[0]["params"]["type"] == "tool.start"


def test_rpc_rejects_malformed_frame_and_unexpected_id():
    malformed = tui_rpc.TuiRpcClient(FakeProcess(["not json"]))
    with pytest.raises(tui_rpc.TuiProtocolError, match="malformed"):
        malformed.call("session.status", {"session_id": "x"}, timeout=1)

    unknown = tui_rpc.TuiRpcClient(FakeProcess([
        {"jsonrpc": "2.0", "id": 99, "result": {}},
    ]))
    with pytest.raises(tui_rpc.TuiProtocolError, match="unexpected response id"):
        unknown.call("session.status", {"session_id": "x"}, timeout=1)


def test_rpc_reports_eof_and_caps_diagnostics():
    proc = FakeProcess([])
    proc.stderr = io.BytesIO(b"x" * 100)
    client = tui_rpc.TuiRpcClient(proc, max_diagnostic_chars=12)
    with pytest.raises(tui_rpc.TuiTransportError, match="EOF"):
        client.call("session.status", {"session_id": "x"}, timeout=1)
    assert client.stderr_tail == "x" * 12


def test_rpc_timeout_names_exact_stage_method_and_last_event():
    class SilentClient(tui_rpc.TuiRpcClient):
        def __init__(self):
            self._next_id = 1

        def _write(self, frame):
            pass

        def read_frame(self, timeout):
            raise tui_rpc.TuiTransportError("TUI RPC response timed out")

    client = SilentClient()
    setattr(client, "last_event_type", "session.info")
    with pytest.raises(
        tui_rpc.TuiTransportError,
        match=r"session_creating RPC session.create timed out.*last event=session.info",
    ):
        client.call(
            "session.create", {"profile": "reviewer"}, timeout=0.01,
            stage="session_creating",
        )


def test_runner_exposes_separate_bounded_startup_and_agent_init_timeouts(monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_GATEWAY_STARTUP_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("PROFILE_DELEGATE_AGENT_INIT_TIMEOUT_SECONDS", "34")
    assert tui_runner._stage_timeout("PROFILE_DELEGATE_GATEWAY_STARTUP_TIMEOUT_SECONDS", 30) == 12.0
    assert tui_runner._stage_timeout("PROFILE_DELEGATE_AGENT_INIT_TIMEOUT_SECONDS", 60) == 34.0
    monkeypatch.setenv("PROFILE_DELEGATE_AGENT_INIT_TIMEOUT_SECONDS", "99999")
    assert tui_runner._stage_timeout("PROFILE_DELEGATE_AGENT_INIT_TIMEOUT_SECONDS", 60) == 600.0


def test_rpc_transport_has_no_projection_or_sanitization_policy():
    source = Path(tui_rpc.__file__).read_text(encoding="utf-8")
    assert "def reduce_event" not in source
    assert "EventJournal" not in source


def test_session_flow_uses_create_resume_submit_and_native_controls():
    class RecordingClient:
        def __init__(self):
            self.calls = []

        def call(self, method, params, **kwargs):
            self.calls.append((method, params))
            if method == "session.create":
                return {"session_id": "ui-new", "session_key": "durable-new"}
            if method == "session.resume":
                return {"session_id": "ui-resumed", "session_key": params["session_id"]}
            return {"accepted": True}

    client = RecordingClient()
    new = tui_rpc.start_session(client, profile="reviewer", mode="new", session_id="", title="review", cwd="/tmp")
    assert new == {"ui_session_id": "ui-new", "child_session_id": "durable-new"}
    resumed = tui_rpc.start_session(client, profile="reviewer", mode="resume", session_id="durable-old", title="review", cwd="/tmp")
    assert resumed == {"ui_session_id": "ui-resumed", "child_session_id": "durable-old"}
    tui_rpc.submit(client, "ui-resumed", "bounded prompt")
    tui_rpc.steer(client, "ui-resumed", "change direction")
    tui_rpc.interrupt(client, "ui-resumed")
    assert [name for name, _ in client.calls] == [
        "session.create", "session.resume", "prompt.submit", "session.steer", "session.interrupt"
    ]
    assert client.calls[1][1]["profile"] == "reviewer"
    assert client.calls[-2][1] == {"session_id": "ui-resumed", "text": "change direction"}


def test_wait_for_completion_consumes_events_until_matching_terminal_message():
    events = queue.Queue()
    events.put({"jsonrpc": "2.0", "method": "event", "params": {"type": "message.delta", "session_id": "other", "payload": {"text": "wrong"}}})
    events.put({"jsonrpc": "2.0", "method": "event", "params": {"type": "message.complete", "session_id": "ui-1", "payload": {"text": "final", "status": "complete"}}})
    result = tui_rpc.wait_for_completion(events, "ui-1", timeout=1)
    assert result == {"text": "final", "status": "complete"}


def test_close_reaps_process_and_is_idempotent():
    proc = FakeProcess([])
    client = tui_rpc.TuiRpcClient(proc)
    client.close()
    client.close()
    assert proc.returncode == 0


@pytest.mark.parametrize("timeout", [False, True])
def test_runner_poll_flushes_pending_journal_text_after_active_and_idle_reads(timeout):
    frame = {"method": "event", "params": {"type": "status.update"}}

    class Client:
        def read_frame(self, poll_timeout):
            if timeout:
                raise tui_rpc.TuiTransportError("TUI RPC response timed out")
            return frame

    class RecordingJournal:
        def __init__(self):
            self.flushes = 0

        def flush(self):
            self.flushes += 1

    journal = RecordingJournal()
    assert tui_runner._poll_event(Client(), 0.15, journal) == (None if timeout else frame)
    assert journal.flushes == 1


def test_runner_poll_flushes_before_propagating_transport_error():
    class Client:
        def read_frame(self, _timeout):
            raise tui_rpc.TuiTransportError("TUI RPC EOF")

    class RecordingJournal:
        def __init__(self):
            self.flushes = 0

        def flush(self):
            self.flushes += 1

    journal = RecordingJournal()
    with pytest.raises(tui_rpc.TuiTransportError, match="EOF"):
        tui_runner._poll_event(Client(), 0.15, journal)
    assert journal.flushes == 1


def test_runner_publishes_ready_status_transitions_after_success(tmp_path, monkeypatch):
    run = tmp_path / "pd_20260721_120001_bbbbbb"
    run.mkdir()
    request = {
        "task_id": run.name, "timeout_seconds": 10, "workdir": str(tmp_path),
        "profile": "reviewer", "session_mode": "new", "requested_session_id": "",
        "session_title": "test", "profile_home": str(tmp_path), "hermes_bin": sys.executable,
        "child_approval_mode": "deny", "effective_execution": {}, "effective_capabilities": {},
        "effective_policy": {"limits": {"max_concurrent": 8}},
    }
    (run / "request.json").write_text(json.dumps(request), encoding="utf-8")
    (run / "prompt.txt").write_text("prompt", encoding="utf-8")
    (run / "status.json").write_text(
        json.dumps({"task_id": run.name, "status": "running"}), encoding="utf-8",
    )
    transitions = []
    real_merge = tui_runner.core.merge_run_status

    def capture_merge(run_dir, updates, **kwargs):
        if "phase" in updates:
            transitions.append(updates["phase"])
        return real_merge(run_dir, updates, **kwargs)

    monkeypatch.setattr(tui_runner.core, "merge_run_status", capture_merge)
    monkeypatch.setattr(
        tui_runner.core, "merge_run_status_best_effort",
        lambda run_dir, updates: bool(capture_merge(run_dir, updates)),
    )
    monkeypatch.setattr(tui_runner, "_environment", lambda request, run_dir: {})

    @contextmanager
    def slot(_limit):
        yield type("Slot", (), {"slot": 0})()

    monkeypatch.setattr(tui_runner.core, "acquire_concurrency_slot", slot)

    complete = {
        "method": "event", "params": {
            "type": "message.complete", "session_id": "ui-1",
            "payload": {"status": "complete", "text": '{"status":"ok","summary":"done","artifacts":[],"errors":[],"next_steps":[]}'},
        },
    }

    class Client:
        stderr_tail = ""

        def __init__(self):
            self.process = type("Process", (), {"pid": os.getpid(), "poll": lambda self: 0})()

        def wait_ready(self, **kwargs):
            return None

        def read_frame(self, timeout):
            return complete

        def call(self, *args, **kwargs):
            return {}

        def close(self):
            return None

    monkeypatch.setattr(tui_runner.tui_rpc, "launch_gateway", lambda **kwargs: Client())
    monkeypatch.setattr(
        tui_runner.tui_rpc, "start_session",
        lambda *args, **kwargs: {"ui_session_id": "ui-1", "child_session_id": "child-1"},
    )
    monkeypatch.setattr(tui_runner.tui_rpc, "submit", lambda *args, **kwargs: {})
    result = tui_runner.execute(run)
    assert result["success"] is True
    assert transitions.index("transport_ready") < transitions.index("session_creating")
    assert transitions.index("session_ready") < transitions.index("agent_initializing")


def test_runner_nonzero_transport_exit_overrides_complete_ok(tmp_path, monkeypatch):
    run = tmp_path / "pd_20260721_120001_cccccc"
    run.mkdir()
    request = {
        "task_id": run.name, "timeout_seconds": 10, "workdir": str(tmp_path),
        "profile": "reviewer", "session_mode": "new", "requested_session_id": "",
        "session_title": "test", "profile_home": str(tmp_path), "hermes_bin": sys.executable,
        "child_approval_mode": "deny", "effective_execution": {}, "effective_capabilities": {},
        "effective_policy": {"limits": {"max_concurrent": 8}},
    }
    (run / "request.json").write_text(json.dumps(request), encoding="utf-8")
    (run / "prompt.txt").write_text("prompt", encoding="utf-8")
    (run / "status.json").write_text(
        json.dumps({"task_id": run.name, "status": "running"}), encoding="utf-8",
    )
    monkeypatch.setattr(tui_runner, "_environment", lambda request, run_dir: {})

    @contextmanager
    def slot(_limit):
        yield type("Slot", (), {"slot": 0})()

    monkeypatch.setattr(tui_runner.core, "acquire_concurrency_slot", slot)
    complete = {
        "method": "event", "params": {
            "type": "message.complete", "session_id": "ui-1",
            "payload": {"status": "complete", "text": '{"status":"ok","summary":"done"}'},
        },
    }

    class Client:
        stderr_tail = ""

        def __init__(self):
            self.process = type("Process", (), {"pid": os.getpid(), "poll": lambda self: 17})()

        def wait_ready(self, **kwargs):
            return None

        def read_frame(self, timeout):
            return complete

        def call(self, *args, **kwargs):
            return {}

        def close(self):
            return None

    monkeypatch.setattr(tui_runner.tui_rpc, "launch_gateway", lambda **kwargs: Client())
    monkeypatch.setattr(
        tui_runner.tui_rpc, "start_session",
        lambda *args, **kwargs: {"ui_session_id": "ui-1", "child_session_id": "child-1"},
    )
    monkeypatch.setattr(tui_runner.tui_rpc, "submit", lambda *args, **kwargs: {})
    result = tui_runner.execute(run)
    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["error_code"] == "tui_nonzero_exit"
    assert result["result"]["status"] == "failed"
    assert result["result"]["execution_status"] == "failed"


@pytest.mark.parametrize(
    ("text", "message_status", "expected_task_status", "expected_contract", "success"),
    [
        ('{"status":"ok","summary":"done"}', "complete", "ok", "valid", True),
        ('{"status":"blocked","summary":"wait"}', "complete", "blocked", "valid", False),
        ("plain useful output", "complete", "unknown", "drifted", False),
        ("OK\n{\"status\":\"ok\"}\n{\"status\":\"blocked\"}", "complete", "unknown", "drifted", False),
    ],
)
def test_tui_and_legacy_normalization_wrapper_parity(
    text, message_status, expected_task_status, expected_contract, success,
):
    parsed, meta = core.parse_json_result(text)
    legacy = core.normalize_result(
        parsed, "/tmp/stdout.txt", raw_output=text, parse_meta=meta,
    )
    tui = core.normalize_result(
        parsed, "/tmp/stdout.txt", raw_output=text, parse_meta=meta,
    )
    if message_status != "complete":
        tui["status"] = "failed"
    core.apply_execution_status(tui, "completed")
    assert (tui["status"], tui["contract_status"]) == (
        legacy["status"], legacy["contract_status"],
    )
    assert core.wrapper_success("completed", tui) is success


@pytest.mark.parametrize(
    ("lifecycle", "contract_status"),
    [
        ("failed", "not_evaluated"),
        ("cancelled", "not_evaluated"),
        ("timed_out", "not_evaluated"),
    ],
)
def test_manual_terminal_failure_results_have_complete_orthogonal_schema(
    tmp_path, lifecycle, contract_status,
):
    run = tmp_path / f"pd_{lifecycle}"
    run.mkdir()
    result = {
        "status": "failed", "execution_status": lifecycle,
        "contract_status": contract_status, "summary": lifecycle,
    }
    core.write_result_artifact(run, result)
    saved = json.loads((run / "result.json").read_text(encoding="utf-8"))
    assert saved["status"] == "failed"
    assert saved["execution_status"] == lifecycle
    assert saved["contract_status"] == contract_status
