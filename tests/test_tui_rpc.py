"""Focused tests for Profile Delegate's Hermes TUI JSON-RPC transport."""
from __future__ import annotations

import io
import json
import os
import signal
import subprocess
import sys
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


def test_rpc_dispatch_backpressure_is_bounded_and_transport_not_reusable():
    import fcntl
    import subprocess
    import sys
    import time

    # Child acknowledges readiness, then waits for EOF without ever reading stdin.
    proc = subprocess.Popen(
        [sys.executable, "-c", "import os,select; os.write(1,b'ready\\n'); select.select([],[],[],30)"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True,
    )
    client = tui_rpc.TuiRpcClient(proc)
    try:
        assert proc.stdout.readline() == b"ready\n"
        capacity = fcntl.fcntl(proc.stdin.fileno(), fcntl.F_GETPIPE_SZ)
        started = time.monotonic()
        with pytest.raises(tui_rpc.TuiTransportError, match=r"dispatch timed out.*written="):
            client.call("session.submit", {"text": "x" * (capacity * 2)}, timeout=0.1)
        assert time.monotonic() - started < 2
        with pytest.raises(tui_rpc.TuiTransportError, match="closed"):
            client.call("session.status", {}, timeout=0.1)
    finally:
        client.close(deadline=time.monotonic() + 1)
    assert proc.poll() is not None
    assert all(stream.closed for stream in (proc.stdin, proc.stdout, proc.stderr))


def test_stderr_fragmented_utf8_flushes_invalid_suffix():
    class FragmentStream(io.BytesIO):
        def __init__(self):
            super().__init__()
            self.chunks = iter([bytes([0xc3]), bytes([0xa9, 0xf0, 0x9f]), bytes([0x99, 0x82, 0xc3]), b""])

        def read(self, size):
            return next(self.chunks)

    proc = FakeProcess([])
    proc.stderr = FragmentStream()
    client = tui_rpc.TuiRpcClient(proc)
    assert client.stderr_tail == "é🙂�"
    assert client.stderr_tail == "é🙂�"


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
