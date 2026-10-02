#!/usr/bin/env python3
"""Launch a delegated Hermes child with plugin-owned approvals. Usage: child_bootstrap.py [options] -- hermes ..."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _event_writer(path: Path, policy: str) -> Callable[..., None]:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    def write(*, detector: str, outcome: str, reason: str, value: str = "",
              elapsed_ms: int | None = None) -> None:
        event: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "effective_policy": policy,
            "detector": detector[:100],
            "reason": reason[:500],
            "outcome": outcome[:50],
        }
        if value:
            event["sha256"] = hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()
            event["value_chars"] = len(value)
        if elapsed_ms is not None:
            event["elapsed_ms"] = max(0, min(elapsed_ms, 600_000))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    return write


def _tool_name(definition: Any) -> str:
    if not isinstance(definition, dict):
        return ""
    if isinstance(definition.get("function"), dict):
        return str(definition["function"].get("name") or "")
    return str(definition.get("name") or "")


def _decision(result: dict, mode: str) -> str:
    if result.get("approved", False):
        return "allowed"
    if mode == "deny" or result.get("user_deny") or result.get("hardline"):
        return "policy_denied"
    return "approval_required"


def _install_capability_filter(blocked_tools: list[str], write_event) -> None:
    blocked = {name for name in blocked_tools if name}
    if not blocked:
        return
    import model_tools
    original_definitions = model_tools.get_tool_definitions

    def filtered_definitions(*args, **kwargs):
        definitions = original_definitions(*args, **kwargs)
        filtered = [item for item in definitions if _tool_name(item) not in blocked]
        model_tools._last_resolved_tool_names = [_tool_name(item) for item in filtered if _tool_name(item)]
        return filtered

    model_tools.get_tool_definitions = filtered_definitions
    for module in ("run_agent", "cli"):
        try:
            __import__(module).get_tool_definitions = filtered_definitions
        except ImportError:
            pass
    write_event(detector="capability_filter", outcome="installed",
                reason="blocked_tools=" + ",".join(sorted(blocked)))


def install_policy(mode: str, events_path: Path, blocked_tools: list[str], envelope: dict | None = None) -> None:
    """Install policy in this process before Hermes constructs the child agent."""
    if mode not in {"deny", "approve_yolo", "yolo", "profile", "inherit"}:
        raise ValueError(f"unsupported child approval mode: {mode}")
    if envelope is not None:
        import native_approval
        native_approval.bind(envelope)
    elif mode in {"profile", "inherit", "yolo"}:
        raise ValueError("native approval mode requires frozen envelope")
    if envelope is not None and envelope["effective"] != ("yolo" if mode == "approve_yolo" else mode):
        raise ValueError("approval selector/envelope mismatch")
    write_event = _event_writer(events_path, mode)
    write_event(detector="bootstrap", outcome="installed", reason="plugin_owned_child_policy")

    from tools import approval
    from tools import terminal_tool

    original_guard = approval.check_all_command_guards
    original_execute_guard = approval.check_execute_code_guard

    def terminal_guard(command: str, env_type: str, approval_callback=None,
                       has_host_access: bool = False) -> dict[str, Any]:
        hardline, hardline_reason = approval.detect_hardline_command(command)
        dangerous, pattern_key, dangerous_reason = approval.detect_dangerous_command(command)
        callback = approval_callback
        if mode == "deny":
            def immediate_deny(*_args, **_kwargs):
                return "deny"

            callback = immediate_deny
        result = original_guard(
            command, env_type, approval_callback=callback,
            has_host_access=has_host_access,
        )
        decision = _decision(result, mode)
        if not result.get("approved", False):
            result["error_code"] = decision
        if hardline or dangerous or not result.get("approved", False):
            write_event(
                detector="hardline" if hardline else (str(pattern_key or "command_guard")),
                outcome=decision,
                reason=str(hardline_reason or dangerous_reason or result.get("message") or "guard_decision"),
                value=command,
            )
        return result

    def execute_guard(code: str, env_type: str, has_host_access: bool = False) -> dict[str, Any]:
        if mode == "deny" and env_type not in {"docker", "vercel_sandbox"}:
            result = {
                "approved": False,
                "message": "BLOCKED: execute_code is disabled by profile-delegate child approval policy.",
                "pattern_key": "execute_code",
                "description": "plugin-owned deterministic deny policy",
                "outcome": "blocked",
                "user_consent": False,
            }
        else:
            result = original_execute_guard(code, env_type, has_host_access=has_host_access)
        decision = "allowed" if result.get("approved", False) else ("policy_denied" if mode == "deny" else "approval_required")
        if not result.get("approved", False):
            result["error_code"] = decision
        write_event(
            detector="execute_code",
            outcome=decision,
            reason=str(result.get("description") or result.get("message") or "execute_code_guard"),
            value=code,
        )
        return result

    approval.check_all_command_guards = terminal_guard
    approval.check_execute_code_guard = execute_guard
    # terminal_tool imported the implementation by value, so replace that alias too.
    terminal_tool._check_all_guards_impl = terminal_guard
    terminal_tool.set_approval_callback(lambda *_args, **_kwargs: "deny" if mode == "deny" else "once")

    _install_capability_filter(blocked_tools, write_event)


def _parse_args(argv: list[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description="Profile Delegate child bootstrap")
    parser.add_argument("--approval-mode", required=True, choices=["deny", "approve_yolo", "profile", "inherit", "yolo"])
    parser.add_argument("--request-path")
    parser.add_argument("--test-shim", action="store_true")
    parser.add_argument("--events-path", required=True)
    parser.add_argument("--blocked-tools", default="")
    parser.add_argument("--tui-gateway", action="store_true")
    args, command = parser.parse_known_args(argv)
    if command and command[0] == "--":
        command = command[1:]
    if not command and not args.tui_gateway:
        parser.error("missing Hermes command after --")
    return args, command


def prepare_tui_runtime(stage_event: Callable[[str, str], None] | None = None) -> None:
    """Finish plugin registration before TUI starts concurrent discovery/build.

    The stdio gateway starts MCP discovery in one thread and lazily builds the
    first agent in another. Both paths can enter plugin discovery. A plugin
    register hook that imports ``run_agent`` while the build thread imports
    ``model_tools`` creates a plugin-lock/import-lock inversion and strands the
    submitted prompt until the 600-second agent-build timeout. Serial discovery
    here makes the registry stable before either TUI thread exists.
    """
    if stage_event:
        stage_event("discover_plugins", "enter")
    try:
        from hermes_cli.plugins import discover_plugins
        discover_plugins()
    finally:
        if stage_event:
            stage_event("discover_plugins", "exit")


def main(argv: list[str] | None = None) -> int:
    args, command = _parse_args(argv)
    # Non-Hermes commands are test/compatibility shims. Execute them directly;
    # importing the full Hermes tool graph would be both incorrect and slow.
    if command and Path(command[0]).resolve().name != "hermes" and not args.tui_gateway:
        if not args.test_shim:
            raise RuntimeError("non-Hermes executable requires explicit test shim")
        return subprocess.run(command, check=False).returncode
    os.environ["HERMES_SINGLE_QUERY_SESSION"] = "1"
    if args.request_path:
        os.environ["PROFILE_DELEGATE_APPROVAL_REQUEST"] = args.request_path
    origin = time.monotonic()
    write_stage_event = _event_writer(Path(args.events_path).expanduser().resolve(), args.approval_mode)

    def stage_event(stage: str, edge: str) -> None:
        # Fixed literals only: no environment, credential, plugin, or exception text.
        write_stage_event(
            detector="startup_stage", outcome=edge, reason=stage,
            elapsed_ms=int((time.monotonic() - origin) * 1000),
        )

    stage_event("bootstrap_policy_filter", "enter")
    try:
        install_policy(
            args.approval_mode,
            Path(args.events_path).expanduser().resolve(),
            [item for item in args.blocked_tools.split(",") if item],
            __import__("native_approval").read_request(Path(args.request_path)) if args.request_path else None,
        )
    except ModuleNotFoundError as exc:
        raise RuntimeError("native approval installation failed; delegated launch refused") from exc
    finally:
        stage_event("bootstrap_policy_filter", "exit")
    if args.tui_gateway:
        prepare_tui_runtime(stage_event)
        stage_event("native_entry_import", "enter")
        try:
            from tui_gateway.entry import main as tui_main
        finally:
            stage_event("native_entry_import", "exit")

        result = tui_main()
        return int(result) if isinstance(result, int) else 0
    # Stay in-process so monkeypatches remain active. The executable path is
    # retained for auditability but hermes_cli.main is the installed entrypoint.
    sys.argv = [command[0], *command[1:]]
    from hermes_cli.main import main as hermes_main

    result = hermes_main()
    return int(result) if isinstance(result, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
