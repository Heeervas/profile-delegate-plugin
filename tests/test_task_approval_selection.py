"""Public task selector regression; runtime acceptance is separately required."""
import json
import pytest

import core
import native_approval
from test_preflight_contract import _plugin


@pytest.fixture
def admitted(tmp_path, monkeypatch):
    home = tmp_path / "caller"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(core, "resolve_hermes_bin", lambda: "/usr/bin/hermes")
    monkeypatch.delenv("PROFILE_DELEGATE_APPROVAL_REQUEST", raising=False)
    monkeypatch.delenv("PROFILE_DELEGATE_PARENT_TASK_ID", raising=False)
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setattr(core, "_plugin_entry", lambda: {
        "allow_child_approval_override": True, "child_approval_mode": "deny",
        "child_approval_modes_by_profile": {"worker": "deny"},
    })
    from hermes_cli import profiles
    monkeypatch.setattr(profiles, "profile_exists", lambda name: name == "worker")
    monkeypatch.setattr(core, "validate_profile", lambda name, policy: core.ValidatedProfile(name, name, str(tmp_path / "worker")))
    return _plugin()


@pytest.mark.parametrize("mode", ["profile", "inherit", "yolo"])
def test_public_unauthorized_task_selection_creates_no_run(admitted, monkeypatch, mode):
    monkeypatch.setattr(core, "_plugin_entry", lambda: {"allow_child_approval_override": False})
    result = json.loads(admitted._handler({"profile": "worker", "task": "x", "session_title": "selector", "child_approval_mode": mode, "preflight": True}))
    assert result["success"] is False
    assert result["error_code"] == "execution_overrides_not_allowed"
    assert result["run_created"] is False
    assert "allow_child_approval_override=true" in result["error"]


def test_public_deny_narrowing_and_omission_need_no_grant(admitted, monkeypatch):
    monkeypatch.setattr(core, "_plugin_entry", lambda: {"allow_child_approval_override": False, "child_approval_mode": "deny"})
    for extra in ({}, {"child_approval_mode": "deny"}):
        result = json.loads(admitted._handler({"profile": "worker", "task": "x", "session_title": "selector", "preflight": True, **extra}))
        assert result["success"] is True, result
        assert result["approval_policy"]["effective"] == "deny"


@pytest.mark.parametrize("mode", ["deny", "profile", "inherit", "yolo", "approve_yolo"])
def test_public_task_selection_overrides_target_default(admitted, mode):
    result = json.loads(admitted._handler({"profile": "worker", "task": "x", "session_title": "selector", "child_approval_mode": mode, "preflight": True}))
    assert result["success"] is True, result
    assert result["approval_policy"]["effective"] == native_approval.selector(mode)


@pytest.mark.parametrize("bad", ["", "bogus", [], {}, False, 1])
def test_public_malformed_selector_is_actionable(admitted, bad):
    result = json.loads(admitted._handler({"profile": "worker", "task": "x", "session_title": "selector", "child_approval_mode": bad, "preflight": True}))
    assert result["success"] is False
    assert result["error_code"] == "validation_error"
    assert "approval selector" in result["error"]


def test_selection_propagates_to_launch_without_mutating_policy(tmp_path, monkeypatch):
    policy = core.EffectivePolicy({"child_approval_mode": "deny", "child_approval_modes_by_profile": {"worker": "deny"}}, {"child_approval_mode": "yaml"})
    target = core.ValidatedProfile("worker", "worker", str(tmp_path / "worker"))
    monkeypatch.delenv("PROFILE_DELEGATE_APPROVAL_REQUEST", raising=False)
    for mode in ("deny", "profile", "inherit", "yolo"):
        envelope = core.resolve_request_approval(policy, target, "new", "", mode)
        assert envelope["source"] == "task"
        assert envelope["effective"] == mode
        command = core.build_child_command({"hermes_bin": "/opt/hermes/.venv/bin/hermes", "profile": "worker", "child_approval_mode": mode, "native_approval": envelope}, tmp_path)
        assert command[command.index("--approval-mode") + 1] == mode
        assert ("--yolo" in command) == (mode == "yolo")
    assert policy.values["child_approval_mode"] == "deny"


def test_resume_cannot_reselect(monkeypatch):
    frozen = native_approval.snapshot("deny", "task", "caller", "target", {}, {})
    monkeypatch.setattr(core, "resume_native_approval", lambda *args: frozen)
    assert core.resolve_request_approval(None, None, "resume", "sid", "deny") == frozen
    with pytest.raises(core.ProfileDelegateError, match="frozen"):
        core.resolve_request_approval(None, None, "resume", "sid", "yolo")


def test_nested_deny_narrows_bypass_without_importing_new_grants():
    ancestor = native_approval.snapshot("yolo", "task", "a", "b", {}, {"command_allowlist": ["old-grant"]})
    child = native_approval.snapshot("deny", "task", "b", "c", {}, {"command_allowlist": ["new-grant"], "approvals": {"deny": ["git push*"]}}, ancestor=ancestor)
    assert child["bypass"] is False
    assert child["native"]["command_allowlist"] == ["old-grant"]
    assert child["native"]["approvals"]["mode"] == "manual"
    assert child["native"]["approvals"]["single_query_mode"] == "deny"
    assert child["native"]["approvals"]["deny"] == ["git push*"]


def test_pytest_lineage_is_independent_of_invoking_parent():
    import os
    assert "PROFILE_DELEGATE_PARENT_TASK_ID" not in os.environ
    assert "PROFILE_DELEGATE_APPROVAL_REQUEST" not in os.environ


def test_public_selector_description_exempts_deny(admitted):
    class Context:
        def __init__(self):
            self.schemas = {}

        def register_tool(self, name, **kwargs):
            self.schemas[name] = kwargs

        def register_cli_command(self, **kwargs):
            pass

    # Read the same schema sent to the model, not a separate documentation copy.
    ctx = Context()
    admitted.register(ctx)
    description = ctx.schemas["profile_delegate"]["schema"]["parameters"]["properties"]["child_approval_mode"]["description"]
    assert "Only profile, inherit and yolo require" in description
    assert "deny narrowing is exempt" in description
