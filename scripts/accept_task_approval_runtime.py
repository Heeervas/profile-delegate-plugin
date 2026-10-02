#!/usr/bin/env python3
"""Opt-in installed-runtime acceptance. No execution on import or without consent.

The ONLY simulated component is an HTTP OpenAI-compatible scripted provider.
Public plugin handlers, launch, native guards, tools, sessions and writes are real.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import shlex
import subprocess
import sys
import threading
import time
from typing import cast
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = Path(__file__).resolve().parents[1]
MARKER = "RUNTIME_ACCEPTANCE_ACTION="
OMIT = "__omitted__"


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")
    path.chmod(0o600)


def load_plugin():
    sys.path.insert(0, "/opt/hermes")
    spec = importlib.util.spec_from_file_location(
        "acceptance_profile_delegate", REPO / "__init__.py",
        submodule_search_locations=[str(REPO)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def driver(payload_path):
    """Separate real caller process; receives already isolated operator fixture env."""
    plugin = load_plugin()
    payload = json.loads(Path(payload_path).read_text())
    from hermes_state import SessionDB
    db = SessionDB()  # native schema, disposable caller home only
    db.ensure_session("runtime-acceptance-caller", source="cli")
    db.close()
    result = json.loads(plugin._handler(payload))
    if payload.get("background") and result.get("task_id"):
        deadline = time.monotonic() + payload["timeout_seconds"] + 30
        while time.monotonic() < deadline:
            observed = json.loads(plugin._status_handler({
                "task_id": result["task_id"], "tail_chars": 0,
            }))
            if observed.get("status") not in {"running", "queued", "starting"}:
                result = observed
                break
            time.sleep(0.25)
        else:
            result = {"status": "failed", "error_code": "harness_status_deadline",
                      "task_id": result["task_id"], "initial": result}
        from tools.async_delegation import get_durable_delegation
        ledger_deadline = time.monotonic() + 10
        ledger = None
        while time.monotonic() < ledger_deadline:
            ledger = get_durable_delegation(result["task_id"])
            if ledger and ledger.get("result"):
                break
            time.sleep(0.25)
        dump(Path(payload_path).with_suffix(".notification.json"), ledger)
    dump(Path(payload_path).with_suffix(".response.json"), result)
    return 0


class ScriptedProvider(ThreadingHTTPServer):
    """Deterministic MODEL fixture, not a replacement tool executor or guard.

    One tool call per prompt. After its actual tool response, stop; never recover
    from denial. Only private request bodies (no HTTP headers) are recorded.
    """
    def __init__(self, root):
        super().__init__(("127.0.0.1", 0), ProviderHandler)
        self.root = root
        self.lock = threading.Lock()
        self.receipts = []


class ProviderHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self.send_json({"object": "list", "data": [
            {"id": "approval-scripted", "object": "model", "owned_by": "fixture"},
        ]})

    def send_json(self, value, code=200):
        data = json.dumps(value).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            messages = body.get("messages", [])
            index, action = None, None
            for i, message in enumerate(messages):
                if message.get("role") != "user":
                    continue
                content = message.get("content", "")
                if isinstance(content, list):
                    content = "\n".join(x.get("text", "") for x in content if isinstance(x, dict))
                # Installed CLI sends the plugin prompt as an @file reference.
                # Resolve only this harness's bounded run prompt, never arbitrary files.
                if isinstance(content, str) and content.startswith("@file:"):
                    prompt = Path(content[len("@file:"):]).resolve()
                    runs = (cast(ScriptedProvider, self.server).root / "runs").resolve()
                    if not prompt.is_relative_to(runs) or prompt.name != "prompt.txt" or prompt.stat().st_size > 1_000_000:
                        raise ValueError("fixture prompt reference outside bounded run prompts")
                    content = prompt.read_text()
                for line in str(content).splitlines():
                    if line.startswith(MARKER):
                        index, action = i, json.loads(line[len(MARKER):])
            if action is None or index is None:
                raise ValueError("missing explicit fixture action; no tools issued")
            actual = [m for m in messages[index + 1:] if m.get("role") == "tool"]
            definitions = [x.get("function", {}).get("name") for x in body.get("tools", [])]
            if not actual:
                if action["name"] not in definitions:
                    raise ValueError("required real tool absent from installed runtime schema")
                message = {"role": "assistant", "content": None, "tool_calls": [{
                    "id": "acceptance_call_1", "type": "function",
                    "function": {"name": action["name"],
                                 "arguments": json.dumps(action["arguments"])},
                }]}
            else:
                # Echo ACTUAL tool result, no invented allow/refuse or FS claim.
                message = {"role": "assistant", "content": json.dumps({
                    "status": "ok", "summary": "Scripted provider stopped after actual tool response",
                    "artifacts": [], "errors": [], "next_steps": [],
                    "actual_tool_results": actual,
                })}
            server = cast(ScriptedProvider, self.server)
            with server.lock:
                server.receipts.append({"action": action, "actual": actual,
                                             "tool_definitions": definitions})
                dump(server.root / "provider-receipts.json", server.receipts)
            if body.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                delta = {k: v for k, v in message.items() if k != "tool_calls"}
                if "tool_calls" in message:
                    call = cast(dict, message["tool_calls"][0])
                    delta["tool_calls"] = [{"index": 0, **call}]
                for d, finish in ((delta, None), ({}, "tool_calls" if not actual else "stop")):
                    chunk = {"id": "acceptance-completion", "object": "chat.completion.chunk",
                             "created": 1, "model": "approval-scripted",
                             "choices": [{"index": 0, "delta": d, "finish_reason": finish}]}
                    self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            else:
                self.send_json({"id": "acceptance-completion", "object": "chat.completion",
                                "created": 1, "model": "approval-scripted",
                                "choices": [{"index": 0, "message": message,
                                             "finish_reason": "tool_calls" if not actual else "stop"}]})
        except Exception as exc:
            self.send_json({"error": {"message": str(exc), "type": "fixture_protocol_error"}}, 400)


def task(action):
    return ("Authorized isolated runtime acceptance. Execute exactly the single supplied tool call. "
            "After ANY refusal stop without retry, rephrase, alternate tool or workaround. "
            "Report its actual result; do not claim filesystem effects.\n"
            + MARKER + json.dumps(action))


def command(path):
    # Native script-execution flag detector sees python3 -c. No shell chains,
    # external destinations, deletion, or broad pattern-key grants.
    # Native exact-command grants reject reinterpreted shell-control chars,
    # including Python parentheses/semicolons inside -c. Import a private,
    # harness-owned marker module instead; keep the flagged command simple.
    module = "acceptance_" + path.stem.replace("-", "_")
    return "python3 -c " + shlex.quote("import " + module)


def terminal_action(path):
    module = "acceptance_" + path.stem.replace("-", "_")
    (path.parent / (module + ".py")).write_text(
        f"from pathlib import Path\nPath({str(path)!r}).write_text('runtime-acceptance\\n')\n"
    )
    return {"name": "terminal", "arguments": {"command": command(path), "timeout": 30}}


class Harness:
    def __init__(self, args, root, server):
        self.args, self.root, self.server = args, root, server
        self.home = root / "homes"
        self.target = self.home / "profiles" / "accept-target"
        self.grandchild = self.home / "profiles" / "accept-grandchild"
        self.caller = self.home / "profiles" / "accept-caller"
        self.strict = self.home / "profiles" / "accept-strict"
        self.unauthorized = self.home / "profiles" / "accept-unauthorized"
        self.rows = []
        self.serial = 0
        self.paths = {k: root / "effects" / (k + ".txt")
                      for k in ("fresh", "target-grant", "caller-grant", "target-deny", "ancestor-deny")}
        self.paths["fresh"].parent.mkdir()
        self.setup()

    def setup(self):
        import yaml
        base_url = f"http://127.0.0.1:{self.server.server_port}/v1"
        dump(self.home / "config.yaml", {})  # JSON is valid YAML; root identity
        for home in (self.target, self.grandchild, self.caller, self.strict, self.unauthorized):
            home.mkdir(parents=True)
            config = {
                "model": {"default": "approval-scripted", "provider": "custom",
                          "base_url": base_url, "api_key": "no-key-required",
                          "api_mode": "chat_completions", "context_length": 64000},
                "tools": {"tool_search": {"enabled": "off"}},
                "agent": {"max_turns": 5}, "compression": {"enabled": False},
                "memory": {"memory_enabled": False, "user_profile_enabled": False},
                "terminal": {"backend": "local", "cwd": str(self.root / "effects")},
                "platform_toolsets": {"cli": ["terminal", "delegation"],
                                      "profile-delegate": ["terminal", "delegation"]},
                "approvals": {"mode": "manual", "single_query_mode": "deny",
                              "unattended_mode": "deny", "deny": []},
                "command_allowlist": [],
                "plugins": {"enabled": ["profile-delegate"], "entries": {"profile-delegate": {
                    "allowed_profiles": ["accept-target", "accept-grandchild"],
                    "allowed_workdirs": [str(self.root)], "allowed_toolsets": ["terminal", "delegation"],
                    "allow_child_approval_override": home != self.unauthorized,
                    "child_approval_mode": "profile", "max_depth": 3,
                    "max_concurrent": 4, "max_transient_resumes": 0,
                }}},
            }
            if home in (self.caller, self.strict, self.unauthorized):
                config["command_allowlist"] = [command(self.paths["caller-grant"])]
                config["approvals"]["deny"] = ["*ancestor-deny.txt*", "*acceptance_ancestor_deny*"]
            else:
                config["command_allowlist"] = [command(self.paths["target-grant"])]
                config["approvals"]["deny"] = ["*target-deny.txt*", "*acceptance_target_deny*"]
            if home == self.caller:
                config["approvals"].update(single_query_mode="approve", unattended_mode="approve")
            (home / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
            (home / "config.yaml").chmod(0o600)
            (home / "plugins").mkdir()
            (home / "plugins" / "profile-delegate").symlink_to(REPO, target_is_directory=True)
            (home / "SOUL.md").write_text("Disposable deterministic runtime acceptance profile.\n")
        self.target_digest = hashlib.sha256((self.target / "config.yaml").read_bytes()).hexdigest()
        self.env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8",
            "HOME": str(self.root / "os-home"), "TMPDIR": str(self.root / "tmp"),
            "PYTHONPATH": "/opt/hermes", "NO_PROXY": "127.0.0.1,localhost",
            "PROFILE_DELEGATE_HERMES_BIN": self.args.hermes_bin,
            "PROFILE_DELEGATE_RUNS_ROOT": str(self.root / "runs"),
            "PROFILE_DELEGATE_LOCKS_ROOT": str(self.root / "locks"),
            "HERMES_SESSION_ID": "runtime-acceptance-caller",
            "HERMES_SESSION_KEY": "runtime-acceptance-local",
            "HERMES_SESSION_SOURCE": "cli",
        }
        for directory in (self.root / "os-home", self.root / "tmp"):
            directory.mkdir()

    def invoke(self, label, payload, caller=None):
        self.serial += 1
        payload_path = self.root / "calls" / f"{self.serial:03d}-{label}.json"
        dump(payload_path, payload)
        env = {**self.env, "HERMES_HOME": str(caller or self.caller)}
        # No inherited credentials, flags, current approval envelope or proxies.
        with payload_path.with_suffix(".driver.log").open("w") as log:
            completed = subprocess.run(
                [self.args.python, str(Path(__file__).resolve()), "--driver", str(payload_path)],
                env=env, cwd=self.root / "effects", stdout=log, stderr=subprocess.STDOUT,
                timeout=self.args.timeout + 90, check=False,
            )
        if completed.returncode:
            raise RuntimeError(f"driver exit {completed.returncode}: {payload_path.with_suffix('.driver.log')}")
        response = json.loads(payload_path.with_suffix(".response.json").read_text())
        return payload_path, response

    def payload(self, label, action, mode=OMIT, transport="cli", **extra):
        payload = {"profile": "accept-target", "session_title": label[:50],
                   "task": task(action), "workdir": str(self.root / "effects"),
                   "output_mode": "json", "timeout_seconds": self.args.timeout,
                   "toolsets": ["terminal", "delegation"],
                   "duplicate_policy": "new", "background": transport == "tui",
                   "transport_mode": "interactive" if transport == "tui" else "simple",
                   "notify_on_complete": transport == "tui", **extra}
        if mode != OMIT:
            payload["child_approval_mode"] = mode
        return payload

    def operation(self, label, mode, kind, allowed, transport, caller=None, **extra):
        path = self.paths[kind]
        if path.exists():
            path.unlink()  # only harness-owned marker, before a distinct task
        action = terminal_action(path)
        before = len(self.server.receipts)
        payload_path, response = self.invoke(
            label, self.payload(label, action, mode, transport, **extra), caller,
        )
        new = self.server.receipts[before:]
        matching = [x for x in new if x["action"] == action]
        actual = [m for x in matching for m in x["actual"]]
        assert actual, f"no actual terminal tool response: {payload_path}"
        # Exactly one tool attempt; subsequent provider reply must stop.
        assert len([x for x in matching if not x["actual"]]) == 1, "retry/alternate attempt"
        assert path.exists() == allowed, f"filesystem mismatch: {label} expected {allowed}"
        text = json.dumps(actual)
        if allowed:
            assert path.read_text() == "runtime-acceptance\n"
            assert 'BLOCKED' not in text, f"allowed effect with contradictory tool result: {label}"
        else:
            assert any(word in text.lower() for word in ("blocked", "denied", "approval_required", "policy_denied")), text
        run_id = response.get("task_id")
        assert run_id, f"missing public run: {payload_path}"
        run = self.root / "runs" / run_id
        request = json.loads((run / "request.json").read_text())
        status = json.loads((run / "status.json").read_text())
        events = [json.loads(line) for line in (run / "approval_events.jsonl").read_text().splitlines()]
        expected_mode = ("deny" if extra.get("session_mode") == "resume" and mode == OMIT
                         else "profile" if mode == OMIT
                         else "yolo" if mode == "approve_yolo" else mode)
        assert request["native_approval"]["effective"] == expected_mode
        assert any(e.get("outcome") == ("allowed" if allowed else "policy_denied") or
                   (not allowed and e.get("outcome") == "approval_required") for e in events), events
        assert status.get("transport") == ("tui_stdio" if transport == "tui" else "cli"), status
        assert status.get("exit_code") == 0, f"runtime did not complete: {run}"
        if transport == "tui":
            ledger = json.loads(payload_path.with_suffix(".notification.json").read_text())
            assert ledger and ledger.get("result"), "local notification completion absent"
        assert self.target_digest == hashlib.sha256((self.target / "config.yaml").read_bytes()).hexdigest(), "fixed target config mutated"
        self.rows.append({"case": label, "transport": transport, "expected_effect": allowed,
                          "observed_effect": path.exists(), "request": str(payload_path),
                          "run_dir": str(run), "native_approval": request["native_approval"],
                          "actual_tool_results": actual, "approval_events": events,
                          "notification_status": status.get("notification_status"), "verdict": "pass"})
        self.save()
        return status, request

    def rejection(self, label, mode, code, caller=None, **extra):
        before = set((self.root / "runs").glob("*"))
        payload_path, response = self.invoke(label, self.payload(
            label, terminal_action(self.paths["fresh"]), mode, **extra), caller)
        assert response.get("success") is False and response.get("error_code") == code, response
        assert set((self.root / "runs").glob("*")) == before, "rejected selection allocated a run"
        self.rows.append({"case": label, "request": str(payload_path), "response": response,
                          "no_run_created": True, "verdict": "pass"})
        self.save()

    def nested(self, parent_mode, child_mode, expected_effect=None):
        label = f"nested-{parent_mode}-{child_mode}"
        path = self.root / "effects" / (label + ".txt")
        child = self.payload(label, terminal_action(path), child_mode)
        child["profile"] = "accept-grandchild"
        action = {"name": "profile_delegate", "arguments": child}
        before = len(self.server.receipts)
        payload_path, response = self.invoke(label, self.payload(label, action, parent_mode))
        actual = [m for x in self.server.receipts[before:] if x["action"] == action for m in x["actual"]]
        assert actual, f"real nested public tool was not called: {payload_path}"
        if expected_effect is None:
            assert not path.exists()
            assert "approval_policy_error" in json.dumps(actual), actual
        else:
            child_actual = [m for x in self.server.receipts[before:]
                            if x["action"] == terminal_action(path) for m in x["actual"]]
            assert child_actual, "no real nested child terminal response"
            assert path.exists() == expected_effect
            if expected_effect:
                assert path.read_text() == "runtime-acceptance\n"
            else:
                assert "blocked" in json.dumps(child_actual).lower()
        self.rows.append({"case": label, "request": str(payload_path), "response": response,
                          "actual_tool_results": actual, "observed_effect": path.exists(), "verdict": "pass"})
        self.save()

    def save(self):
        dump(self.root / "matrix.json", {"provider": "deterministic scripted MODEL HTTP fixture",
                                        "runtime": "installed Hermes; real handlers/launch/guards/tools",
                                        "target_config_sha256": self.target_digest, "cases": self.rows,
                                        "complete": False})

    def run(self):
        # Smallest boundary FIRST. If this fails, no full matrix or alternate operation.
        self.operation("probe-cli-deny-fresh", "deny", "fresh", False, "cli")
        if self.args.phase == "probe":
            return
        for transport in ("cli", "tui"):
            for mode in ("deny", "profile", "inherit", "yolo"):
                self.operation(f"{transport}-{mode}-fresh", mode, "fresh", mode in {"inherit", "yolo"}, transport)
                self.operation(f"{transport}-{mode}-target-grant", mode, "target-grant", True, transport)
                self.operation(f"{transport}-{mode}-caller-grant", mode, "caller-grant", mode in {"inherit", "yolo"}, transport)
                self.operation(f"{transport}-{mode}-target-deny", mode, "target-deny", False, transport)
            # Separate caller with deny posture proves inherited permanent grants,
            # independent of caller's contrasting approve posture in primary matrix.
            self.operation(f"{transport}-strict-inherit-caller-grant", "inherit", "caller-grant", True, transport, self.strict)
            self.operation(f"{transport}-strict-inherit-target-grant", "inherit", "target-grant", False, transport, self.strict)
            self.operation(f"{transport}-inherit-ancestor-deny", "inherit", "ancestor-deny", False, transport)
            self.operation(f"{transport}-alias", "approve_yolo", "fresh", True, transport)
            self.operation(f"{transport}-omission", OMIT, "fresh", False, transport)
        for i, bad in enumerate(("", "bogus", [], {}, False, 1)):
            self.rejection(f"invalid-{i}", bad, "validation_error")
        for mode in ("profile", "inherit", "yolo"):
            self.rejection(f"unauthorized-{mode}", mode, "execution_overrides_not_allowed", self.unauthorized)
        self.operation("unauthorized-deny-narrowing", "deny", "fresh", False, "cli", self.unauthorized)
        for transport in ("cli", "tui"):
            status, original = self.operation(f"{transport}-resume-seed", "deny", "fresh", False, transport)
            sid = status.get("child_session_id") or status.get("session_id")
            assert sid, "runtime session identity absent; frozen resume cannot be verified"
            self.rejection(f"{transport}-resume-reselect", "yolo", "approval_policy_error", session_mode="resume", session_id=sid)
            resumed_status, resumed = self.operation(
                f"{transport}-resume-frozen", OMIT, "fresh", False, transport, session_mode="resume", session_id=sid,
            )
            assert resumed["native_approval"] == original["native_approval"], "resume refreshed authority"
            assert (resumed_status.get("child_session_id") or resumed_status.get("session_id")) == sid, "resume changed session identity"
        self.nested("deny", "yolo")
        self.nested("yolo", "profile")
        self.nested("yolo", "inherit", True)
        self.nested("yolo", "deny", False)
        self.nested("deny", "deny", False)
        report = json.loads((self.root / "matrix.json").read_text())
        report["complete"] = True
        dump(self.root / "matrix.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorize-isolated-runtime", action="store_true")
    parser.add_argument("--phase", choices=["probe", "matrix"], default="probe")
    parser.add_argument("--hermes-bin", default="/opt/hermes/bin/hermes")
    parser.add_argument("--python", default="/opt/hermes/.venv/bin/python")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--driver", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if os.environ.get("PROFILE_DELEGATE_APPROVAL_REQUEST") or os.environ.get("PROFILE_DELEGATE_PARENT_TASK_ID"):
        parser.error("frozen delegated authority detected; do not clear it or run this harness here")
    if args.driver:
        # Private subprocess entry; require the operator-created fixture config.
        home = Path(os.environ.get("HERMES_HOME", "/nonexistent")).resolve()
        artifacts = (REPO / ".artifacts").resolve()
        if not home.is_relative_to(artifacts) or not (home / "config.yaml").is_file():
            parser.error("driver requires disposable repository .artifacts home")
        return driver(args.driver)
    if not args.authorize_isolated_runtime:
        parser.error("opt-in only: controller must pass --authorize-isolated-runtime")
    for value in (args.hermes_bin, args.python):
        path = Path(value).resolve()
        if not path.is_relative_to(Path("/opt/hermes")) or not path.is_file():
            parser.error("must use installed /opt/hermes runtime, never a test double")
    os.umask(0o077)
    import tempfile
    artifacts = REPO / ".artifacts"
    artifacts.mkdir(exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="task-approval-runtime-", dir=artifacts))
    server = ScriptedProvider(root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(json.dumps({"artifact_root": str(root), "phase": args.phase}), flush=True)
    try:
        harness = Harness(args, root, server)
        harness.run()
        dump(root / "receipt.json", {"status": "ok", "phase": args.phase,
                                    "matrix_complete": args.phase == "matrix",
                                    "case_count": len(harness.rows)})
        return 0
    except Exception as exc:
        dump(root / "receipt.json", {"status": "failed", "phase": args.phase,
                                    "matrix_complete": False, "error": str(exc)})
        print(json.dumps({"status": "failed", "evidence": str(root / "receipt.json")}), flush=True)
        return 1
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
