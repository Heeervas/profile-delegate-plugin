"""Fail-closed installed test gate; never supplies or mocks runtime dependencies."""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import sys


def check_runtime(home: Path) -> dict:
    interpreter = home / ".venv/bin/python"
    if not interpreter.is_file():
        raise RuntimeError("installed integration requires a runtime interpreter")
    # Compare lexical venv paths, not resolved symlinks to a shared base Python.
    if Path(os.path.abspath(sys.executable)) != Path(os.path.abspath(interpreter)):
        raise RuntimeError("pytest must run with PROFILE_DELEGATE_TEST_RUNTIME/.venv/bin/python")
    if sys.version_info[:2] != (3, 14):
        raise RuntimeError("installed Hermes integration requires Python 3.14")
    if Path(sys.prefix).resolve() != (home / ".venv").resolve():
        raise RuntimeError("native pytest requires selected runtime venv prefix")
    modules = (
        "pytest", "yaml", "ruamel.yaml", "hermes_cli.config", "tools.approval",
        "hermes_state", "agent.display", "tui_gateway.contracts.prompt_voice",
        "pydantic_core",
    )
    imported = {name: importlib.import_module(name) for name in modules}
    for name in ("hermes_cli.config", "tools.approval", "hermes_state", "agent.display",
                 "tui_gateway.contracts.prompt_voice"):
        source = imported[name].__file__
        if source is None or not Path(source).resolve().is_relative_to(home.resolve()):
            raise RuntimeError(f"{name} did not load from selected runtime")
    for name in ("pytest", "yaml", "ruamel.yaml", "pydantic_core"):
        source = imported[name].__file__
        if source is None or not Path(source).resolve().is_relative_to((home / ".venv").resolve()):
            raise RuntimeError(f"{name} did not load from selected runtime venv closure")
    assert callable(imported["hermes_state"].SessionDB)
    # Exercise real Pydantic validation (including its compiled extension).
    params = imported["tui_gateway.contracts.prompt_voice"].PromptSubmitParams.model_validate(
        {"session_id": "prerequisite", "text": "harmless"}
    )
    assert params.text == "harmless"
    return {"interpreter": sys.executable, "version": sys.version, "modules": {
        name: module.__file__ for name, module in imported.items()
    }}


if __name__ == "__main__":
    print(json.dumps(check_runtime(Path(os.environ.get("PROFILE_DELEGATE_TEST_RUNTIME", "/opt/hermes"))), indent=2))
