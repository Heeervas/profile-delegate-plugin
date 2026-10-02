#!/usr/bin/env python3
"""Bounded installed TUI controls / CLI recovery smoke.

ONLY the MODEL HTTP provider is scripted. No mocked handlers, launch, sessions,
transport, control or process cleanup. Operator opt-in; never delegated ancestry.
Reuses isolated setup from accept_task_approval_runtime; does not run its matrix.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from typing import cast
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from accept_task_approval_runtime import Harness, REPO, dump, load_plugin

TAG = "AUDIT_SMOKE="
FOLLOWUP = "AUDIT_FOLLOWUP_CORRELATED"


def wait_for(predicate, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise RuntimeError("smoke observation deadline")


class SmokeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, root):
        super().__init__(("127.0.0.1", 0), Provider)
        self.root = root
        self.lock = threading.Lock()
        self.requests = []


class Provider(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self.reply({"data": [{"id": "approval-scripted", "object": "model"}]})

    def reply(self, body, code=200):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        server = cast(SmokeServer, self.server)
        root = server.root
        messages = body.get("messages", [])
        texts = []
        for message in messages:
            content = str(message.get("content", ""))
            if content.startswith("@file:"):
                path = Path(content[6:]).resolve()
                if not path.is_relative_to((root / "runs").resolve()) or path.stat().st_size > 1_000_000:
                    self.reply({"error": {"message": "unbounded prompt reference"}}, 400)
                    return
                content = path.read_text()
            texts.append(content)
        combined = "\n".join(texts)
        case = next((line[len(TAG):] for text in texts for line in text.splitlines() if line.startswith(TAG)), None)
        if case is None:
            self.reply({"error": {"message": "missing smoke tag"}}, 400)
            return
        request_paths = list((root / "runs").glob("*/request.json"))
        snapshots = [json.loads(path.read_text()) for path in request_paths]
        envelope = next(record["native_approval"] for record in snapshots if record.get("session_title") == case)
        with server.lock:
            server.requests.append({"case": case, "messages": messages, "resolved_text": combined,
                                    "native_approval": envelope})
            dump(root / "provider-requests.json", server.requests)
        (root / (case + ".active")).touch()
        recovery = "previous delegated run ended because of a transient" in combined
        if case.startswith("recovery-") and not recovery:
            # Exhaust bounded native provider retries. Only actual plugin recovery
            # unlocks success: ordinary resume cannot satisfy this condition.
            # Do not forge a legacy "API call failed after N retries:" diagnostic
            # in the provider body. Installed quiet CLI copy may not match the
            # plugin classifier; that is an evidence gap, never a synthetic PASS.
            self.reply({"error": {"message": "HTTP 503: Service Unavailable upstream temporarily unavailable",
                                  "type": "server_error"}}, 503)
            return
        followup = FOLLOWUP in combined
        if case in {"steer", "cancel"} and not followup:
            wait_for(lambda: (root / (case + ".release")).exists(), 60)
        text = ("# Installed smoke\n" if case != "recovery-text" else "Installed smoke\n")
        text += (FOLLOWUP if followup else case) + "\nPROFILE_DELEGATE_RESULT: ok"
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for delta, finish in (({"role": "assistant", "content": text}, None), ({}, "stop")):
                chunk = {"id": "audit-smoke", "object": "chat.completion.chunk", "created": 1,
                         "model": "approval-scripted", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        else:
            self.reply({"id": "audit-smoke", "object": "chat.completion", "created": 1,
                        "model": "approval-scripted", "choices": [{"index": 0, "message": {
                            "role": "assistant", "content": text}, "finish_reason": "stop"}]})


def driver(payload_path):
    plugin = load_plugin()
    from hermes_state import SessionDB
    db = SessionDB()
    db.ensure_session("runtime-acceptance-caller", source="cli")
    db.close()
    path = Path(payload_path)
    payload = json.loads(path.read_text())
    case = payload["session_title"]
    root = Path(os.environ["PROFILE_DELEGATE_RUNS_ROOT"]).parent
    response = json.loads(plugin._handler(payload))
    dump(path.with_suffix(".initial.json"), response)
    run = root / "runs" / response["task_id"]
    if payload["background"]:
        wait_for(lambda: (root / (case + ".active")).exists(), 60)
        status = json.loads((run / "status.json").read_text())
        pid = status["transport_pid"]
        ack = None
        if case in {"steer", "cancel"}:
            handler = plugin._steer_handler if case == "steer" else plugin._cancel_handler
            control = json.loads(handler({"task_id": response["task_id"], "text": FOLLOWUP}))
            dump(path.with_suffix(".control.json"), control)
            command_id = control.get("command_id")
            assert command_id, control
            ack_dir = run / "control" / "acks"
            ack = wait_for(lambda: next((json.loads(p.read_text()) for p in ack_dir.glob("*.json")
                                        if command_id in p.name), None), 10)
            assert ack["state"] == "accepted", ack
            dump(path.with_suffix(".ack.json"), ack)
            (root / (case + ".release")).touch()
        response = wait_for(lambda: terminal_status(plugin, response["task_id"]), 90)
        status = json.loads((run / "status.json").read_text())
        assert status["transport_alive"] is False
        assert not Path(f"/proc/{pid}").exists(), "owned transport not reaped"
        # No instrumentation replaces close: runner's terminal status plus OS
        # PID absence prove reaping/no open child pipes, not Python fd.closed.
        dump(path.with_suffix(".cleanup.json"), {"pid": pid, "proc_absent": True,
             "transport_alive": status["transport_alive"], "fd_closed_in_parent": "not instrumented"})
        if case == "cancel":
            assert response["status"] == "cancelled", response
        else:
            assert response["success"] is True, response
            if case == "steer":
                assert FOLLOWUP in json.dumps(response), "ACK without correlated final uptake"
                events = [json.loads(line) for line in (run / "events.jsonl").read_text().splitlines()]
                starts = [e for e in events if e.get("type") == "message.start"]
                completes = [e for e in events if e.get("type") == "message.complete"]
                assert len(starts) >= 2 and len(completes) >= 2, "missing observed follow-up lifecycle"
                assert all(e["task_id"] == response["task_id"] for e in starts + completes)
                ui_session_id = status.get("ui_child_session_id")
                assert ui_session_id, "missing authoritative UI identity"
                # Journal ingestion only projects events matching runner UI identity.
                dump(path.with_suffix(".followup.json"), {"ack": ack, "starts": starts, "completes": completes,
                     "ui_child_session_id": ui_session_id, "uptake": FOLLOWUP,
                     "child_session_id": response.get("child_session_id")})
    else:
        assert response["success"] is True, response
        status = json.loads((run / "status.json").read_text())
        history = response.get("result", {}).get("recovery_history", [])
        assert len(history) == 2 and history[0]["transient_reason"], status
        assert history[0]["session_id"] == history[1]["session_id"] == response["child_session_id"]
        assert "PROFILE_DELEGATE_RESULT: ok" in (run / "stdout.txt").read_text()
        request = json.loads((run / "request.json").read_text())
        assert request["resolved_output_mode"] == case.removeprefix("recovery-")
        assert request["native_approval"]["effective"] == "deny"
        provider_rows = json.loads((root / "provider-requests.json").read_text())
        matching = [row for row in provider_rows if row["case"] == case]
        assert matching and all(row["native_approval"] == request["native_approval"] for row in matching)
        assert any("previous delegated run ended because of a transient" in row["resolved_text"] for row in matching)
        # Native child's envelope artifacts are the same immutable run snapshot
        # for both real argv; request history records exact resume session.
        dump(path.with_suffix(".recovery.json"), {"history": history, "native_approval": request["native_approval"],
             "recovery_prompt": (run / "recovery_prompt_2.txt").read_text()})
    dump(path.with_suffix(".response.json"), response)
    return 0


def terminal_status(plugin, task_id):
    status = json.loads(plugin._status_handler({"task_id": task_id, "tail_chars": 4000}))
    return status if status.get("status") not in {"running", "queued", "starting", "cancelling"} else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorize-isolated-runtime", action="store_true")
    parser.add_argument("--cases", nargs="+", choices=(
        "completion", "steer", "cancel", "recovery-markdown", "recovery-text",
    ), default=("completion", "steer", "cancel", "recovery-markdown", "recovery-text"))
    parser.add_argument("--driver", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if os.environ.get("PROFILE_DELEGATE_APPROVAL_REQUEST") or os.environ.get("PROFILE_DELEGATE_PARENT_TASK_ID"):
        parser.error("frozen delegated authority detected; do not clear or bypass it")
    if args.driver:
        home = Path(os.environ.get("HERMES_HOME", "/nonexistent")).resolve()
        if not home.is_relative_to((REPO / ".artifacts").resolve()):
            parser.error("private driver requires isolated home")
        return driver(args.driver)
    if not args.authorize_isolated_runtime:
        parser.error("operator opt-in required")
    os.umask(0o077)
    root = Path(tempfile.mkdtemp(prefix="audit-runtime-", dir=REPO / ".artifacts"))
    server = SmokeServer(root)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(root, flush=True)
    try:
        settings = argparse.Namespace(hermes_bin="/opt/hermes/bin/hermes", python="/opt/hermes/.venv/bin/python", timeout=180)
        harness = Harness(settings, root, server)
        # Disposable fixture only. Does not mutate production profile/config.
        import yaml
        config_path = harness.caller / "config.yaml"
        config = yaml.safe_load(config_path.read_text())
        config["plugins"]["entries"]["profile-delegate"]["max_transient_resumes"] = 1
        config_path.write_text(yaml.safe_dump(config))
        # Native contract: agent_init.py defaults to 3 attempts + 5 delayed
        # auto-recovery cycles. That ladder exhausted the 180s outer deadline
        # before a failed turn/footer could reach the plugin. Configure only the
        # newly generated target home; keep real HTTP failure and total deadline.
        target_config_path = harness.target / "config.yaml"
        target_config = yaml.safe_load(target_config_path.read_text())
        target_config["agent"].update(api_max_retries=1, auto_recovery_cycles=0)
        target_config_path.write_text(yaml.safe_dump(target_config))
        rows = []
        for case in args.cases:
            background = not case.startswith("recovery-")
            payload = {"profile": "accept-target", "session_title": case,
                       "task": "Harmless deterministic installed smoke; no tools needed.\n" + TAG + case,
                       "workdir": str(root / "effects"), "output_mode": "text" if case == "recovery-text" else "markdown",
                       "timeout_seconds": 180, "toolsets": ["terminal"], "duplicate_policy": "new",
                       "background": background, "transport_mode": "interactive" if background else "simple",
                       "notify_on_complete": False, "child_approval_mode": "deny"}
            path = root / "calls" / (case + ".json")
            dump(path, payload)
            with path.with_suffix(".log").open("w") as log:
                completed = subprocess.run([settings.python, str(Path(__file__).resolve()), "--driver", str(path)],
                    cwd=REPO, env={**harness.env, "HERMES_HOME": str(harness.caller)},
                    stdout=log, stderr=subprocess.STDOUT, timeout=270, check=False)
            assert completed.returncode == 0, f"{case}: inspect {path.with_suffix('.log')}"
            rows.append({"case": case, "evidence": str(path.with_suffix(".response.json"))})
        dump(root / "receipt.json", {"status": "ok", "provider": "deterministic scripted MODEL HTTP fixture",
             "runtime": "installed Hermes real handlers/launch/session/control", "cases": rows})
        return 0
    except Exception as exc:
        dump(root / "receipt.json", {"status": "failed", "error": str(exc)})
        raise
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
