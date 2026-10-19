"""TUI runner lifecycle tests; scenarios moved unchanged from test_tui_rpc."""
from __future__ import annotations
import json
import os
import signal
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import pytest
import tui_rpc
import tui_runner
import core
from test_tui_rpc import _execute_with_control, runner_run, runner_slot, runner_complete, RecordingJournal, CompleteClient

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


def test_runner_exposes_separate_bounded_startup_and_agent_init_timeouts(monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_GATEWAY_STARTUP_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("PROFILE_DELEGATE_AGENT_INIT_TIMEOUT_SECONDS", "34")
    assert tui_runner._stage_timeout("PROFILE_DELEGATE_GATEWAY_STARTUP_TIMEOUT_SECONDS", 30) == 12.0
    assert tui_runner._stage_timeout("PROFILE_DELEGATE_AGENT_INIT_TIMEOUT_SECONDS", 60) == 34.0
    monkeypatch.setenv("PROFILE_DELEGATE_AGENT_INIT_TIMEOUT_SECONDS", "99999")
    assert tui_runner._stage_timeout("PROFILE_DELEGATE_AGENT_INIT_TIMEOUT_SECONDS", 60) == 600.0


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
