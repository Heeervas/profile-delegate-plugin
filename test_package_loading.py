"""Exercise Hermes-style package loading outside the plugin working directory."""
import subprocess
import sys
from pathlib import Path

import pytest


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


@pytest.mark.parametrize("transport", ["tui", "cli"])
@pytest.mark.parametrize("collision", ["core", "all_helpers"])
def test_child_bootstrap_ignores_foreign_modules(tmp_path, transport, collision):
    entry = Path(__file__).resolve().parent / "child_bootstrap.py"
    code = """
import importlib.util
import json
import pathlib
import sys
import types

entry, transport, collision = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
sys.path.insert(0, str(entry.parent))
from native_approval import snapshot
request = {'native_approval': snapshot('deny', 'test', 'caller', 'target', {}, {}),
           'reasoning_mode': 'inherit'}
path = pathlib.Path('request.json')
path.write_text(json.dumps(request))
names = ('core',) if collision == 'core' else (
    'core', 'native_approval', 'child_reasoning', 'contracts', 'native', 'execution')
foreign = {name: types.ModuleType(name) for name in names}
for name, module in foreign.items():
    module.__file__ = str(pathlib.Path('other-plugin') / (name + '.py'))
    sys.modules[name] = module

spec = importlib.util.spec_from_file_location('bootstrap_probe', entry)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)
observed = []
def install_policy(mode, events, blocked, envelope):
    assert mode == 'deny' and blocked == ['write_file', 'terminal']
    assert envelope == request['native_approval']
    observed.append('policy')
    # Discovery can also prepend another plugin's directory after bootstrap import.
    sys.path.insert(0, str(pathlib.Path('other-plugin').resolve()))
bootstrap.install_policy = install_policy

def native_main():
    assert observed == ['policy']
    observed.append('native')
    return 0
plugins = types.ModuleType('hermes_cli.plugins')
plugins.discover_plugins = lambda: None
sys.modules['hermes_cli'] = types.ModuleType('hermes_cli')
sys.modules['hermes_cli.plugins'] = plugins
native_name = 'tui_gateway.entry' if transport == 'tui' else 'hermes_cli.main'
sys.modules['tui_gateway'] = types.ModuleType('tui_gateway')
native_entry = types.ModuleType(native_name)
native_entry.main = native_main
sys.modules[native_name] = native_entry
args = ['--approval-mode', 'deny', '--events-path', 'events.jsonl',
        '--request-path', str(path), '--blocked-tools', 'write_file,terminal']
args += ['--tui-gateway'] if transport == 'tui' else ['--', '/installed/hermes', 'chat']
assert bootstrap.main(args) == 0
assert observed == ['policy', 'native']
for name, module in foreign.items():
    assert sys.modules[name] is module
"""
    result = subprocess.run([sys.executable, "-W", "error", "-c", code, str(entry), transport, collision],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
