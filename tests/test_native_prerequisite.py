"""Gate regressions: actual invoking interpreters, no fake runtime import closure."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.native_prerequisite import check_runtime


def test_missing_native_runtime_fails(tmp_path):
    with pytest.raises(RuntimeError, match="requires a runtime interpreter"):
        check_runtime(tmp_path)


def test_foreign_interpreter_fails_before_imports(tmp_path):
    interpreter = tmp_path / ".venv/bin/python"
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    with pytest.raises(RuntimeError, match="pytest must run with"):
        check_runtime(tmp_path)


@pytest.mark.integration
def test_native_prerequisite_actual_closure_and_foreign_interpreter(tmp_path):
    home = Path(os.environ.get("PROFILE_DELEGATE_TEST_RUNTIME", "/opt/hermes"))
    receipt = check_runtime(home)
    assert receipt["interpreter"] == sys.executable
    assert "pydantic_core" in receipt["modules"]
    # Fail closed on a genuine missing closure module; no substituted APIs.
    from scripts import native_prerequisite
    original_import = native_prerequisite.importlib.import_module
    with pytest.MonkeyPatch.context() as patch:
        def missing_contract(name):
            if name == "tui_gateway.contracts.prompt_voice":
                raise ModuleNotFoundError("deliberately unavailable native contracts")
            return original_import(name)
        patch.setattr(native_prerequisite.importlib, "import_module", missing_contract)
        with pytest.raises(ModuleNotFoundError, match="unavailable native contracts"):
            check_runtime(home)
    (tmp_path / "native-prerequisite.json").write_text(json.dumps(receipt, indent=2))
    portable = Path(__file__).parents[1] / ".venv/bin/python"
    foreign = str(portable) if portable.is_file() else getattr(sys, "_base_executable")
    completed = subprocess.run(
        [foreign, "scripts/native_prerequisite.py"],
        env={**os.environ, "PROFILE_DELEGATE_TEST_RUNTIME": str(home)},
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode != 0
    assert "pytest must run with" in completed.stderr
