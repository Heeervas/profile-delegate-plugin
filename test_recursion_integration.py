"""End-to-end request admission and real lock-slot evidence for nested delegation."""
from pathlib import Path

import pytest

import core


@pytest.fixture
def admission(tmp_path, monkeypatch):
    caller = tmp_path / "caller"
    caller.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(caller))
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setenv("PROFILE_DELEGATE_MAX_DEPTH", "2")
    monkeypatch.setenv("PROFILE_DELEGATE_MAX_CONCURRENT", "2")
    monkeypatch.delenv("PROFILE_DELEGATE_PARENT_TASK_ID", raising=False)
    monkeypatch.delenv("PROFILE_DELEGATE_DEPTH", raising=False)
    monkeypatch.setattr(core, "get_hermes_home_path", lambda: caller)
    monkeypatch.setattr(core, "validate_profile", lambda name, policy=None: core.ValidatedProfile(name, name, str(caller if name == "self" else target)))
    monkeypatch.setattr(core, "resolve_hermes_bin", lambda: "/usr/bin/true")
    return caller, target, tmp_path / "runs"


def _preflight(profile):
    return core.delegate_profile(profile, "Harmless task", session_title="nested check", preflight=True,
                                 background=False, notify_on_complete=False)


def test_top_level_self_target_is_admitted_without_lineage(admission):
    caller, _, runs = admission
    result = _preflight("self")
    assert result["success"] and result["normalized_request"]["profile"] == "self"
    assert not runs.exists()


def test_nested_cross_home_allowed_but_same_home_refused_before_artifacts(admission, monkeypatch):
    _, _, runs = admission
    monkeypatch.setenv("PROFILE_DELEGATE_DEPTH", "1")
    monkeypatch.setenv("PROFILE_DELEGATE_PARENT_TASK_ID", "pd_20260927_000000_abcdef")
    assert _preflight("other")["success"]
    with pytest.raises(core.ProfileDelegateError) as error:
        _preflight("self")
    assert error.value.code == "same_profile_delegation_not_supported"
    assert not runs.exists()


def test_configured_capacity_does_not_widen_for_nested_cross_home(admission, monkeypatch):
    if core.fcntl is None:
        pytest.skip("interprocess flock unavailable")
    _, _, runs = admission
    monkeypatch.setenv("PROFILE_DELEGATE_DEPTH", "1")
    monkeypatch.setenv("PROFILE_DELEGATE_PARENT_TASK_ID", "pd_20260927_000000_abcdef")
    # The same lock root passes to children, even when their profile home differs.
    env = core.child_environment(1, parent_task_id="pd_20260927_000000_abcdef")
    assert env["PROFILE_DELEGATE_LOCKS_ROOT"] == str(Path(core.get_locks_root()))
    assert env["PROFILE_DELEGATE_MAX_CONCURRENT"] == "2"
    with core.acquire_concurrency_slot(2) as first:
        assert _preflight("other")["success"]
        with core.acquire_concurrency_slot(2) as second:
            assert first.slot != second.slot
            with pytest.raises(core.ProfileDelegateError) as error:
                core.acquire_concurrency_slot(2)
            assert error.value.code == "concurrency_limit"
        with core.acquire_concurrency_slot(2) as reused:
            assert reused.slot == second.slot
    assert not runs.exists()


def test_depth_limit_applies_to_cross_home_even_with_spare_capacity(admission, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_DEPTH", "2")
    monkeypatch.setenv("PROFILE_DELEGATE_PARENT_TASK_ID", "pd_20260927_000000_abcdef")
    with pytest.raises(core.ProfileDelegateError) as error:
        _preflight("other")
    assert error.value.code == "recursion_limit"
