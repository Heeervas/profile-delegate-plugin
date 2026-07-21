"""Focused tests for Profile Delegate's Hermes TUI JSON-RPC transport."""
from __future__ import annotations

import io
import json
import os
import queue
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import tui_rpc
import tui_runner


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
