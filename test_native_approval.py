"""Approval source, immutable snapshot and native guard contracts."""
import copy
import json
import os
import subprocess
from pathlib import Path

import pytest

import native_approval as policy


@pytest.mark.parametrize("mode", ["deny", "profile", "inherit", "yolo", "approve_yolo"])
def test_source_isolation_and_snapshot(mode):
    caller = {"approvals": {"mode": "manual", "deny": ["git push*"], "single_query_mode": "deny"}, "command_allowlist": ["caller"]}
    target = {"approvals": {"mode": "off", "deny": ["sudo*"], "single_query_mode": "approve"}, "command_allowlist": ["target"]}
    value = policy.snapshot(mode, "operator_target", "caller", "target", caller, target, True)
    assert value["native"]["command_allowlist"] == (["caller"] if mode == "inherit" else ["target"])
    assert value["native"]["approvals"]["deny"] == (["git push*", "sudo*"] if mode == "inherit" else ["sudo*"])
    original = copy.deepcopy(value)
    target["approvals"]["mode"] = "manual"
    assert policy.validate(value) == original
    value["bypass"] = not value["bypass"]
    with pytest.raises(ValueError, match="fingerprint"):
        policy.validate(value)


def test_nested_policy_cannot_hop_or_gain_bypass():
    ancestor = policy.snapshot("profile", "yaml", "a", "b", {}, {})
    with pytest.raises(ValueError, match="nested"):
        policy.snapshot("yolo", "yaml", "b", "c", {}, {}, True, ancestor)
    child = policy.snapshot("inherit", "yaml", "b", "c", {"approvals": {"mode": "off"}}, {"approvals": {"deny": ["git push*"]}}, True, ancestor)
    assert child["bypass"] is False
    assert child["native"]["approvals"]["mode"] == "manual"
    assert child["native"]["approvals"]["deny"] == ["git push*"]


@pytest.mark.parametrize("mode", ["manual", "smart", "off"])
@pytest.mark.parametrize("unattended", ["deny", "approve"])
def test_installed_native_guards_in_fresh_child(tmp_path, mode, unattended):
    script = tmp_path / "probe.py"
    script.write_text('''import sys, os, json
sys.path[:0] = ['/opt/hermes', REPO]
from native_approval import snapshot
from child_bootstrap import install_policy
native={'approvals':{'mode':MODE,'single_query_mode':POSTURE,'unattended_mode':POSTURE,'deny':['git push*']}}
env=snapshot('profile','test','a',os.environ['HERMES_HOME'],{},native)
install_policy('profile', EVENTS, [], env)
os.environ.update(HERMES_GATEWAY_SESSION='1',HERMES_EXEC_ASK='1',HERMES_INTERACTIVE='1')
from tools import approval
result={'terminal':approval.check_all_command_guards('rm -rf /tmp/disposable-never-executed','local')['approved'], 'code':approval.check_execute_code_guard('print(1)','local')['approved'], 'isolated':approval.check_execute_code_guard('print(1)','docker')['approved'], 'host':approval.check_execute_code_guard('print(1)','docker',has_host_access=True)['approved'], 'floor':approval.check_all_command_guards('git push origin main','local')['approved'], 'queues':len(approval._gateway_queues),'pending':len(approval._pending)}
print(json.dumps(result))
'''.replace('REPO', repr(str(Path(__file__).parent))).replace('MODE', repr(mode)).replace('POSTURE', repr(unattended)).replace('EVENTS', "__import__('pathlib').Path("+repr(str(tmp_path/'events.jsonl'))+")"))
    env = dict(os.environ)
    env.pop("HERMES_YOLO_MODE", None)
    observed = subprocess.run(["/opt/hermes/.venv/bin/python", str(script)], env=env, text=True, capture_output=True, timeout=30)
    assert observed.returncode == 0, observed.stderr
    result = json.loads(observed.stdout.splitlines()[-1])
    allowed = mode == "off" or unattended == "approve"
    assert result == {"terminal": allowed, "code": allowed, "isolated": True, "host": allowed, "floor": False, "queues": 0, "pending": 0}
