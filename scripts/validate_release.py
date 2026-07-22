#!/usr/bin/env python3
"""Validate Profile Delegate registration and release metadata. Usage: python scripts/validate_release.py; Example: .venv/bin/python scripts/validate_release.py"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class FakeContext:
    def __init__(self) -> None:
        self.tools: dict[str, dict] = {}
        self.commands: dict[str, dict] = {}

    def register_tool(self, **kwargs) -> None:
        self.tools[kwargs["name"]] = kwargs

    def register_cli_command(self, **kwargs) -> None:
        self.commands[kwargs["name"]] = kwargs


def load_plugin():
    spec = importlib.util.spec_from_file_location(
        "profile_delegate_release_smoke", ROOT / "__init__.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load plugin module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    manifest = yaml.safe_load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^Version: `([^`]+)`$", readme, re.MULTILINE)
    if not match:
        raise AssertionError("README version marker missing")
    version = str(manifest["version"])
    assert match.group(1) == version, "README/manifest version mismatch"
    assert f"## [{version}]" in changelog, "CHANGELOG release entry missing"

    plugin = load_plugin()
    ctx = FakeContext()
    plugin.register(ctx)
    expected = set(manifest.get("provides_tools") or [])
    assert set(ctx.tools) == expected, "registered tools differ from plugin.yaml"
    assert "profile-delegate" in ctx.commands, "spectator CLI command not registered"
    for name, entry in ctx.tools.items():
        schema = entry["schema"]
        assert schema.get("name") == name
        assert isinstance(schema.get("parameters"), dict)
        assert "input_schema" not in schema

    validation_error = json.loads(
        ctx.tools["profile_delegate"]["handler"](
            {"profile": "", "task": "smoke", "session_title": "release smoke"}
        )
    )
    assert validation_error["success"] is False
    assert validation_error["error_code"] == "validation_error"
    print(
        json.dumps(
            {
                "success": True,
                "version": version,
                "tools": sorted(ctx.tools),
                "cli_commands": sorted(ctx.commands),
                "handler_smoke": "validation_error_ok",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
