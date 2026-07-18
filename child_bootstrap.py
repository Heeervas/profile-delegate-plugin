#!/usr/bin/env python3
"""Launch a delegated Hermes child with plugin-owned approvals. Usage: child_bootstrap.py [options] -- hermes ..."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _event_writer(path: Path, policy: str) -> Callable[..., None]:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    def write(*, detector: str, outcome: str, reason: str, value: str = "") -> None:
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


def install_policy(mode: str, events_path: Path, blocked_tools: list[str]) -> None:
    """Install policy in this process before Hermes constructs the child agent."""
    if mode not in {"deny", "approve_yolo"}:
        raise ValueError(f"unsupported child approval mode: {mode}")
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
        if mode == "deny" and dangerous and not hardline:
            result = {
                "approved": False,
                "message": f"BLOCKED by profile-delegate deny policy: {dangerous_reason}",
                "pattern_key": pattern_key,
                "description": dangerous_reason,
                "outcome": "denied",
                "user_consent": False,
            }
        else:
            callback = approval_callback
            if mode == "deny":
                def immediate_deny(*_args, **_kwargs):
                    return "deny"

                callback = immediate_deny
            result = original_guard(
                command, env_type, approval_callback=callback,
                has_host_access=has_host_access,
            )
        if hardline or dangerous or not result.get("approved", False):
            write_event(
                detector="hardline" if hardline else (str(pattern_key or "command_guard")),
                outcome="allowed" if result.get("approved", False) else "denied",
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
        write_event(
            detector="execute_code",
            outcome="allowed" if result.get("approved", False) else "denied",
            reason=str(result.get("description") or result.get("message") or "execute_code_guard"),
            value=code,
        )
        return result

    approval.check_all_command_guards = terminal_guard
    approval.check_execute_code_guard = execute_guard
    # terminal_tool imported the implementation by value, so replace that alias too.
    terminal_tool._check_all_guards_impl = terminal_guard
    terminal_tool.set_approval_callback(lambda *_args, **_kwargs: "deny" if mode == "deny" else "once")

    blocked = {name for name in blocked_tools if name}
    if blocked:
        import model_tools

        original_definitions = model_tools.get_tool_definitions

        def filtered_definitions(*args, **kwargs):
            definitions = original_definitions(*args, **kwargs)
            filtered = [item for item in definitions if _tool_name(item) not in blocked]
            model_tools._last_resolved_tool_names = [
                _tool_name(item) for item in filtered if _tool_name(item)
            ]
            return filtered

        model_tools.get_tool_definitions = filtered_definitions
        # AIAgent resolves schemas through run_agent's imported alias. Patch
        # both aliases in case either module was imported before installation.
        try:
            run_agent_module = __import__("run_agent")
            run_agent_module.get_tool_definitions = filtered_definitions
        except ImportError:
            pass
        try:
            cli_module = __import__("cli")
            cli_module.get_tool_definitions = filtered_definitions
        except ImportError:
            pass
        write_event(
            detector="capability_filter",
            outcome="installed",
            reason="blocked_tools=" + ",".join(sorted(blocked)),
        )


def _parse_args(argv: list[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description="Profile Delegate child bootstrap")
    parser.add_argument("--approval-mode", required=True, choices=["deny", "approve_yolo"])
    parser.add_argument("--events-path", required=True)
    parser.add_argument("--blocked-tools", default="")
    args, command = parser.parse_known_args(argv)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("missing Hermes command after --")
    return args, command


def main(argv: list[str] | None = None) -> int:
    args, command = _parse_args(argv)
    try:
        install_policy(
            args.approval_mode,
            Path(args.events_path).expanduser().resolve(),
            [item for item in args.blocked_tools.split(",") if item],
        )
    except ModuleNotFoundError as exc:
        # Compatibility for test shims or non-Python Hermes executables. Real
        # Hermes installs provide tools/hermes_cli and therefore stay in-process.
        if exc.name not in {"tools", "hermes_cli"}:
            raise
        return subprocess.run(command, check=False).returncode
    # Stay in-process so monkeypatches remain active. The executable path is
    # retained for auditability but hermes_cli.main is the installed entrypoint.
    sys.argv = [command[0], *command[1:]]
    from hermes_cli.main import main as hermes_main

    result = hermes_main()
    return int(result) if isinstance(result, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
