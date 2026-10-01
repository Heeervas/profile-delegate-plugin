"""Explicit detached test shim stays fixture-only."""
import json
import time
from pathlib import Path
import core


def test_detached_background_worker_finalizes_completed_run(tmp_path, monkeypatch):
    original_write = core.json_safe_write

    def explicit_test_write(path, value):
        if Path(path).name == "request.json":
            value = {**value, "test_shim": True}
        return original_write(path, value)

    # Explicit persisted fixture-only bypass for the detached test worker.
    monkeypatch.setattr(core, "json_safe_write", explicit_test_write)
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setenv("PROFILE_DELEGATE_BACKGROUND_TRANSPORT", "cli")
    monkeypatch.delenv("PROFILE_DELEGATE_BACKGROUND_MODE", raising=False)
    monkeypatch.setattr(core, "validate_profile", lambda profile, policy=None: core.ValidatedProfile(profile, profile, str(tmp_path / profile)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)
    monkeypatch.setenv("PROFILE_DELEGATE_HERMES_BIN", "/bin/echo")

    result = core.delegate_profile("reviewer", "task", session_title="detached", background=True, notify_on_complete=True, transport_mode="simple")
    assert result["mode"] == "async"
    run_dir = Path(result["paths"]["run_dir"])

    status = {}
    for _ in range(100):
        status = json.loads((run_dir / "status.json").read_text())
        if status.get("status") == "completed":
            break
        time.sleep(0.05)
    assert status["status"] == "completed"
    assert status["background_worker_mode"] == "detached"
    assert status["ended_at"]
    saved = json.loads((run_dir / "result.json").read_text())
    assert saved["status"] == "unknown"
    assert saved["execution_status"] == "completed"
    assert saved["structured"] is False
    assert saved["contract_status"] == "drifted"
    assert (run_dir / "result.json").exists()
