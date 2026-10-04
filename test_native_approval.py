"""Approval source, immutable snapshot and native guard contracts."""
import copy
import json
import os
import subprocess
from pathlib import Path

import pytest

import native_approval as policy


def historical_deny(config):
    """Exact pre-repair v1 snapshot algorithm (not current normalization)."""
    native = policy.subset(config)
    value = {"schema_version": 1, "effective": "deny", "source": "yaml",
             "caller": "caller", "target": "target", "native": native,
             "bypass": native["approvals"]["mode"] == "off",
             "unattended_context": "single_query", "lineage_admission": "operator_target"}
    value["fingerprint"] = policy.fingerprint(value)
    return value


@pytest.mark.parametrize("config", [
    {"approvals": {"mode": "off"}},
    {"approvals": {"single_query_mode": "approve"}},
    {"approvals": {"unattended_mode": "approve"}},
    # Even manual/deny v1 is incompatible: old bootstrap refused dangerous
    # commands before permanent grants. Posture-only validation misses this.
    {"command_allowlist": ["rm -rf*"]},
    {},
])
def test_historical_deny_resume_and_binding_fail_closed(tmp_path, monkeypatch, config):
    import core
    from child_bootstrap import install_policy

    frozen = historical_deny(config)
    original = copy.deepcopy(frozen)
    run = tmp_path / "runs" / "old-run"
    run.mkdir(parents=True)
    target = core.ValidatedProfile("worker", "worker", "target")
    request = {"profile_home": target.home, "native_approval": frozen}
    (run / "request.json").write_text(json.dumps(request))
    (run / "status.json").write_text(json.dumps({"child_session_id": "old-session", "status": "completed"}))
    monkeypatch.setattr(core, "get_runs_root", lambda: run.parent)
    monkeypatch.setattr(core, "resolve_native_approval", lambda *args: pytest.fail("must not recompute frozen authority"))
    with pytest.raises(core.ProfileDelegateError, match="create a new session") as error:
        core.resume_native_approval(None, target, "old-session")
    assert error.value.code == "approval_policy_error"
    with pytest.raises(ValueError, match="create a new session"):
        install_policy("deny", tmp_path / "events", [], frozen)
    assert not (tmp_path / "events").exists()
    assert frozen == original
    assert json.loads((run / "request.json").read_text()) == request


@pytest.mark.parametrize("mode", ["profile", "inherit", "yolo"])
def test_v1_non_deny_authority_retained_without_migration(mode):
    value = policy.snapshot(mode, "yaml", "caller", "target", {}, {})
    value["schema_version"] = 1
    value["fingerprint"] = policy.fingerprint({k: v for k, v in value.items() if k != "fingerprint"})
    assert policy.validate(value) == value


@pytest.mark.parametrize("field,value", [("bypass", True), ("mode", "off"), ("single_query_mode", "approve"), ("unattended_mode", "approve")])
def test_v2_deny_requires_normalized_posture(field, value):
    envelope = policy.snapshot("deny", "task", "caller", "target", {}, {})
    if field == "bypass":
        envelope[field] = value
    else:
        envelope["native"]["approvals"][field] = value
    envelope["fingerprint"] = policy.fingerprint({k: v for k, v in envelope.items() if k != "fingerprint"})
    with pytest.raises(ValueError, match="unsafe deny authority"):
        policy.validate(envelope)


def test_normalized_deny_resume_keeps_fingerprint(tmp_path, monkeypatch):
    import core

    target = core.ValidatedProfile("worker", "worker", "target")
    frozen = policy.snapshot("deny", "task", "caller", target.home, {}, {"command_allowlist": ["rm -rf*"]})
    run = tmp_path / "runs" / "new-run"
    run.mkdir(parents=True)
    (run / "request.json").write_text(json.dumps({"profile_home": target.home, "native_approval": frozen}))
    (run / "status.json").write_text(json.dumps({"child_session_id": "stored-session"}))
    monkeypatch.setattr(core, "get_runs_root", lambda: run.parent)
    monkeypatch.setattr(core, "resolve_native_approval", lambda *args: pytest.fail("must not recompute"))
    assert core.resume_native_approval(None, target, "stored-session") == frozen


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


@pytest.mark.parametrize(
    ("selection", "mode", "unattended"),
    [("profile", mode, posture) for mode in ("manual", "smart", "off") for posture in ("deny", "approve")]
    + [("deny", "off", "approve")],
)
def test_installed_native_guards_in_fresh_child(tmp_path, mode, unattended, selection):
    script = tmp_path / "probe.py"
    script.write_text('''import sys, os, json
sys.path[:0] = [os.environ.get('PROFILE_DELEGATE_TEST_RUNTIME', '/opt/hermes'), REPO]
from native_approval import snapshot
from child_bootstrap import install_policy
native={'approvals':{'mode':MODE,'single_query_mode':POSTURE,'unattended_mode':POSTURE,'deny':['git push*']},'command_allowlist':['rm -rf /tmp/permanent-grant*','git push*']}
env=snapshot(SELECTION,'test','a',os.environ['HERMES_HOME'],{},native)
install_policy(SELECTION, EVENTS, [], env)
os.environ.update(HERMES_GATEWAY_SESSION='1',HERMES_EXEC_ASK='1',HERMES_INTERACTIVE='1')
from tools import approval
result={'terminal':approval.check_all_command_guards('rm -rf /tmp/disposable-never-executed','local')['approved'], 'code':approval.check_execute_code_guard('print(1)','local')['approved'], 'isolated':approval.check_execute_code_guard('print(1)','docker')['approved'], 'host':approval.check_execute_code_guard('print(1)','docker',has_host_access=True)['approved'], 'floor':approval.check_all_command_guards('git push origin main','local')['approved'], 'queues':len(approval._gateway_queues),'pending':len(approval._pending)}
print(json.dumps(result))
assert approval.check_all_command_guards('rm -rf /tmp/permanent-grant-never-executed','local')['approved']
'''.replace('REPO', repr(str(Path(__file__).parent))).replace('MODE', repr(mode)).replace('POSTURE', repr(unattended)).replace('SELECTION', repr(selection)).replace('EVENTS', "__import__('pathlib').Path("+repr(str(tmp_path/'events.jsonl'))+")"))
    env = dict(os.environ)
    env.pop("HERMES_YOLO_MODE", None)
    observed = subprocess.run([str(Path(os.environ.get("PROFILE_DELEGATE_TEST_RUNTIME", "/opt/hermes")) / ".venv/bin/python"), str(script)], env=env, text=True, capture_output=True, timeout=30)
    assert observed.returncode == 0, observed.stderr
    result = json.loads(observed.stdout.splitlines()[-1])
    allowed = selection != "deny" and (mode == "off" or unattended == "approve")
    assert result == {"terminal": allowed, "code": allowed, "isolated": True, "host": allowed, "floor": False, "queues": 0, "pending": 0}
