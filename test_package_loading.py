"""Exercise Hermes-style package loading outside the plugin working directory."""
import subprocess
import sys
from pathlib import Path


def test_package_loading_resolves_native_helpers(tmp_path):
    entry = Path(__file__).resolve().parent / "__init__.py"
    code = """
import importlib.util
import pathlib
import sys
import types
foreign = {}
for name in ('core', 'native_approval', 'native_resolution', 'native', 'execution', 'contracts'):
    foreign[name] = types.ModuleType(name)
    sys.modules[name] = foreign[name]
entry = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location('pd_package_smoke', entry,
    submodule_search_locations=[str(entry.parent)])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
from pd_package_smoke import core, native_approval, native, execution, contracts
assert native_approval.selector('approve_yolo') == 'yolo'
assert callable(core.resolve_native_approval)
assert callable(native.ledger_compatibility)
assert execution.ProfileDelegateError is contracts.ProfileDelegateError is core.ProfileDelegateError
assert callable(execution.bootstrap_command)
assert native_approval.configured_target_modes({}) == {}
assert core.load_effective_policy().values['child_approval_mode'] in ('deny', 'profile', 'inherit', 'yolo')
assert core._resume_record_matches({}, {}, types.SimpleNamespace(home='unused'), 'unused') is False
for name, value in foreign.items():
    assert sys.modules[name] is value
"""
    result = subprocess.run([sys.executable, "-c", code, str(entry)],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
