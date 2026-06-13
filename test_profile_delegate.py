"""Tests for Profile Delegate. Usage: pytest . -q"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import core
import __init__ as plugin


def test_extract_json_pure():
    assert core.extract_json_object('{"status":"ok","summary":"x"}') == {"status": "ok", "summary": "x"}


def test_extract_json_fenced():
    text = 'noise\n```json\n{"status":"ok","summary":"x"}\n```'
    obj = core.extract_json_object(text)
    assert isinstance(obj, dict)
    assert obj["status"] == "ok"


def test_extract_json_last_object():
    text = 'first {"status":"failed"}\nlast {"status":"ok","summary":"final"}'
    obj = core.extract_json_object(text)
    assert isinstance(obj, dict)
    assert obj["summary"] == "final"


def test_normalize_result_parse_failure():
    result = core.normalize_result(None, "/tmp/stdout.txt")
    assert result["status"] == "failed"
    assert result["structured"] is False
    assert result["error_code"] == "parse_failed"
    assert result["raw_output_path"] == "/tmp/stdout.txt"


def test_normalize_result_invalid_shape():
    result = core.normalize_result({"status": "weird", "artifacts": "a.md", "errors": "bad"}, "/tmp/stdout.txt")
    assert result["status"] == "failed"
    assert result["artifacts"] == ["a.md"]
    assert "invalid_status:weird" in result["errors"]


def test_build_prompt_contains_task_context_contract():
    prompt = core.build_prompt("Do the task", "ctx", "contract")
    assert "Do the task" in prompt
    assert "ctx" in prompt
    assert "contract" in prompt
    assert "Return ONLY valid JSON" in prompt


def test_plugin_registers_tools():
    calls = []

    class Ctx:
        def register_tool(self, **kwargs):
            calls.append(kwargs)

    plugin.register(Ctx())
    names = {call["name"] for call in calls}
    assert {"profile_delegate", "profile_delegate_status", "profile_delegate_list", "profile_delegate_prune"}.issubset(names)
    first = next(call for call in calls if call["name"] == "profile_delegate")
    assert first["toolset"] == "delegation"
    assert first["emoji"] == "🤝"
    assert first["schema"]["parameters"]["required"] == ["profile", "task"]


def test_handler_validation_error_json():
    data = json.loads(plugin._handler({"profile": "", "task": "x"}))
    assert data["success"] is False
    assert data["status"] == "failed"
    assert data["error_code"] == "validation_error"


def test_handler_requires_profile_policy_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("PROFILE_DELEGATE_ALLOWED_PROFILES", raising=False)
    monkeypatch.delenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", raising=False)
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setattr(core, "resolve_hermes_bin", lambda: "/usr/bin/hermes")
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="": tmp_path)

    def fake_validate(profile):
        core.enforce_profile_policy(profile)
        return core.ValidatedProfile(profile, profile, str(tmp_path / profile))

    monkeypatch.setattr(core, "validate_profile", fake_validate)
    data = json.loads(plugin._handler({"profile": "reviewer", "task": "x"}))
    assert data["success"] is False
    assert data["error_code"] == "profile_policy_required"


def test_profile_policy_allowlist(monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOWED_PROFILES", "reviewer,builder")
    monkeypatch.delenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", raising=False)
    core.enforce_profile_policy("reviewer")
    try:
        core.enforce_profile_policy("work")
    except core.ProfileDelegateError as exc:
        assert exc.code == "profile_not_allowed"
    else:
        raise AssertionError("expected profile_not_allowed")


def test_depth_policy(monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_DEPTH", "1")
    monkeypatch.setenv("PROFILE_DELEGATE_MAX_DEPTH", "1")
    try:
        core.enforce_depth_policy()
    except core.ProfileDelegateError as exc:
        assert exc.code == "recursion_limit"
    else:
        raise AssertionError("expected recursion_limit")


def test_resolve_hermes_bin_uses_absolute_path(monkeypatch):
    monkeypatch.delenv("PROFILE_DELEGATE_HERMES_BIN", raising=False)
    monkeypatch.setattr(core.shutil, "which", lambda name: "/usr/bin/hermes")
    monkeypatch.setattr(core.os, "access", lambda path, mode: True)
    assert core.resolve_hermes_bin() == "/usr/bin/hermes"


def test_resolve_hermes_bin_env_override(tmp_path, monkeypatch):
    hermes = tmp_path / "hermes"
    hermes.write_text("#!/bin/sh\n", encoding="utf-8")
    hermes.chmod(0o755)
    monkeypatch.setenv("PROFILE_DELEGATE_HERMES_BIN", str(hermes))
    monkeypatch.setattr(core.os, "access", lambda path, mode: True)
    assert core.resolve_hermes_bin() == str(hermes.resolve())


def test_workdir_requires_policy_for_explicit_path(tmp_path, monkeypatch):
    monkeypatch.delenv("PROFILE_DELEGATE_ALLOWED_WORKDIRS", raising=False)
    try:
        core.resolve_workdir(str(tmp_path))
    except core.ProfileDelegateError as exc:
        assert exc.code == "workdir_policy_required"
    else:
        raise AssertionError("expected workdir_policy_required")


def test_workdir_allowlist(tmp_path, monkeypatch):
    root = tmp_path / "allowed"
    child = root / "repo"
    child.mkdir(parents=True)
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOWED_WORKDIRS", str(root))
    assert core.resolve_workdir(str(child)) == child.resolve()
    try:
        core.resolve_workdir(str(other))
    except core.ProfileDelegateError as exc:
        assert exc.code == "workdir_not_allowed"
    else:
        raise AssertionError("expected workdir_not_allowed")


def test_concurrency_limit(tmp_path, monkeypatch):
    if core.fcntl is None:
        return
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_MAX_CONCURRENT", "1")
    with core.acquire_concurrency_slot():
        try:
            core.acquire_concurrency_slot()
        except core.ProfileDelegateError as exc:
            assert exc.code == "concurrency_limit"
        else:
            raise AssertionError("expected concurrency_limit")


def test_profile_delegate_preview_includes_profile_and_task():
    preview = plugin._profile_delegate_preview({"profile": "reviewer", "task": "Review the plan for risks and return JSON."})
    assert preview == "to reviewer: Review the plan for risks and return JSON."


def test_profile_delegate_preview_truncates_task():
    preview = plugin._profile_delegate_preview({"profile": "reviewer", "task": "x" * 200}, max_len=40)
    assert preview.startswith("to reviewer: ")
    assert preview.endswith("...")
    assert len(preview) <= 40


def test_delegate_uses_prompt_file_not_raw_prompt_in_argv(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.delenv("PROFILE_DELEGATE_HERMES_BIN", raising=False)
    monkeypatch.setattr(core.shutil, "which", lambda name: "/usr/bin/hermes")
    monkeypatch.setattr(core.os, "access", lambda path, mode: True)
    monkeypatch.setattr(core, "validate_profile", lambda profile: core.ValidatedProfile(profile, profile, str(tmp_path / profile)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="": tmp_path)
    seen = {}

    class Completed:
        stdout = '{"status":"ok","summary":"done","artifacts":[],"errors":[],"next_steps":[]}'
        stderr = ""
        returncode = 0

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["env"] = kwargs.get("env")
        return Completed()

    monkeypatch.setattr(core.subprocess, "run", fake_run)
    result = core.delegate_profile("reviewer", "PRIVATE TASK TEXT")
    assert result["success"] is True
    assert seen["cmd"][:4] == ["/usr/bin/hermes", "-p", "reviewer", "-z"]
    assert seen["cmd"][4].startswith("@file:")
    assert seen["env"]["PROFILE_DELEGATE_DEPTH"] == "1"
    assert "PRIVATE TASK TEXT" not in " ".join(seen["cmd"])


def test_status_list_and_prune(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(runs))
    task_id = "pd_20260101_010101_abc123"
    run_dir = runs / task_id
    run_dir.mkdir(parents=True)
    core.json_safe_write(run_dir / "status.json", {"task_id": task_id, "profile": "reviewer", "status": "completed", "created_at": "2020-01-01T00:00:00+00:00"})
    core.json_safe_write(run_dir / "result.json", {"status": "ok", "summary": "done"})
    core.text_safe_write(run_dir / "stdout.txt", "hello stdout")
    core.text_safe_write(run_dir / "stderr.txt", "")

    status = core.profile_delegate_status(task_id)
    assert status["task_id"] == task_id
    assert status["stdout_tail"] == "hello stdout"

    listed = core.profile_delegate_list()
    assert listed["count"] == 1

    dry = core.profile_delegate_prune(max_age_days=1, dry_run=True)
    assert dry["matched_count"] == 1
    assert run_dir.exists()
    real = core.profile_delegate_prune(max_age_days=1, dry_run=False)
    assert real["removed_count"] == 1
    assert not run_dir.exists()


def test_resolve_run_dir_rejects_bad_task_id(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    try:
        core.resolve_run_dir("../../bad")
    except core.ProfileDelegateError as exc:
        assert exc.code == "validation_error"
    else:
        raise AssertionError("expected validation error")
