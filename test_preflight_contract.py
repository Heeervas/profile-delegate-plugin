"""Preflight is a dry run of the same model-facing delegation contract."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core


def _plugin():
    spec = importlib.util.spec_from_file_location("profile_delegate_preflight_plugin", Path(__file__).parent / "__init__.py")
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    return plugin


def test_preflight_model_handler_creates_no_run(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path))
    monkeypatch.delenv("PROFILE_DELEGATE_PARENT_TASK_ID", raising=False)
    monkeypatch.delenv("PROFILE_DELEGATE_APPROVAL_REQUEST", raising=False)
    plugin = _plugin()
    payload = {"profile": "builder", "task": "Return JSON", "session_title": "dry run",
               "background": True, "preflight": True}
    observed = json.loads(plugin._handler(payload))
    assert observed["success"] is True
    assert observed["preflight"] is True
    assert observed["run_created"] is False
    assert observed["normalized_request"]["selected_transport"] == "interactive"
    assert observed["runtime_observed_capabilities"] == "unknown"
    assert observed["retry_shape"] is None
    assert not list(tmp_path.iterdir())
    assert "preflight" in plugin._schema()["parameters"]["properties"]


def test_preflight_conflicts_return_actionable_patch_without_run(tmp_path, monkeypatch):
    # This refusal contract must not inherit the invoking caller's live grant.
    monkeypatch.setattr(core, "_plugin_entry", lambda: {
        "allowed_profiles": ["builder"],
        "allow_child_approval_override": False,
        "allow_reasoning_override": False,
    })
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path))
    monkeypatch.delenv("PROFILE_DELEGATE_PARENT_TASK_ID", raising=False)
    monkeypatch.delenv("PROFILE_DELEGATE_APPROVAL_REQUEST", raising=False)
    plugin = _plugin()
    observed = json.loads(plugin._handler({"profile": "builder", "task": "Return JSON",
                                            "session_title": "dry run", "preflight": True,
                                            "reasoning_mode": "override", "child_approval_mode": "approve_yolo"}))
    assert observed["success"] is False
    assert observed["error_code"] == "execution_overrides_not_allowed"
    assert "child_approval_mode" in observed["unsupported_fields"]
    assert observed["retry_shape"]["child_approval_mode"] is None
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("bad", ["true", 1, None])
def test_preflight_flag_must_be_boolean(bad):
    with pytest.raises(core.ProfileDelegateError, match="preflight must be a boolean"):
        core.delegate_profile(profile="builder", task="x", session_title="x", preflight=bad)
