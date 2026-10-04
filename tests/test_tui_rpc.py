"""Focused tests for Profile Delegate's Hermes TUI JSON-RPC transport."""
from __future__ import annotations

import io
import json
import os
import signal
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1]
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


def runner_run(tmp_path, task_id, *, fields=None, prompt=None):
    """Shared artifacts only; scenario-specific fields and omissions stay explicit."""
    run = tmp_path / task_id
    run.mkdir()
    request = {
        "task_id": run.name, "timeout_seconds": 10, "workdir": str(tmp_path),
        "profile": "reviewer", "session_mode": "new", "profile_home": str(tmp_path),
        "hermes_bin": sys.executable, "child_approval_mode": "deny",
        "effective_policy": {"limits": {"max_concurrent": 8}},
        **(fields or {}),
    }
    (run / "request.json").write_text(json.dumps(request), encoding="utf-8")
    (run / "status.json").write_text(json.dumps({"task_id": run.name, "status": "running"}), encoding="utf-8")
    if prompt is not None:
        (run / "prompt.txt").write_text(prompt, encoding="utf-8")
    return run


@contextmanager
def runner_slot(_limit):
    yield type("Slot", (), {"slot": 0})()


def runner_complete(text='{"status":"ok","summary":"done"}'):
    return {
        "method": "event", "params": {
            "type": "message.complete", "session_id": "ui-1",
            "payload": {"status": "complete", "text": text},
        },
    }


class RecordingJournal:
    def __init__(self):
        self.flushes = 0

    def flush(self):
        self.flushes += 1


class CompleteClient:
    """Existing complete-event fixture, shared without adding gateway behavior."""
    stderr_tail = ""

    def __init__(self, complete, *, exit_code=0):
        self.process = type("Process", (), {"pid": os.getpid(), "poll": lambda self: exit_code})()
        self.complete, self.calls, self.close_kwargs = complete, [], None

    def wait_ready(self, **kwargs):
        return None

    def read_event(self, _timeout):
        return self.complete

    def call(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {}

    def close(self, **kwargs):
        self.close_kwargs = kwargs
        return None


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
    assert tui_runner.CANCEL_GRACE_SECONDS == 5.0


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
            self._abandoned_ids = set()

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


def test_rpc_deadline_remains_authoritative_during_continuous_events(monkeypatch):
    class FloodClient(tui_rpc.TuiRpcClient):
        def __init__(self):
            super().__init__(FakeProcess([]))
            self.reads = 0

        def _read_raw_frame(self, timeout):
            self.reads += 1
            return {
                "jsonrpc": "2.0", "method": "event",
                "params": {"type": "status.update", "session_id": "ui-1", "payload": {}},
            }

    ticks = iter([0.0, 0.0, 0.0, 0.0, 0.002, 0.002, 0.002])
    monkeypatch.setattr(tui_rpc.time, "monotonic", lambda: next(ticks))
    client = FloodClient()

    with pytest.raises(tui_rpc.TuiTransportError, match="timed out"):
        client.call("session.interrupt", {"session_id": "ui-1"}, timeout=0.001)

    assert client.reads == 1
    assert client._abandoned_ids == {1}


def test_rpc_timeout_tracks_id_and_late_response_is_consumed_once():
    class TimeoutOnceClient(tui_rpc.TuiRpcClient):
        def __init__(self, process):
            super().__init__(process)
            self.force_timeout = True

        def read_frame(self, timeout):
            if self.force_timeout:
                raise tui_rpc.TuiTransportError("TUI RPC response timed out")
            return super().read_frame(timeout)

    proc = FakeProcess([])
    client = TimeoutOnceClient(proc)
    with pytest.raises(tui_rpc.TuiTransportError, match="timed out before dispatch"):
        client.call("session.steer", {"session_id": "ui-1", "text": "x"}, timeout=0)
    assert proc.stdin.getvalue() == b""
    with pytest.raises(tui_rpc.TuiTransportError, match="timed out"):
        client.call("session.steer", {"session_id": "ui-1", "text": "x"}, timeout=0.01)
    client.force_timeout = False
    assert client._abandoned_ids == {1}

    proc.stdout = io.BytesIO(
        (
            json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"code": 4010, "message": "late"}})
            + "\n"
            + json.dumps({
                "jsonrpc": "2.0", "method": "event",
                "params": {"type": "message.complete", "session_id": "ui-1", "payload": {}},
            })
            + "\n"
        ).encode()
    )
    frame = client.read_event(1)
    assert frame["params"]["type"] == "message.complete"
    assert client._abandoned_ids == set()


def test_idle_unknown_response_id_remains_fatal():
    client = tui_rpc.TuiRpcClient(FakeProcess([
        {"jsonrpc": "2.0", "id": 999, "result": {}},
    ]))
    with pytest.raises(tui_rpc.TuiProtocolError, match="unexpected idle response id"):
        client.read_event(1)


@pytest.mark.parametrize(
    "frame, message",
    [
        ({"jsonrpc": "2.0", "id": True, "result": {}}, "id must be an integer"),
        ({"jsonrpc": "2.0", "id": 1.0, "result": {}}, "id must be an integer"),
        ({"jsonrpc": "2.0", "id": 1, "result": {}, "error": {"code": 1, "message": "x"}}, "exactly one"),
        ({"jsonrpc": "2.0", "id": 1, "result": "bad"}, "result must be an object"),
        ({"jsonrpc": "2.0", "id": 1, "error": "bad"}, "error must contain"),
        ({"jsonrpc": "2.0", "id": 1, "error": {"code": True, "message": "bad"}}, "error must contain"),
        ({"jsonrpc": "2.0", "id": 1, "method": None, "result": {}}, "must not include method"),
    ],
)
def test_malformed_matching_late_response_remains_fatal(frame, message):
    client = tui_rpc.TuiRpcClient(FakeProcess([frame]))
    client._abandoned_ids.add(1)
    with pytest.raises(tui_rpc.TuiProtocolError, match=message):
        client.read_event(1)
    assert client._abandoned_ids == {1}


def test_valid_late_result_is_consumed_once_and_duplicate_is_fatal():
    late = {"jsonrpc": "2.0", "id": 1, "result": {}}
    client = tui_rpc.TuiRpcClient(FakeProcess([late, late]))
    client._abandoned_ids.add(1)
    with pytest.raises(tui_rpc.TuiProtocolError, match="unexpected idle response id 1"):
        client.read_event(1)
    assert client._abandoned_ids == set()


@pytest.mark.parametrize("response_id", [1, 9])
def test_idle_id_bearing_event_hybrid_is_fatal(response_id):
    frame = {
        "jsonrpc": "2.0", "id": response_id, "method": "event",
        "params": {"type": "message.complete", "session_id": "ui-1", "payload": {}},
    }
    client = tui_rpc.TuiRpcClient(FakeProcess([frame]))
    with pytest.raises(tui_rpc.TuiProtocolError, match="must not include method"):
        client.read_event(1)


def test_abandoned_id_bearing_event_hybrid_is_fatal_without_consuming_id():
    frame = {
        "jsonrpc": "2.0", "id": 1, "method": "event",
        "params": {"type": "message.complete", "session_id": "ui-1", "payload": {}},
    }
    client = tui_rpc.TuiRpcClient(FakeProcess([frame]))
    client._abandoned_ids.add(1)
    with pytest.raises(tui_rpc.TuiProtocolError, match="must not include method"):
        client.read_event(1)
    assert client._abandoned_ids == {1}


def test_active_call_id_bearing_event_hybrid_is_fatal():
    frame = {
        "jsonrpc": "2.0", "id": 1, "method": "event",
        "params": {"type": "status.update", "session_id": "ui-1", "payload": {}},
    }
    client = tui_rpc.TuiRpcClient(FakeProcess([frame]))
    with pytest.raises(tui_rpc.TuiProtocolError, match="must not include method"):
        client.call("session.status", {"session_id": "ui-1"}, timeout=1)


def test_close_honors_absolute_deadline_and_kills_stubborn_process():
    proc = subprocess.Popen(
        [sys.executable, "-c", "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready', flush=True); time.sleep(30)"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True,
    )
    client = tui_rpc.TuiRpcClient(proc)
    assert proc.stdout is not None and proc.stdout.readline() == b"ready\n"
    started = time.monotonic()
    try:
        client.close(deadline=started + 0.3)
        elapsed = time.monotonic() - started
        assert elapsed < 0.8
        assert proc.poll() is not None
        assert proc.returncode == -signal.SIGKILL
        assert all(
            stream is None or stream.closed
            for stream in (proc.stdin, proc.stdout, proc.stderr)
        )
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2)


def test_runner_exposes_separate_bounded_startup_and_agent_init_timeouts(monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_GATEWAY_STARTUP_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("PROFILE_DELEGATE_AGENT_INIT_TIMEOUT_SECONDS", "34")
    assert tui_runner._stage_timeout("PROFILE_DELEGATE_GATEWAY_STARTUP_TIMEOUT_SECONDS", 30) == 12.0
    assert tui_runner._stage_timeout("PROFILE_DELEGATE_AGENT_INIT_TIMEOUT_SECONDS", 60) == 34.0
    monkeypatch.setenv("PROFILE_DELEGATE_AGENT_INIT_TIMEOUT_SECONDS", "99999")
    assert tui_runner._stage_timeout("PROFILE_DELEGATE_AGENT_INIT_TIMEOUT_SECONDS", 60) == 600.0


def test_session_flow_uses_create_resume_submit_and_native_controls(monkeypatch):
    ticks = iter([0.0, 0.25, 1.0, 1.25])
    monkeypatch.setattr(tui_rpc, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    class RecordingClient:
        def __init__(self):
            self.calls = []
            self.timeouts = []

        def call(self, method, params, **kwargs):
            self.calls.append((method, params))
            self.timeouts.append(kwargs["timeout"])
            if method == "session.create":
                return {"session_id": "ui-new", "session_key": "durable-new"}
            if method == "session.resume":
                return {"session_id": "ui-resumed", "session_key": params["session_id"]}
            return {"accepted": True}

    client = RecordingClient()
    new = tui_rpc.start_session(client, profile="reviewer", mode="new", session_id="", title="review", cwd="/tmp")
    assert new == {"ui_session_id": "ui-new", "child_session_id": "durable-new"}
    resumed = tui_rpc.start_session(client, profile="reviewer", mode="resume", session_id="durable-old", title="ignored", cwd="/different-workspace")
    assert resumed == {"ui_session_id": "ui-resumed", "child_session_id": "durable-old"}
    assert client.timeouts[:2] == [59.75, 59.75]
    tui_rpc.submit(client, "ui-resumed", "bounded prompt")
    tui_rpc.steer(client, "ui-resumed", "change direction")
    tui_rpc.interrupt(client, "ui-resumed")
    assert [name for name, _ in client.calls] == [
        "session.create", "session.resume", "prompt.submit", "session.steer", "session.interrupt"
    ]
    assert client.calls[1][1]["profile"] == "reviewer"
    assert client.calls[0][1]["cwd"] == "/tmp"
    assert client.calls[1][1] == {
        "profile": "reviewer", "session_id": "durable-old", "source": "profile-delegate", "cols": 100,
        "omit_messages": True, "inline_images": False,
    }
    # The plugin's minimal venv deliberately lacks Hermes' pydantic dependency.
    # Validate actual emitted params with the installed runtime's interpreter.
    check = subprocess.run(
        [str(Path(os.environ.get("PROFILE_DELEGATE_TEST_RUNTIME", "/opt/hermes")) / ".venv/bin/python"), "-c",
         "import json,sys; from tui_gateway.contracts.sessions import SessionCreateParams,SessionResumeParams; "
         "create,resume=json.load(sys.stdin); SessionCreateParams.model_validate(create); "
         "SessionResumeParams.model_validate(resume); print('installed_contracts_ok')"],
        input=json.dumps([client.calls[0][1], client.calls[1][1]]),
        capture_output=True, text=True, timeout=30,
    )
    assert check.returncode == 0, check.stderr
    assert check.stdout.strip() == "installed_contracts_ok"
    assert client.calls[-2][1] == {"session_id": "ui-resumed", "text": "change direction"}


@pytest.mark.parametrize("mode, selection", [
    ("resume", {"model": "codex/example", "provider": "openai-api", "reasoning_effort": "high"}),
    ("resume", {"model": "codex/example"}), ("resume", {"provider": "openai-api"}),
    ("resume", {"reasoning_effort": "none"}), ("new", {"provider": "openai-api", "reasoning_effort": "high"}),
    ("resume", {"reasoning_effort": "show"}),
])
def test_session_applies_authorized_selection_without_config_writes(monkeypatch, mode, selection):
    from contextlib import nullcontext
    import types
    from hermes_cli import model_switch
    from tui_gateway import methods_config_set, model_switch as gateway_model
    from tui_gateway.method_ctx import rebind

    def forbidden_write(*args, **kwargs):
        pytest.fail("session selection attempted a configuration write")

    monkeypatch.setattr(model_switch, "persist_model_selection", forbidden_write)
    switched = []
    def resolve_switch(**kwargs):
        switched.append(kwargs)
        return model_switch.ModelSwitchResult(True, new_model=kwargs["raw_input"],
                                              target_provider=kwargs["explicit_provider"])
    monkeypatch.setattr(model_switch, "switch_model", resolve_switch)
    from hermes_cli.observability import shared_metrics_events
    monkeypatch.setattr(shared_metrics_events, "record_model_switch", lambda **kwargs: None)
    session = {"session_key": "durable-child", "agent": None}
    namespace = dict(vars(gateway_model), **vars(methods_config_set))
    for name, value in list(namespace.items()):
        if isinstance(value, types.FunctionType) and value.__module__ in {gateway_model.__name__, methods_config_set.__name__}:
            namespace[name] = rebind(value, namespace)
    namespace.update(_current_model_runtime=lambda *args: ("openai-api", "codex/stored", "", ""), _sessions={"ui-resumed": session}, _write_config_key=forbidden_write,
                     _save_cfg=forbidden_write, _load_cfg_raw=lambda: {}, _resolve_model=lambda: "codex/stored",
                     _ok=lambda rid, result: {"result": result},
                     _err=lambda rid, code, message: {"error": {"code": code, "message": message}},
                     _session_profile_runtime_scope=lambda session: nullcontext(),
                     _start_agent_build=lambda *args: None, _wait_agent=lambda *args: None,
                     _cfgset_await_agent=lambda *args: None,
                     _expensive_model_confirm=lambda *args: None,
                     _switch_away_provider=lambda *args: None, _session_source=lambda *args: "test",
                     _sess_nowait=lambda *args: (None, {"error": {"code": 4001}}))
    namespace["_apply_model_switch"] = rebind(gateway_model._apply_model_switch, namespace)
    namespace["_CONFIG_SETTERS"] = {key: rebind(methods_config_set._CONFIG_SETTERS[key], namespace)
                                  for key in ("model", "reasoning")}
    handler = rebind(dict(methods_config_set._registry._pending)["config.set"], namespace)
    calls = []
    class Client:
        def call(self, method, params, **kwargs):
            calls.append((method, params))
            if method in {"session.resume", "session.create"}:
                return {"session_id": "ui-resumed", "resumed": "durable-child", "session_key": "durable-child",
                        "info": {"model": "codex/stored"}}
            response = handler(1, params)
            assert "error" not in response, response
            return response["result"]
    if selection.get("reasoning_effort") == "show":
        with pytest.raises(tui_rpc.TuiProtocolError, match="reasoning"):
            tui_rpc.start_session(Client(), profile="builder", mode=mode, session_id="durable-parent",
                                  title="ignored", cwd="/ignored", **selection)
        assert calls == []
        return
    identity = tui_rpc.start_session(Client(), profile="builder", mode=mode, session_id="durable-parent",
                                     title="ignored", cwd="/ignored", **selection)
    assert identity["child_session_id"] == "durable-child"
    for method, params in calls[1:]:
        assert method == "config.set"
        assert params["session_id"] == "ui-resumed" and params["scope"] == "session"
    if selection.get("model") or selection.get("provider"):
        assert switched[0]["is_global"] is False
        assert session["model_override"]["model"] == selection.get("model", "codex/stored")
    if selection.get("reasoning_effort"):
        from hermes_constants import parse_reasoning_effort
        assert session["create_reasoning_override"] == parse_reasoning_effort(selection["reasoning_effort"])
    assert handler(1, {"session_id": "stale", "key": "reasoning", "value": "high", "scope": "session"})["error"]["code"] == 4001


@pytest.mark.parametrize("reply", [{"confirm_required": True, "confirm_message": "operator confirmation needed"},
                                    {"scope": "global"}])
def test_resume_refuses_confirmation_or_global_scope(reply):
    class Client:
        def call(self, method, params, **kwargs):
            return {"session_id": "ui-1", "resumed": "child-1"} if method == "session.resume" else reply
    with pytest.raises(tui_rpc.TuiRpcError):
        tui_rpc.start_session(Client(), profile="builder", mode="resume", session_id="child-1",
                              title="", cwd="/tmp", model="codex/example")


def test_large_resume_response_is_bounded_without_changing_identity_or_model_history():
    class NativeLikeClient:
        def __init__(self):
            self.params = None
            self.model_history = [{"role": "user", "content": "private" * 400_000}]

        def call(self, method, params, **kwargs):
            assert method == "session.resume"
            self.params = params
            response = {"jsonrpc": "2.0", "id": 1, "result": {
                "session_id": "runtime-1", "resumed": "stored-1",
                "message_count": len(self.model_history),
                "messages": [] if params["omit_messages"] else self.model_history,
            }}
            wire = (json.dumps(response, separators=(",", ":")) + "\n").encode()
            self.wire_bytes = len(wire)
            legacy = {**response, "result": {**response["result"], "messages": self.model_history}}
            self.legacy_wire_bytes = len((json.dumps(legacy, separators=(",", ":")) + "\n").encode())
            return response["result"]

    client = NativeLikeClient()
    identity = tui_rpc.start_session(
        client, profile="builder", mode="resume", session_id="stored-1",
        title="ignored", cwd="/ignored",
    )
    assert identity == {"ui_session_id": "runtime-1", "child_session_id": "stored-1"}
    assert client.wire_bytes < 2_000_000
    assert client.legacy_wire_bytes > 2_000_000
    assert len(client.model_history) == 1
    assert client.params is not None
    assert "cwd" not in client.params and "model" not in client.params


@pytest.mark.parametrize("exact", [True, False])
def test_oversized_frame_diagnostic_is_bounded_safe_and_actionable(exact):
    secret = "PRIVATE_TRANSCRIPT_MARKER"
    bound = 128
    # A complete frame gives an exact size; an unterminated one gives only a lower bound.
    raw = (secret * 10 + "\n" if exact else secret * 10).encode()
    proc = FakeProcess([])
    proc.stdout = io.BytesIO(raw)
    client = tui_rpc.TuiRpcClient(proc, max_frame_bytes=bound)  # type: ignore[arg-type]
    if exact:
        # A complete buffered frame allows an exact length; streamed reads are
        # intentionally capped at bound+1 and can report only that lower bound.
        client._stdout_buffer.extend(raw)
        proc.stdout = io.BytesIO()
    with pytest.raises(tui_rpc.TuiProtocolError) as failure:
        client.call("session.resume", {"session_id": "stored-1"}, timeout=1, stage="session_creating")
    diagnostic = str(failure.value)
    assert "configured=128 bytes" in diagnostic
    assert (f"observed={len(raw)} bytes" if exact else "observed>=129 bytes") in diagnostic
    assert "stage=session_creating, request_id=1, method=session.resume" in diagnostic
    assert "frame_type=unparsed" in diagnostic and "omit_messages=true" in diagnostic
    assert secret not in diagnostic


def test_close_reaps_process_and_is_idempotent():
    proc = FakeProcess([])
    client = tui_rpc.TuiRpcClient(proc)
    client.close()
    client.close()
    assert proc.returncode == 0
    assert proc.stdin.closed and proc.stdout.closed and proc.stderr.closed


@pytest.mark.parametrize("timeout", [False, True])
def test_runner_poll_flushes_pending_journal_text_after_active_and_idle_reads(timeout):
    frame = {"method": "event", "params": {"type": "status.update"}}

    class Client:
        def read_event(self, poll_timeout):
            if timeout:
                raise tui_rpc.TuiTransportError("TUI RPC response timed out")
            return frame

    journal = RecordingJournal()
    assert tui_runner._poll_event(Client(), 0.15, journal) == (None if timeout else frame)
    assert journal.flushes == 1


def test_runner_poll_flushes_before_propagating_transport_error():
    class Client:
        def read_event(self, _timeout):
            raise tui_rpc.TuiTransportError("TUI RPC EOF")

    journal = RecordingJournal()
    with pytest.raises(tui_rpc.TuiTransportError, match="EOF"):
        tui_runner._poll_event(Client(), 0.15, journal)
    assert journal.flushes == 1


def test_runner_publishes_ready_status_transitions_after_success(tmp_path, monkeypatch):
    run = runner_run(tmp_path, "pd_20260721_120001_bbbbbb", prompt="prompt", fields={
        "requested_session_id": "", "session_title": "test", "timeout_seconds": 5,
        "effective_execution": {}, "effective_capabilities": {},
    })
    clock = [0.0]
    monkeypatch.setattr(tui_runner, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    transitions, budgets = [], []
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

    monkeypatch.setattr(tui_runner.core, "acquire_concurrency_slot", runner_slot)

    complete = runner_complete('{"status":"ok","summary":"done","artifacts":[],"errors":[],"next_steps":[]}')


    monkeypatch.setattr(tui_runner.tui_rpc, "launch_gateway", lambda **kwargs: CompleteClient(complete, exit_code=0))
    def start_session(*args, **kwargs):
        budgets.append(kwargs["timeout"])
        clock[0] += 3.0
        return {"ui_session_id": "ui-1", "child_session_id": "child-1"}

    monkeypatch.setattr(tui_runner.tui_rpc, "start_session", start_session)
    monkeypatch.setattr(tui_runner.tui_rpc, "submit", lambda *args, **kwargs: budgets.append(kwargs["timeout"]))
    result = tui_runner.execute(run)
    assert result["success"] is True
    assert budgets == [5.0, 2.0]
    assert transitions.index("transport_ready") < transitions.index("session_creating")
    assert transitions.index("session_ready") < transitions.index("agent_initializing")
    status = json.loads((run / "status.json").read_text(encoding="utf-8"))
    assert status["startup_readiness"]["state"] == "ready"
    assert status["startup_readiness"]["elapsed_ms"] >= 0


def test_bootstrap_stage_evidence_survives_native_import_failure(tmp_path, monkeypatch):
    import child_bootstrap
    import types

    events = tmp_path / "approval_events.jsonl"
    monkeypatch.setenv("PROVIDER_SECRET", "must-not-appear")
    monkeypatch.setattr(child_bootstrap, "install_policy", lambda *_args: None)
    plugins = types.ModuleType("hermes_cli.plugins")
    plugins.discover_plugins = lambda: None
    monkeypatch.setitem(sys.modules, "hermes_cli", types.ModuleType("hermes_cli"))
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins", plugins)
    gateway = types.ModuleType("tui_gateway")
    monkeypatch.setitem(sys.modules, "tui_gateway", gateway)
    monkeypatch.delitem(sys.modules, "tui_gateway.entry", raising=False)
    with pytest.raises(ModuleNotFoundError):
        child_bootstrap.main([
            "--approval-mode", "deny", "--events-path", str(events), "--tui-gateway",
        ])
    records = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
    assert [(record["reason"], record["outcome"]) for record in records] == [
        ("bootstrap_policy_filter", "enter"), ("bootstrap_policy_filter", "exit"),
        ("discover_plugins", "enter"), ("discover_plugins", "exit"),
        ("native_entry_import", "enter"), ("native_entry_import", "exit"),
    ]
    elapsed = [record["elapsed_ms"] for record in records]
    assert elapsed == sorted(elapsed)
    assert all(0 <= value <= 600_000 for value in elapsed)
    assert "must-not-appear" not in events.read_text(encoding="utf-8")


def test_bootstrap_discovery_failure_preserves_entry_exit_evidence(tmp_path, monkeypatch):
    import child_bootstrap
    import types

    events = tmp_path / "approval_events.jsonl"
    monkeypatch.setattr(child_bootstrap, "install_policy", lambda *_args: None)
    plugins = types.ModuleType("hermes_cli.plugins")

    def fail_discovery():
        raise RuntimeError("discovery stopped")

    plugins.__dict__["discover_plugins"] = fail_discovery
    monkeypatch.setitem(sys.modules, "hermes_cli", types.ModuleType("hermes_cli"))
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins", plugins)
    with pytest.raises(RuntimeError, match="discovery stopped"):
        child_bootstrap.main([
            "--approval-mode", "deny", "--events-path", str(events), "--tui-gateway",
        ])
    records = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
    assert [(record["reason"], record["outcome"]) for record in records] == [
        ("bootstrap_policy_filter", "enter"), ("bootstrap_policy_filter", "exit"),
        ("discover_plugins", "enter"), ("discover_plugins", "exit"),
    ]
    assert "discovery stopped" not in events.read_text(encoding="utf-8")


def test_runner_readiness_timeout_persists_stage_and_failure(tmp_path, monkeypatch):
    run = runner_run(tmp_path, "pd_20260721_120001_timeout")
    monkeypatch.setattr(tui_runner, "_environment", lambda *_args: {})

    monkeypatch.setattr(tui_runner.core, "acquire_concurrency_slot", runner_slot)

    class Client:
        stderr_tail = ""
        process = type("Process", (), {"pid": os.getpid(), "poll": lambda self: 0})()

        def wait_ready(self, **kwargs):
            raise tui_rpc.TuiTransportError("TUI RPC response timed out")

        def close(self, **kwargs):
            pass

    monkeypatch.setattr(tui_runner.tui_rpc, "launch_gateway", lambda **kwargs: Client())
    result = tui_runner.execute(run)
    status = json.loads((run / "status.json").read_text(encoding="utf-8"))
    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["result"]["execution_status"] == "failed"
    assert result["result"]["contract_status"] == "not_evaluated"
    assert status["startup_readiness"]["state"] == "failed"
    assert status["startup_readiness"]["elapsed_ms"] >= 0


def test_client_close_allows_bounded_graceful_gateway_teardown():
    proc = subprocess.Popen(
        [sys.executable, "-c", "import sys,time; sys.stdin.read(); time.sleep(3)"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True,
    )
    client = tui_rpc.TuiRpcClient(proc)
    client.close()
    assert proc.returncode == 0
    assert all(stream is not None and stream.closed for stream in (proc.stdin, proc.stdout, proc.stderr))


def test_runner_nonzero_transport_exit_overrides_complete_ok(tmp_path, monkeypatch):
    run = runner_run(tmp_path, "pd_20260721_120001_cccccc", prompt="prompt", fields={
        "requested_session_id": "", "session_title": "test", "effective_execution": {}, "effective_capabilities": {},
    })
    monkeypatch.setattr(tui_runner, "_environment", lambda request, run_dir: {})

    monkeypatch.setattr(tui_runner.core, "acquire_concurrency_slot", runner_slot)
    complete = runner_complete()


    monkeypatch.setattr(tui_runner.tui_rpc, "launch_gateway", lambda **kwargs: CompleteClient(complete, exit_code=17))
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


def _execute_with_control(
    tmp_path, monkeypatch, command_type, control_call, *, extra_command_type=None,
    return_trace=False, client_factory=None, timeout_seconds=10,
):
    run = runner_run(tmp_path, f"pd_control_{command_type}", prompt="prompt", fields={
        "timeout_seconds": timeout_seconds, "requested_session_id": "", "session_title": "control",
        "effective_execution": {}, "effective_capabilities": {},
    })
    _, commands, acks = core._control_dirs(run)
    command = {
        "schema_version": 1, "task_id": run.name, "type": command_type,
        "command_id": "cmd-1", "seq": 1, "created_at": core.now_iso(),
        "payload": {"text": "redirect"} if command_type == "steer" else {},
    }
    command_path = commands / "000000000001-cmd-1.json"
    command_path.write_text(json.dumps(command), encoding="utf-8")
    extra_path = None
    if extra_command_type:
        extra = {
            "schema_version": 1, "task_id": run.name, "type": extra_command_type,
            "command_id": "cmd-2", "seq": 2, "created_at": core.now_iso(),
            "payload": {"text": "late redirect"} if extra_command_type == "steer" else {},
        }
        extra_path = commands / "000000000002-cmd-2.json"
        extra_path.write_text(json.dumps(extra), encoding="utf-8")
    monkeypatch.setattr(tui_runner, "_environment", lambda request, run_dir: {})

    monkeypatch.setattr(tui_runner.core, "acquire_concurrency_slot", runner_slot)
    complete = runner_complete()


    client = client_factory(complete) if client_factory else CompleteClient(complete)
    monkeypatch.setattr(tui_runner.tui_rpc, "launch_gateway", lambda **kwargs: client)
    monkeypatch.setattr(
        tui_runner.tui_rpc, "start_session",
        lambda *args, **kwargs: {"ui_session_id": "ui-1", "child_session_id": "child-1"},
    )
    monkeypatch.setattr(tui_runner.tui_rpc, "submit", lambda *args, **kwargs: {})
    control_call()
    # All fixture/process setup and command publication are complete here.
    prepared_at = time.monotonic()
    result = tui_runner.execute(run)
    finished_at = time.monotonic()
    ack = json.loads((acks / command_path.name).read_text(encoding="utf-8"))
    trace = {"client": client, "extra_path": extra_path, "acks": acks,
             "prepared_at": prepared_at, "finished_at": finished_at}
    return (result, ack, trace) if return_trace else (result, ack)


def test_runner_steer_4010_is_rejected_without_failing_turn(tmp_path, monkeypatch):
    def arrange():
        monkeypatch.setattr(
            tui_runner.tui_rpc, "steer",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                tui_rpc.TuiRemoteError(4010, "agent does not support steer")
            ),
        )

    result, ack = _execute_with_control(tmp_path, monkeypatch, "steer", arrange)
    assert result["status"] == "completed"
    assert ack["state"] == "rejected"


def test_runner_steer_timeout_without_followup_fails_closed(tmp_path, monkeypatch):
    def arrange():
        monkeypatch.setattr(
            tui_runner.tui_rpc, "steer",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                tui_rpc.TuiTransportError("TUI RPC response timed out")
            ),
        )

    result, ack = _execute_with_control(tmp_path, monkeypatch, "steer", arrange, timeout_seconds=1)
    assert result["status"] == "failed"
    assert result["error_code"] == "steer_outcome_uncertain"
    assert result["success"] is False
    assert ack["state"] == "delivery_unknown"


@pytest.mark.parametrize("followup", ["none", "complete", "incomplete"])
def test_runner_queued_steer_never_turns_quiet_into_success(tmp_path, monkeypatch, followup):
    def arrange():
        monkeypatch.setattr(tui_runner.tui_rpc, "steer", lambda *args, **kwargs: {"status": "queued"})

    class DelayedClient(CompleteClient):
        def __init__(self, complete):
            super().__init__(complete)
            self.events = 0
            self.calls = []

        def read_event(self, _timeout):
            self.events += 1
            if self.events == 1:
                return self.complete
            if self.events == 2:
                return {"method": "event", "params": {"type": "session.info", "session_id": "ui-1", "payload": {}}}
            if followup != "none" and self.events == 3:
                time.sleep(0.6)  # A delayed native follow-up exceeds the old quiet oracle.
                return {"method": "event", "params": {"type": "message.start", "session_id": "ui-1", "payload": {}}}
            if followup == "complete" and self.events == 4:
                return {"method": "event", "params": {"type": "message.complete", "session_id": "ui-1", "payload": {
                    "status": "complete", "text": '{"status":"ok","summary":"follow-up"}',
                }}}
            if followup == "complete" and self.events == 5:
                return {"method": "event", "params": {"type": "session.info", "session_id": "ui-1", "payload": {}}}
            time.sleep(min(0.02, _timeout))
            return None

        def call(self, *args, **kwargs):
            self.calls.append(args[0])
            return {}

    published_at = []
    real_publish = core.publish_terminal_run

    def publish(run_dir, result, updates):
        published_at.append(time.monotonic())
        return real_publish(run_dir, result, updates)

    monkeypatch.setattr(tui_runner.core, "publish_terminal_run", publish)
    started = time.monotonic()
    result, ack, trace = _execute_with_control(
        tmp_path, monkeypatch, "steer", arrange,
        client_factory=DelayedClient, return_trace=True, timeout_seconds=3,
    )
    elapsed = time.monotonic() - started
    assert len(published_at) == 1
    assert published_at[0] - started <= elapsed
    if followup == "complete":
        # A settled observed follow-up can complete without exhausting the run deadline.
        assert 0.6 <= elapsed < 1.8
        assert published_at[0] - started < 1.8
    elif followup == "none":
        # The 1.2s bound classifies uncertainty, never success or a missed steer.
        assert 1.1 <= elapsed < 2.5
        assert published_at[0] - started < 2.5
    else:
        # A started, unfinished turn remains under the actual task deadline.
        assert 2.8 <= elapsed < 4.2
        assert published_at[0] - started < 4.2
    assert ack["state"] == "accepted"
    assert result["success"] is (followup == "complete")
    assert result["status"] == {"none": "failed", "complete": "completed", "incomplete": "timed_out"}[followup]
    assert result["error_code"] == {
        "none": "steer_outcome_uncertain", "complete": None, "incomplete": "timeout",
    }[followup]
    if followup == "incomplete":
        assert result["result"]["execution_status"] == "timed_out"
        assert result["result"]["contract_status"] == "not_evaluated"
        assert result["result"]["raw_output_path"] == str(tmp_path / "pd_control_steer" / "stdout.txt")
    else:
        assert result["result"]["summary"] == ("follow-up" if followup == "complete" else "done")
    assert trace["client"].calls == []
    state = json.loads((tmp_path / "pd_control_steer" / "status.json").read_text(encoding="utf-8"))
    assert state["followup_observed"] is (followup != "none")
    assert state["followup_settled"] is (followup == "complete")
    assert state["steer_delivery_state"] == "unknown"


@pytest.mark.parametrize("delivery", ["fresh", "merged", "replayed", "inactive_twin"])
def test_runner_native_steer_occurrences_survive_compression(tmp_path, monkeypatch, delivery):
    from contextlib import closing
    from hermes_state import SessionDB
    from agent.prompt_builder import steer_user_row

    with closing(SessionDB(tmp_path / "state.db")) as db:
        db.create_session("child-1", source="cli", profile_name="reviewer")
        db.append_message("child-1", **steer_user_row("redirect"))
        original = db.get_messages_as_conversation("child-1", include_row_ids=True)[0]
        if delivery == "inactive_twin":
            db.rewind_to_message("child-1", original["_row_id"])
            db.append_message("child-1", **steer_user_row("redirect"))
            original = db.get_messages_as_conversation("child-1", include_row_ids=True)[0]
        db.append_message("child-1", role="assistant", content="previous completion")
        db.append_message("child-1", role="user", content="prompt")
        calls = []

        def native_steer(*args, **kwargs):
            calls.append(args[2])
            if delivery == "fresh" or (delivery == "merged" and len(calls) == 2):
                db.append_message("child-1", **steer_user_row("\n".join(calls)))
            if delivery != "merged" or len(calls) == 2:
                db.publish_compression_child(
                    parent_session_id="child-1", child_session_id="child-2", source="cli",
                    profile_name="reviewer", require_compression_lease=False,
                    messages=db.get_messages_as_conversation("child-1", include_row_ids=True),
                )
            return {"status": "queued"}

        class SettledClient(CompleteClient):
            def read_event(self, _timeout):
                complete, self.complete = self.complete, None
                return complete or {"method": "event", "params": {
                    "type": "session.info", "session_id": "ui-1", "payload": {
                        "stored_session_id": "child-2", "profile_name": "reviewer",
                    },
                }}

        result, ack, trace = _execute_with_control(
            tmp_path, monkeypatch, "steer",
            lambda: monkeypatch.setattr(tui_runner.tui_rpc, "steer", native_steer),
            client_factory=SettledClient, return_trace=True,
            extra_command_type="steer" if delivery == "merged" else None,
        )
        cloned = db.get_messages_as_conversation("child-2", include_row_ids=True)[0]
        assert cloned["message_uid"] == original["message_uid"]
        assert cloned["_row_id"] != original["_row_id"]
        expected = delivery in {"fresh", "merged"}
        assert ack["state"] == "accepted"
        assert result["success"] is expected
        assert result["status"] == ("completed" if expected else "failed")
        assert result["error_code"] == (None if expected else "steer_outcome_uncertain")
        state = core.read_json_file(tmp_path / "pd_control_steer" / "status.json")
        assert state["followup_observed"] is False
        assert state["steer_delivery_state"] == ("delivered" if expected else "unknown")
        assert trace["client"].calls == []
        if delivery == "merged":
            assert core.read_json_file(trace["acks"] / trace["extra_path"].name)["state"] == "accepted"
        db.append_message("child-2", **steer_user_row("future turn"))
        future_uid = db.get_messages("child-2")[-1]["message_uid"]
        snapshot = core.native.steer_snapshot(tmp_path, "child-1", deadline=time.monotonic() + 10)
        assert snapshot is not None and future_uid not in snapshot
        monkeypatch.setattr(core.native, "STEER_SNAPSHOT_MAX_ROWS", 1)
        assert core.native.steer_snapshot(tmp_path, "child-1", deadline=time.monotonic() + 10) is None


@pytest.mark.parametrize("stage", ["baseline", "receipt"])
def test_runner_steer_snapshot_expiry_cannot_dispatch_or_complete(tmp_path, monkeypatch, stage):
    import hashlib
    from agent.prompt_builder import format_steer_marker

    monotonic, controls = time.monotonic, []

    def snapshot(*args, **kwargs):
        baseline = kwargs.get("include_inactive", False)
        if baseline == (stage == "baseline"):
            monkeypatch.setattr(time, "monotonic", lambda: monotonic() + 2)
        return {} if baseline else {
            "fresh": hashlib.sha256(format_steer_marker("redirect").lstrip().encode()).hexdigest(),
        }

    def arrange():
        monkeypatch.setattr(tui_runner.core.native, "steer_snapshot", snapshot)
        monkeypatch.setattr(tui_runner.tui_rpc, "steer",
                            lambda *args, **kwargs: controls.append(args[2]) or {"status": "queued"})

    class SettledClient(CompleteClient):
        def read_event(self, _timeout):
            complete, self.complete = self.complete, None
            return complete or {"method": "event", "params": {
                "type": "session.info", "session_id": "ui-1", "payload": {},
            }}

    result, ack = _execute_with_control(
        tmp_path, monkeypatch, "steer", arrange, client_factory=SettledClient, timeout_seconds=1,
    )
    assert controls == ([] if stage == "baseline" else ["redirect"])
    assert ack["state"] == ("rejected" if stage == "baseline" else "accepted")
    assert result["status"] == "timed_out"
    assert result["error_code"] == "timeout"
    assert result["success"] is False
    assert result["result"]["execution_status"] == "timed_out"
    assert core.read_json_file(tmp_path / "pd_control_steer" / "status.json").get("steer_delivery_state") != "delivered"


def test_runner_very_late_followup_is_unknown_not_missed(tmp_path, monkeypatch):
    def arrange():
        monkeypatch.setattr(tui_runner.tui_rpc, "steer", lambda *args, **kwargs: {"status": "queued"})

    class LateClient(CompleteClient):
        def __init__(self, complete):
            super().__init__(complete)
            self.reads = 0
            self.observed_wait = 0.0
            self.late_followup_at = 1.5
            self.followup_emitted = False

        def read_event(self, timeout):
            self.reads += 1
            if self.reads == 1:
                return self.complete
            self.observed_wait += timeout
            if self.observed_wait >= self.late_followup_at:
                self.followup_emitted = True
                return {"method": "event", "params": {
                    "type": "message.start", "session_id": "ui-1", "payload": {},
                }}
            time.sleep(timeout)
            return None

    published_at = []
    real_publish = core.publish_terminal_run

    def publish(run_dir, result, updates):
        published_at.append(time.monotonic())
        return real_publish(run_dir, result, updates)

    monkeypatch.setattr(tui_runner.core, "publish_terminal_run", publish)
    started = time.monotonic()
    result, ack, trace = _execute_with_control(
        tmp_path, monkeypatch, "steer", arrange, client_factory=LateClient,
        return_trace=True, timeout_seconds=4,
    )
    elapsed = time.monotonic() - started
    assert len(published_at) == 1
    assert published_at[0] - started < 2.5
    assert 1.1 <= elapsed < 2.5
    assert trace["client"].reads > 2
    assert trace["client"].observed_wait < trace["client"].late_followup_at
    assert trace["client"].followup_emitted is False
    assert trace["client"].calls == []
    assert ack["state"] == "accepted"
    assert result["status"] == "failed"
    assert result["error_code"] == "steer_outcome_uncertain"
    assert result["success"] is False
    assert result["result"]["summary"] == "done"
    assert core.read_json_file(tmp_path / "pd_control_steer" / "status.json")["steer_delivery_state"] == "unknown"


def test_runner_applies_steer_over_real_stdio_gateway(tmp_path, monkeypatch):
    run = runner_run(tmp_path, "pd_20260824_120000_stdio1", prompt="initial prompt", fields={
        "timeout_seconds": 1, "requested_session_id": "", "session_title": "stdio steer",
        "requested_execution": {}, "effective_execution": {}, "effective_capabilities": {},
        "approval_policy": {}, "resolved_output_mode": "json",
    })
    methods_path = tmp_path / "methods.txt"
    _, commands, acks = core._control_dirs(run)
    command = {
        "schema_version": 1, "task_id": run.name, "type": "steer",
        "command_id": "stdio-steer", "seq": 1, "created_at": core.now_iso(),
        "payload": {"text": "redirect through stdio"},
    }
    command_path = commands / "000000000001-stdio-steer.json"

    gateway_code = r'''
import json
import sys

methods_path = sys.argv[1]

def send(frame):
    sys.stdout.write(json.dumps(frame, separators=(",", ":")) + "\n")
    sys.stdout.flush()

send({"jsonrpc": "2.0", "method": "event", "params": {
    "type": "gateway.ready", "session_id": "", "payload": {},
}})
for line in sys.stdin:
    request = json.loads(line)
    method = request["method"]
    with open(methods_path, "a", encoding="utf-8") as handle:
        handle.write(method + "\n")
    if method == "session.create":
        result = {"session_id": "ui-stdio", "session_key": "durable-stdio"}
    elif method == "prompt.submit":
        result = {"accepted": True}
    elif method == "session.steer":
        result = {"status": "queued"}
    elif method == "session.close":
        result = {}
    else:
        result = {}
    send({"jsonrpc": "2.0", "id": request["id"], "result": result})
    if method == "prompt.submit":
        send({"jsonrpc": "2.0", "method": "event", "params": {
            "type": "message.complete", "session_id": "ui-stdio", "payload": {
                "status": "complete", "text": json.dumps({"status": "ok", "summary": "initial"}),
            },
        }})
    if method == "session.steer":
        send({"jsonrpc": "2.0", "method": "event", "params": {
            "type": "message.start", "session_id": "ui-stdio", "payload": {},
        }})
        send({"jsonrpc": "2.0", "method": "event", "params": {
            "type": "message.complete", "session_id": "ui-stdio", "payload": {
                "status": "complete", "text": json.dumps({
                    "status": "ok", "summary": "STEER_STDIO_OK",
                    "artifacts": [], "errors": [], "next_steps": [],
                }),
            },
        }})
        send({"jsonrpc": "2.0", "method": "event", "params": {
            "type": "session.info", "session_id": "ui-stdio", "payload": {},
        }})
'''

    monkeypatch.setattr(tui_runner, "_environment", lambda request, run_dir: {})
    monkeypatch.setattr(
        tui_runner, "_gateway_command",
        lambda request, run_dir: [sys.executable, "-u", "-c", gateway_code, str(methods_path)],
    )

    monkeypatch.setattr(tui_runner.core, "acquire_concurrency_slot", runner_slot)

    poll_entered = threading.Event()
    command_written = threading.Event()
    real_poll_event = tui_runner._poll_event
    real_launch_gateway = tui_runner.tui_rpc.launch_gateway
    holder = {}

    def poll_event(*args, **kwargs):
        poll_entered.set()
        assert command_written.wait(timeout=2), "producer did not publish steer"
        return real_poll_event(*args, **kwargs)

    def launch_gateway(**kwargs):
        client = real_launch_gateway(**kwargs)
        holder["client"] = client
        return client

    def enqueue_steer() -> None:
        assert poll_entered.wait(timeout=2), "runner never entered event polling"
        core.json_safe_write(command_path, command)
        command_written.set()

    monkeypatch.setattr(tui_runner, "_poll_event", poll_event)
    monkeypatch.setattr(tui_runner.tui_rpc, "launch_gateway", launch_gateway)
    producer = threading.Thread(target=enqueue_steer, name="stdio-steer-producer")
    producer.start()

    result = tui_runner.execute(run)
    producer.join(timeout=2)

    ack = json.loads((acks / command_path.name).read_text(encoding="utf-8"))
    methods = methods_path.read_text(encoding="utf-8").splitlines()
    status = json.loads((run / "status.json").read_text(encoding="utf-8"))
    assert result["success"] is True
    assert result["status"] == "completed"
    assert result["error_code"] is None
    assert result["result"]["summary"] == "STEER_STDIO_OK"
    assert command_written.is_set()
    assert ack["state"] == "accepted"
    assert methods == ["session.create", "prompt.submit", "session.steer"]
    assert status["transport_alive"] is False
    process = holder["client"].process
    assert process.returncode == 0
    assert process.stdin.closed and process.stdout.closed and process.stderr.closed
    if hasattr(os, "waitpid"):
        with pytest.raises(ChildProcessError):
            os.waitpid(process.pid, os.WNOHANG)


def test_runner_cancel_preserves_cleanup_reserve_and_reaps_stubborn_process(
    tmp_path, monkeypatch,
):
    holder = {}

    def factory(_complete):
        proc = subprocess.Popen(
            [
                sys.executable, "-c",
                "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('READY', flush=True); time.sleep(30)",
            ],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,
        )
        assert proc.stdout and proc.stdout.readline() == b"READY\n"
        rpc_client = tui_rpc.TuiRpcClient(proc)

        class StubbornClient:
            process = proc
            stderr_tail = ""
            close_kwargs = None
            read_calls = 0
            calls = []

            def wait_ready(self, **kwargs):
                return None

            def read_event(self, _timeout):
                self.read_calls += 1
                raise AssertionError("cancelled runner must not resume event polling")

            def call(self, *args, **kwargs):
                self.calls.append((args, kwargs))
                return {}

            def close(self, **kwargs):
                self.close_kwargs = kwargs
                rpc_client.close(**kwargs)

        client = StubbornClient()
        holder["client"] = client
        return client

    def arrange():
        monkeypatch.setattr(tui_runner, "CANCEL_GRACE_SECONDS", 0.3)
        monkeypatch.setattr(
            tui_runner.tui_rpc, "interrupt",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                tui_rpc.TuiTransportError("TUI RPC response timed out")
            ),
        )

    started = time.monotonic()
    result, ack, trace = _execute_with_control(
        tmp_path, monkeypatch, "cancel", arrange,
        return_trace=True, client_factory=factory,
    )
    elapsed = time.monotonic() - started
    client = holder["client"]
    assert result["status"] == "cancelled"
    assert ack["state"] == "accepted"
    assert client.read_calls == 0
    assert client.close_kwargs and client.close_kwargs["deadline"] > started
    assert client.process.poll() is not None
    assert client.process.returncode == -signal.SIGKILL
    cleanup_elapsed = trace["finished_at"] - trace["prepared_at"]
    # Original .8s control bound, now excludes fixture/interpreter startup.
    assert cleanup_elapsed < 0.8
    # Separate total task deadline (10s fixture contract), not a relaxed cleanup bound.
    assert elapsed < 10
    assert trace["client"] is client
    assert client.process.stdin.closed and client.process.stdout.closed and client.process.stderr.closed
    (tmp_path / "cancel-timing-receipt.json").write_text(json.dumps({
        "total_seconds": elapsed, "prepared_control_seconds": cleanup_elapsed,
        "cleanup_bound_seconds": 0.8, "task_deadline_seconds": 10,
        "returncode": client.process.returncode, "pipes_closed": True,
    }))


def test_runner_cancel_timeout_is_authoritative_and_bounded(tmp_path, monkeypatch):
    interrupt_timeouts = []

    def arrange():
        monkeypatch.setattr(tui_runner, "CANCEL_GRACE_SECONDS", 0.01)

        def interrupt(*args, **kwargs):
            interrupt_timeouts.append(kwargs["timeout"])
            raise tui_rpc.TuiTransportError("TUI RPC response timed out")

        monkeypatch.setattr(tui_runner.tui_rpc, "interrupt", interrupt)

    result, ack, trace = _execute_with_control(
        tmp_path, monkeypatch, "cancel", arrange,
        extra_command_type="steer", return_trace=True,
    )
    assert result["status"] == "cancelled"
    assert result["result"]["execution_status"] == "cancelled"
    assert result["result"]["contract_status"] == "not_evaluated"
    assert ack["state"] == "accepted"
    assert "delivery unknown" in ack["detail"]
    assert interrupt_timeouts and interrupt_timeouts[0] <= 0.005
    assert trace["client"].calls == []
    assert trace["client"].close_kwargs and "deadline" in trace["client"].close_kwargs
    assert not (trace["acks"] / trace["extra_path"].name).exists()


@pytest.mark.parametrize(
    "failure",
    [
        tui_rpc.TuiProtocolError("malformed response"),
        tui_rpc.TuiTransportError("TUI stdout EOF"),
    ],
)
def test_runner_non_timeout_steer_failure_remains_fatal(tmp_path, monkeypatch, failure):
    def arrange():
        monkeypatch.setattr(
            tui_runner.tui_rpc, "steer",
            lambda *args, **kwargs: (_ for _ in ()).throw(failure),
        )

    result, ack = _execute_with_control(tmp_path, monkeypatch, "steer", arrange)
    assert result["status"] == "failed"
    assert result["error_code"] == "tui_transport_error"
    assert ack["state"] == "rejected"


@pytest.mark.parametrize(
    "failure, detail_fragment",
    [
        (tui_rpc.TuiRemoteError(4999, "cannot interrupt"), "rejected"),
        (tui_rpc.TuiProtocolError("malformed response"), "protocol failure"),
        (tui_rpc.TuiTransportError("TUI stdout EOF"), "delivery unknown"),
    ],
)
def test_runner_cancel_failures_remain_authoritative(
    tmp_path, monkeypatch, failure, detail_fragment,
):
    def arrange():
        monkeypatch.setattr(tui_runner, "CANCEL_GRACE_SECONDS", 0.01)
        monkeypatch.setattr(
            tui_runner.tui_rpc, "interrupt",
            lambda *args, **kwargs: (_ for _ in ()).throw(failure),
        )

    result, ack = _execute_with_control(tmp_path, monkeypatch, "cancel", arrange)
    assert result["status"] == "cancelled"
    assert result["result"]["execution_status"] == "cancelled"
    assert result["result"]["contract_status"] == "not_evaluated"
    assert ack["state"] == "accepted"
    assert detail_fragment in ack["detail"]
