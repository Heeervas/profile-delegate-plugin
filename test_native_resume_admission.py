"""Frozen resume must not bypass current nested authority."""
import json

import pytest

import core
import native_approval


@pytest.mark.parametrize("ancestor_mode,frozen_mode", [("deny", "yolo"), ("profile", "yolo"), ("deny", "deny")])
def test_resume_rejects_broad_frozen_policy_under_restricted_ancestor(tmp_path, monkeypatch, ancestor_mode, frozen_mode):
    target = core.ValidatedProfile("worker", "worker", str(tmp_path / "worker"))
    frozen = native_approval.snapshot(frozen_mode, "operator_target", "caller", target.home, {}, {})
    ancestor = native_approval.snapshot(ancestor_mode, "yaml", "caller", "parent", {}, {"approvals": {"deny": ["git push*"]}})
    ancestor_path = tmp_path / "ancestor.json"
    ancestor_path.write_text(json.dumps({"native_approval": ancestor}))
    monkeypatch.setenv("PROFILE_DELEGATE_APPROVAL_REQUEST", str(ancestor_path))
    root = tmp_path / "runs"
    run = root / "previous"
    run.mkdir(parents=True)
    (run / "request.json").write_text(json.dumps({"profile_home": target.home, "native_approval": frozen}))
    (run / "status.json").write_text(json.dumps({"child_session_id": "frozen_session"}))
    monkeypatch.setattr(core, "get_runs_root", lambda: root)
    with pytest.raises(core.ProfileDelegateError, match="current ancestry"):
        core.resume_native_approval(core.EffectivePolicy({}, {}), target, "frozen_session")
    assert json.loads((run / "request.json").read_text())["native_approval"] == frozen


@pytest.mark.parametrize("stored,expected", [(None, "deny"), ("approve_yolo", "yolo"), ("deny", "deny")])
def test_historical_resume_preserves_stored_selector(tmp_path, monkeypatch, stored, expected):
    monkeypatch.delenv("PROFILE_DELEGATE_APPROVAL_REQUEST", raising=False)
    target = core.ValidatedProfile("worker", "worker", str(tmp_path / "worker"))
    run = tmp_path / "runs" / "old"
    run.mkdir(parents=True)
    request = {"profile_home": target.home}
    if stored:
        request["child_approval_mode"] = stored
    (run / "request.json").write_text(json.dumps(request))
    (run / "status.json").write_text(json.dumps({"child_session_id": "old_session"}))
    monkeypatch.setattr(core, "get_runs_root", lambda: run.parent)
    monkeypatch.setattr(core, "resolve_native_approval", lambda policy, target: native_approval.snapshot(
        policy.values["child_approval_mode"], "legacy", "caller", target.home, {}, {}))
    resolved = core.resume_native_approval(core.EffectivePolicy({}, {}), target, "old_session")
    assert resolved["effective"] == expected


def test_non_hermes_executable_does_not_implicitly_authorize_test_shim(tmp_path):
    command = core.build_child_command({"hermes_bin": "/bin/echo", "profile": "worker"}, tmp_path)
    assert "--test-shim" not in command


def test_cancelled_requested_resume_does_not_establish_authority(tmp_path, monkeypatch):
    target = core.ValidatedProfile("worker", "worker", str(tmp_path / "worker"))
    frozen = native_approval.snapshot("yolo", "yaml", "caller", target.home, {}, {})
    root = tmp_path / "runs"
    established = root / "established"
    stale = root / "cancelled"
    established.mkdir(parents=True)
    stale.mkdir()
    (established / "request.json").write_text(json.dumps({"profile_home": target.home, "native_approval": frozen}))
    (established / "status.json").write_text(json.dumps({"child_session_id": "actual"}))
    (stale / "request.json").write_text(json.dumps({"profile_home": target.home, "requested_session_id": "actual"}))
    (stale / "status.json").write_text(json.dumps({"status": "cancelled", "child_session_id": "actual"}))
    monkeypatch.delenv("PROFILE_DELEGATE_APPROVAL_REQUEST", raising=False)
    monkeypatch.setattr(core, "get_runs_root", lambda: root)
    assert core.resume_native_approval(core.EffectivePolicy({}, {}), target, "actual") == frozen
