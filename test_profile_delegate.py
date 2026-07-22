"""Tests for Profile Delegate. Usage: pytest . -q"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import core
import __init__ as plugin


HERMES_TEST_PYTHON = Path("/opt/hermes/.venv/bin/python")
HAS_HERMES_RUNTIME = HERMES_TEST_PYTHON.is_file()



def setup_function(_function):
    core._async_running = 0
    core.os.environ["PROFILE_DELEGATE_DEPTH"] = "0"


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


def test_extract_json_warning_prelude_prefers_outer_envelope_over_nested_map():
    text = '''⚠ tirith security scanner enabled but not available — command scanning will use pattern matching only
{
  "status": "ok",
  "summary": "full result",
  "ssr_status": "READY",
  "mode": "DESIGN_ONLY",
  "normalized_input": {"objective": "compare"},
  "evaluation_design": {
    "expected_execution_output": {
      "rating_distribution": {
        "1": "count_or_share_placeholder",
        "2": "count_or_share_placeholder",
        "3": "count_or_share_placeholder",
        "4": "count_or_share_placeholder",
        "5": "count_or_share_placeholder"
      }
    }
  },
  "artifacts": [],
  "errors": [],
  "next_steps": []
}
'''
    obj = core.extract_json_object(text)
    assert isinstance(obj, dict)
    assert obj["summary"] == "full result"
    assert obj["ssr_status"] == "READY"
    assert "1" not in obj


def test_extract_json_multiple_objects_prefers_stronger_final_envelope():
    text = 'progress {"status":"ok","summary":"partial"}\nfinal {"status":"ok","summary":"final","artifacts":[],"errors":[],"next_steps":[]}'
    obj = core.extract_json_object(text)
    assert isinstance(obj, dict)
    assert obj["summary"] == "final"


def test_parse_json_result_rejects_equal_terminal_ambiguity():
    text = '{"status":"ok","summary":"one"}\n{"status":"blocked","summary":"two"}'
    parsed, meta = core.parse_json_result(text)
    assert parsed is None
    assert meta["parse_error"] == "ambiguous_json_candidates"
    assert meta["candidate_count"] == 2


def test_parse_json_result_ignores_nested_terminal_object():
    text = 'noise {"status":"ok","summary":"outer","data":{"status":"blocked","summary":"nested"}}'
    parsed, meta = core.parse_json_result(text)
    assert parsed["summary"] == "outer"
    assert meta["candidate_count"] == 1


def test_extract_json_ignores_non_envelope_nested_object():
    text = 'noise {"1":"placeholder","2":"placeholder"}'
    assert core.extract_json_object(text) is None


def test_delegate_parses_warning_prefixed_stdout_outer_envelope(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setattr(core.shutil, "which", lambda name: "/usr/bin/hermes")
    monkeypatch.setattr(core.os, "access", lambda path, mode: True)
    monkeypatch.setattr(core, "validate_profile", lambda profile, policy=None: core.ValidatedProfile(profile, profile, str(tmp_path / profile)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)

    stdout = '''⚠ tirith security scanner enabled but not available — command scanning will use pattern matching only
{"status":"ok","summary":"outer","ssr_status":"READY","mode":"DESIGN_ONLY","normalized_input":{},"evaluation_design":{"rating_distribution":{"1":"count_or_share_placeholder","2":"count_or_share_placeholder"}},"artifacts":[],"errors":[],"next_steps":[]}

session_id: sid_outer'''

    def fake_run_capped(cmd, **kwargs):
        core.text_safe_write(kwargs["stdout_path"], stdout)
        core.text_safe_write(kwargs["stderr_path"], "")
        return {"exit_code": 0, "timed_out": False, "stdout_truncated": False, "stderr_truncated": False, "stdout_chars": len(stdout), "stderr_chars": 0, "stdout_limit": 200000, "stderr_limit": 100000}

    monkeypatch.setattr(core, "run_capped_subprocess", fake_run_capped)
    monkeypatch.setattr(core, "rename_session", lambda *a, **k: {"session_renamed": True, "rename_exit_code": 0, "rename_error": None})
    result = core.delegate_profile("ssr_synthetic_consumer", "task", session_title="warning stdout")
    assert result["success"] is True
    assert result["child_session_id"] == "sid_outer"
    assert result["result"]["summary"] == "outer"
    assert result["result"]["ssr_status"] == "READY"
    assert "1" not in result["result"]


def test_session_id_footer_helpers():
    text = 'noise\n{"status":"ok","summary":"x"}\n\nsession_id: 20260618_065934_cd40a6'
    assert core.extract_session_id_footer(text) == "20260618_065934_cd40a6"
    stripped = core.strip_session_id_footer(text)
    assert stripped == 'noise\n{"status":"ok","summary":"x"}'
    assert core.extract_json_object(stripped)["summary"] == "x"


def test_session_id_footer_helpers_only_strip_final_footer():
    text = 'session_id: keep_me\n{"status":"ok","summary":"x"}\n\nsession_id: final_id\n\n'
    stripped, session_id = core.split_session_id_footer(text)
    assert session_id == "final_id"
    assert stripped.startswith("session_id: keep_me")
    assert "session_id: final_id" not in stripped
    no_footer = 'session_id: keep_me\n{"status":"ok"}\nnot footer'
    assert core.strip_session_id_footer(no_footer) == no_footer


def test_delegate_reads_session_footer_from_stderr(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setattr(core.shutil, "which", lambda name: "/usr/bin/hermes")
    monkeypatch.setattr(core.os, "access", lambda path, mode: True)
    monkeypatch.setattr(core, "validate_profile", lambda profile, policy=None: core.ValidatedProfile(profile, profile, str(tmp_path / profile)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)

    def fake_run_capped(cmd, **kwargs):
        core.text_safe_write(kwargs["stdout_path"], '{"status":"ok","summary":"done","artifacts":[],"errors":[],"next_steps":[]}')
        core.text_safe_write(kwargs["stderr_path"], 'session_id: sid_stderr')
        return {"exit_code": 0, "timed_out": False, "stdout_truncated": False, "stderr_truncated": False, "stdout_chars": 74, "stderr_chars": 22, "stdout_limit": 200000, "stderr_limit": 100000}

    monkeypatch.setattr(core, "run_capped_subprocess", fake_run_capped)
    monkeypatch.setattr(core, "rename_session", lambda *a, **k: {"session_renamed": True, "rename_exit_code": 0, "rename_error": None})
    result = core.delegate_profile("reviewer", "task", session_title="stderr sid")
    assert result["child_session_id"] == "sid_stderr"
    assert result["session_renamed"] is True


def test_normalize_result_parse_failure_coerces_plain_text():
    result = core.normalize_result(None, "/tmp/stdout.txt", raw_output="The file is a profile_delegate smoke-test prompt.\n\nPath: /tmp/prompt.txt")
    assert result["status"] == "unknown"
    assert result["execution_status"] == "completed"
    assert result["contract_status"] == "drifted"
    assert result["structured"] is False
    assert result["error_code"] == "unstructured_output"
    assert result["raw_output_path"] == "/tmp/stdout.txt"
    assert result["summary"] == "The file is a profile_delegate smoke-test prompt."
    assert result["errors"] == []


def test_normalize_result_recovers_blocked_markdown_without_false_success():
    raw = "scanner warning\n\n## `BLOCKED_NEEDS_FIXES`\n\nUseful review body."
    result = core.normalize_result(None, "/tmp/stdout.txt", raw_output=raw, output_mode="json")
    assert result["status"] == "blocked"
    assert result["contract_status"] == "recovered"
    assert result["structured"] is False


def test_normalize_result_statusless_custom_json_is_unknown_and_preserves_keys():
    parsed = {"verdict": "PASS", "findings": [], "summary": "useful"}
    result = core.normalize_result(parsed, "/tmp/stdout.txt")
    assert result["status"] == "unknown"
    assert result["contract_status"] == "valid"
    assert result["verdict"] == "PASS"
    assert result["findings"] == []


def test_normalize_result_empty_parse_failure_stays_failed():
    result = core.normalize_result(None, "/tmp/stdout.txt", raw_output="   ")
    assert result["status"] == "failed"
    assert result["error_code"] == "parse_failed"


def test_normalize_result_invalid_shape():
    result = core.normalize_result({"status": "weird", "artifacts": "a.md", "errors": "bad"}, "/tmp/stdout.txt")
    assert result["status"] == "failed"
    assert result["artifacts"] == ["a.md"]
    assert "invalid_status:weird" in result["errors"]


def test_result_artifact_writer_adds_current_schema_identity_and_requires_status(tmp_path):
    run_dir = tmp_path / "pd_20260721_120001_abcdef"
    run_dir.mkdir()
    core.write_result_artifact(run_dir, {
        "status": "ok", "execution_status": "completed",
        "contract_status": "valid", "summary": "done",
    })
    saved = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    assert saved["result_schema_version"] == 1
    assert saved["task_id"] == run_dir.name
    assert saved["status"] == "ok"
    with pytest.raises(core.ProfileDelegateError):
        core.write_result_artifact(run_dir, {"summary": "missing status"})
    with pytest.raises(core.ProfileDelegateError):
        core.write_result_artifact(run_dir, {"status": "ok", "summary": "missing lifecycle"})


def test_build_prompt_contains_task_context_contract():
    prompt = core.build_prompt("Do the task", "ctx", "contract")
    assert "Do the task" in prompt
    assert "ctx" in prompt
    assert "contract" in prompt
    assert "Final serialization mode: JSON object" in prompt


def test_output_mode_auto_preserves_historical_markdown_contract():
    requested, resolved = core.resolve_output_mode("auto", "Return full Markdown plan only")
    assert (requested, resolved) == ("auto", "markdown")
    prompt = core.build_prompt("task", output_contract="Return full Markdown plan only")
    assert "Resolved output mode: markdown" in prompt
    assert "Final serialization mode: Markdown" in prompt


def test_explicit_output_mode_conflicts_fail_before_launch():
    with pytest.raises(core.ProfileDelegateError) as caught:
        core.resolve_output_mode("json", "Return full Markdown plan only")
    assert caught.value.code == "contract_conflict"


def test_plugin_registers_tools():
    calls = []
    cli_calls = []

    class Ctx:
        def register_tool(self, **kwargs):
            calls.append(kwargs)

        def register_cli_command(self, **kwargs):
            cli_calls.append(kwargs)

    plugin.register(Ctx())
    assert len(cli_calls) == 1
    assert cli_calls[0]["name"] == "profile-delegate"
    assert callable(cli_calls[0]["setup_fn"])
    assert callable(cli_calls[0]["handler_fn"])
    names = {call["name"] for call in calls}
    assert {
        "profile_delegate", "profile_delegate_status", "profile_delegate_steer",
        "profile_delegate_cancel", "profile_delegate_list", "profile_delegate_prune",
    }.issubset(names)
    first = next(call for call in calls if call["name"] == "profile_delegate")
    assert first["toolset"] == "delegation"
    assert first["emoji"] == "🤝"
    assert first["schema"]["parameters"]["required"] == ["profile", "task", "session_title"]
    props = first["schema"]["parameters"]["properties"]
    assert "session_title" in props
    assert props["session_mode"]["enum"] == ["new", "resume"]
    assert "session_id" in props
    assert "background" in props
    assert "notify_on_complete" in props
    assert props["capability_preset"]["enum"] == ["review", "build"]
    assert props["child_approval_mode"]["enum"] == ["deny", "approve_yolo"]


def test_spectator_watch_command_default_and_named_profile():
    task_id = "pd_20260721_085059_dzk2o9"
    assert core.spectator_watch_command(task_id) == f"hermes profile-delegate watch {task_id}"
    assert core.spectator_watch_command(task_id, {"profile": "work"}) == f"hermes -p work profile-delegate watch {task_id}"
    assert core.spectator_watch_command(task_id, {"profile": "bad profile"}) == f"hermes profile-delegate watch {task_id}"


def test_handler_validation_error_json():
    data = json.loads(plugin._handler({"profile": "", "task": "x", "session_title": "smoke"}))
    assert data["success"] is False
    assert data["status"] == "failed"
    assert data["error_code"] == "validation_error"


def test_handler_tool_args_win_over_internal_kwargs(monkeypatch):
    seen = {}

    def fake_delegate(**kwargs):
        seen.update(kwargs)
        return {"success": True}

    monkeypatch.setattr(plugin, "delegate_profile", fake_delegate)
    data = json.loads(plugin._handler({"profile": "reviewer", "task": "x", "session_title": "smoke", "session_mode": "new", "session_id": "", "output_mode": "markdown"}, session_id="caller-session"))
    assert data["success"] is True
    assert seen["session_id"] == ""
    assert seen["output_mode"] == "markdown"


def test_status_handler_tool_task_id_wins_over_internal_kwargs(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(runs))
    task_id = "pd_20260704_100753_wwhlvu"
    internal_id = "caller-session-id"
    run_dir = runs / task_id
    run_dir.mkdir(parents=True)
    core.json_safe_write(run_dir / "status.json", {"task_id": task_id, "profile": "builder", "status": "completed"})
    core.json_safe_write(run_dir / "result.json", {"status": "ok", "summary": "done"})
    core.text_safe_write(run_dir / "stdout.txt", "stdout")
    core.text_safe_write(run_dir / "stderr.txt", "")

    data = json.loads(plugin._status_handler({"task_id": task_id}, task_id=internal_id))
    assert data["success"] is True
    assert data["task_id"] == task_id


def test_handler_passes_background_notify_and_origin_session(monkeypatch):
    seen = {}

    def fake_delegate(**kwargs):
        seen.update(kwargs)
        return {"success": True, "mode": "async"}

    monkeypatch.setattr(plugin, "delegate_profile", fake_delegate)
    monkeypatch.setattr(plugin, "_current_origin", lambda: {
        "platform": "discord", "source": "", "profile": "", "session_id": "",
        "ui_session_id": "", "session_key": "discord:guild:channel:thread",
    })
    data = json.loads(plugin._handler({"profile": "reviewer", "task": "x", "session_title": "async", "background": True, "notify_on_complete": True, "child_approval_mode": "approve_yolo", "capability_preset": "review"}))
    assert data["success"] is True
    assert seen["background"] is True
    assert seen["notify_on_complete"] is True
    assert seen["origin_session_key"] == "discord:guild:channel:thread"
    assert seen["child_approval_mode"] == "approve_yolo"
    assert seen["capability_preset"] == "review"


def test_handler_requires_profile_policy_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("PROFILE_DELEGATE_ALLOWED_PROFILES", raising=False)
    monkeypatch.delenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", raising=False)
    monkeypatch.setattr(core, "_plugin_entry", lambda: {})
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setattr(core, "resolve_hermes_bin", lambda: "/usr/bin/hermes")
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)

    def fake_validate(profile, policy=None):
        core.enforce_profile_policy(profile, policy)
        return core.ValidatedProfile(profile, profile, str(tmp_path / profile))

    monkeypatch.setattr(core, "validate_profile", fake_validate)
    data = json.loads(plugin._handler({"profile": "reviewer", "task": "x", "session_title": "smoke"}))
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


def test_child_environment_default_denies_without_parent_prompt(monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_DEPTH", "0")
    monkeypatch.setenv("HERMES_SESSION_PLATFORM", "discord")
    monkeypatch.setenv("HERMES_SESSION_KEY", "discord:guild:channel:thread")
    monkeypatch.setenv("HERMES_GATEWAY_SESSION", "1")
    monkeypatch.setenv("HERMES_EXEC_ASK", "1")
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
    monkeypatch.setenv("HERMES_CRON_SESSION", "1")
    monkeypatch.setenv("HERMES_YOLO_MODE", "1")
    monkeypatch.setenv("HERMES_ACCEPT_HOOKS", "1")

    env = core.child_environment(0)
    assert env["PROFILE_DELEGATE_DEPTH"] == "1"
    assert "HERMES_CRON_SESSION" not in env
    assert "HERMES_YOLO_MODE" not in env
    assert "HERMES_ACCEPT_HOOKS" not in env
    assert "HERMES_SESSION_PLATFORM" not in env
    assert "HERMES_SESSION_KEY" not in env
    assert "HERMES_GATEWAY_SESSION" not in env
    assert "HERMES_EXEC_ASK" not in env
    assert "HERMES_INTERACTIVE" not in env


def test_child_environment_approve_yolo_is_explicit(monkeypatch):
    monkeypatch.setenv("HERMES_SESSION_PLATFORM", "discord")
    env = core.child_environment(0, "approve_yolo")
    assert env["PROFILE_DELEGATE_DEPTH"] == "1"
    assert env["HERMES_YOLO_MODE"] == "1"
    assert env["HERMES_ACCEPT_HOOKS"] == "1"
    assert "HERMES_SESSION_PLATFORM" not in env
    assert "HERMES_CRON_SESSION" not in env


def test_child_environment_strip_only_strips_without_policy_flags(monkeypatch):
    with pytest.raises(core.ProfileDelegateError, match="no longer accepted") as exc:
        core.child_environment(0, "strip_only")
    assert exc.value.code == "validation_error"


def test_plugin_config_legacy_strip_only_migrates_fail_closed(monkeypatch):
    import types

    fake_config = types.SimpleNamespace(load_config=lambda: {"plugins": {"entries": {"profile-delegate": {"child_approval_mode": "strip_only"}}}})
    monkeypatch.setitem(sys.modules, "hermes_cli.config", fake_config)
    assert core.plugin_config_child_approval_mode() == "deny"


def test_review_capability_preset_filters_mutating_schema_and_terminal(monkeypatch):
    monkeypatch.delenv("PROFILE_DELEGATE_ALLOWED_TOOLSETS", raising=False)
    requested = core.normalize_requested_execution()
    effective, capabilities = core.resolve_capability_preset("review", requested)
    assert effective["toolsets"] == ["web", "file"]
    assert {"write_file", "patch", "execute_code", "terminal", "process"}.issubset(
        capabilities["blocked_tools"]
    )
    assert capabilities["terminal_access"] is False


def test_review_capability_preset_rejects_ambiguous_toolset_override():
    requested = core.normalize_requested_execution()
    requested["toolsets"] = ["terminal"]
    with pytest.raises(core.ProfileDelegateError, match="cannot be combined"):
        core.resolve_capability_preset("review", requested)


def test_build_capability_preset_preserves_requested_execution(monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOWED_TOOLSETS", "web,terminal")
    requested = core.normalize_requested_execution(toolsets=["web", "terminal"])
    effective, capabilities = core.resolve_capability_preset("build", requested)
    assert effective == requested
    assert capabilities["preset"] == "build"
    assert capabilities["blocked_tools"] == []


def test_child_command_uses_plugin_bootstrap_before_hermes(tmp_path):
    request = {
        "hermes_bin": "/opt/hermes/.venv/bin/hermes",
        "profile": "reviewer",
        "child_approval_mode": "deny",
        "requested_execution": {},
        "effective_capabilities": {"blocked_tools": []},
        "session_mode": "new",
    }
    cmd = core.build_child_command(request, tmp_path)
    expected_python = Path("/opt/hermes/.venv/bin/python")
    assert cmd[0] == str(expected_python if expected_python.is_file() else Path(sys.executable))
    assert Path(cmd[1]).name == "child_bootstrap.py"
    assert cmd[cmd.index("--approval-mode") + 1] == "deny"
    assert cmd[cmd.index("--events-path") + 1] == str(tmp_path / "approval_events.jsonl")
    separator = cmd.index("--")
    assert cmd[separator + 1] == "/opt/hermes/.venv/bin/hermes"


@pytest.mark.skipif(not HAS_HERMES_RUNTIME, reason="requires an installed Hermes runtime")
def test_bootstrap_real_subprocess_deny_is_immediate_and_observable(tmp_path):
    events = tmp_path / "approval_events.jsonl"
    script = f"""
import json, pathlib, time
import child_bootstrap
child_bootstrap.install_policy('deny', pathlib.Path({str(events)!r}), [])
from tools import terminal_tool
started=time.monotonic()
danger=terminal_tool._check_all_guards('git reset --hard HEAD', 'local')
safe=terminal_tool._check_all_guards('printf safe', 'local')
from tools import approval
code=approval.check_execute_code_guard('print(1)', 'local')
print(json.dumps({{'danger': danger, 'safe': safe, 'code': code, 'elapsed': time.monotonic()-started}}))
"""
    completed = subprocess.run(
        [str(HERMES_TEST_PYTHON), "-c", script], cwd=str(PLUGIN_DIR), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    assert result["danger"]["approved"] is False
    assert result["safe"]["approved"] is True
    assert result["code"]["approved"] is False
    assert result["elapsed"] < 3
    raw_events = events.read_text()
    assert "git reset --hard HEAD" not in raw_events
    event_rows = [json.loads(line) for line in raw_events.splitlines()]
    assert any(row.get("outcome") == "denied" for row in event_rows)
    assert any(row.get("detector") == "execute_code" for row in event_rows)


@pytest.mark.skipif(not HAS_HERMES_RUNTIME, reason="requires an installed Hermes runtime")
def test_bootstrap_real_subprocess_yolo_keeps_hardline_floor(tmp_path):
    events = tmp_path / "approval_events.jsonl"
    script = f"""
import json, pathlib, os
os.environ['HERMES_YOLO_MODE']='1'
import child_bootstrap
child_bootstrap.install_policy('approve_yolo', pathlib.Path({str(events)!r}), [])
from tools import terminal_tool
print(json.dumps({{'recoverable': terminal_tool._check_all_guards('git reset --hard HEAD', 'local'), 'hardline': terminal_tool._check_all_guards('rm -rf /', 'local')}}))
"""
    completed = subprocess.run(
        [str(HERMES_TEST_PYTHON), "-c", script], cwd=str(PLUGIN_DIR), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    assert result["recoverable"]["approved"] is True
    assert result["hardline"]["approved"] is False


@pytest.mark.skipif(not HAS_HERMES_RUNTIME, reason="requires an installed Hermes runtime")
def test_bootstrap_review_filter_removes_mutators_from_real_schema(tmp_path):
    events = tmp_path / "approval_events.jsonl"
    blocked = ["write_file", "patch", "execute_code", "terminal", "process"]
    script = f"""
import json, pathlib
import child_bootstrap
child_bootstrap.install_policy('deny', pathlib.Path({str(events)!r}), {blocked!r})
import run_agent
defs=run_agent.get_tool_definitions(enabled_toolsets=['web','file'], quiet_mode=True)
names=[item['function']['name'] for item in defs]
print(json.dumps(names))
"""
    completed = subprocess.run(
        [str(HERMES_TEST_PYTHON), "-c", script], cwd=str(PLUGIN_DIR), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    names = set(json.loads(completed.stdout.strip().splitlines()[-1]))
    assert {"read_file", "search_files"}.issubset(names)
    assert not names.intersection(blocked)


def test_approval_timeout_marker_becomes_structured_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setattr(core, "validate_profile", lambda profile, policy=None: core.ValidatedProfile(profile, profile, str(tmp_path / profile)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)
    monkeypatch.setattr(core, "resolve_hermes_bin", lambda: "/usr/bin/hermes")

    def fake_run(_cmd, **kwargs):
        core.text_safe_write(kwargs["stdout_path"], "Timeout — denying command\n")
        core.text_safe_write(kwargs["stderr_path"], "")
        return {"exit_code": 0, "timed_out": False, "stdout_truncated": False, "stderr_truncated": False, "stdout_chars": 27, "stderr_chars": 0, "stdout_limit": 200000, "stderr_limit": 100000}

    monkeypatch.setattr(core, "run_capped_subprocess", fake_run)
    result = core.delegate_profile("reviewer", "task", session_title="timeout marker")
    assert result["success"] is False
    assert result["error_code"] == "approval_timeout"
    assert result["result"]["errors"] == ["approval_timeout_marker"]
    assert result["result"]["execution_status"] == "failed"
    assert result["result"]["contract_status"] == "not_evaluated"


def test_plugin_config_child_approval_mode_reads_yaml(monkeypatch):
    import types

    fake_config = types.SimpleNamespace(load_config=lambda: {"plugins": {"entries": {"profile-delegate": {"child_approval_mode": "approve_yolo"}}}})
    monkeypatch.setitem(sys.modules, "hermes_cli.config", fake_config)
    assert core.plugin_config_child_approval_mode() == "approve_yolo"


def test_timeout_defaults_and_caps(monkeypatch):
    expected_default = int(os.getenv("PROFILE_DELEGATE_DEFAULT_TIMEOUT_SECONDS", "1200"))
    assert core.DEFAULT_TIMEOUT_SECONDS == expected_default
    assert core.MAX_TIMEOUT_SECONDS >= core.DEFAULT_TIMEOUT_SECONDS
    assert core.coerce_timeout(None) == expected_default
    assert core.coerce_timeout(core.MAX_TIMEOUT_SECONDS) == core.MAX_TIMEOUT_SECONDS
    try:
        core.coerce_timeout(core.MAX_TIMEOUT_SECONDS + 1)
    except core.ProfileDelegateError as exc:
        assert exc.code == "validation_error"
        assert f"<= {core.MAX_TIMEOUT_SECONDS}" in str(exc)
    else:
        raise AssertionError("expected validation_error")

    expanded_values = core.load_effective_policy().values.copy()
    expanded_values["max_timeout_seconds"] = 86_400
    expanded = core.EffectivePolicy(expanded_values, {})
    assert core.coerce_timeout(86_400, expanded) == 86_400
    uncapped_values = expanded_values.copy()
    uncapped_values["max_timeout_seconds"] = 0
    uncapped = core.EffectivePolicy(uncapped_values, {})
    assert core.coerce_timeout(604_800, uncapped) == 604_800


def test_schema_uses_runtime_timeout_defaults(monkeypatch):
    props = plugin._schema()["parameters"]["properties"]["timeout_seconds"]
    assert props["default"] == core.DEFAULT_TIMEOUT_SECONDS
    assert props["maximum"] == core.MAX_TIMEOUT_SECONDS

    monkeypatch.setattr(plugin, "MAX_TIMEOUT_SECONDS", 0)
    uncapped = plugin._schema()["parameters"]["properties"]["timeout_seconds"]
    assert "maximum" not in uncapped
    assert "no plugin cap" in uncapped["description"]


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
    monkeypatch.setattr(core, "_plugin_entry", lambda: {})
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


def test_profile_delegate_preview_uses_title():
    preview = plugin._profile_delegate_preview({"profile": "reviewer", "session_title": "review plan riesgos", "task": "Review the plan for risks and return JSON."})
    assert preview == "to reviewer: review plan riesgos"


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
    monkeypatch.setattr(core, "validate_profile", lambda profile, policy=None: core.ValidatedProfile(profile, profile, str(tmp_path / profile)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)
    seen = {}

    def fake_run_capped(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["env"] = kwargs.get("env")
        core.text_safe_write(kwargs["stdout_path"], '{"status":"ok","summary":"done","artifacts":[],"errors":[],"next_steps":[]}\n\nsession_id: sid999')
        core.text_safe_write(kwargs["stderr_path"], "")
        return {"exit_code": 0, "timed_out": False, "stdout_truncated": False, "stderr_truncated": False, "stdout_chars": 74, "stderr_chars": 0, "stdout_limit": 200000, "stderr_limit": 100000}

    monkeypatch.setattr(core, "run_capped_subprocess", fake_run_capped)
    result = core.delegate_profile("reviewer", "PRIVATE TASK TEXT", session_title="private task")
    assert result["success"] is True
    assert result["result"]["execution_status"] == "completed"
    assert result["result"]["contract_status"] == "valid"
    separator = seen["cmd"].index("--")
    child = seen["cmd"][separator + 1:]
    assert child[:5] == ["/usr/bin/hermes", "-p", "reviewer", "chat", "-q"]
    assert child[5].startswith("@file:")
    assert "-Q" in child
    assert "--pass-session-id" in child
    assert "--source" in child
    assert "profile-delegate" in child
    assert "--resume" not in child
    assert seen["env"]["PROFILE_DELEGATE_DEPTH"] == "1"
    assert "PRIVATE TASK TEXT" not in " ".join(seen["cmd"])


def test_run_capped_subprocess_limits_stdout_stderr(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_MAX_STDOUT_CHARS", "25")
    monkeypatch.setenv("PROFILE_DELEGATE_MAX_STDERR_CHARS", "10")
    code = "import sys; print('x'*100); print('e'*50, file=sys.stderr)"
    result = core.run_capped_subprocess(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={},
        timeout=10,
        stdout_path=tmp_path / "stdout.txt",
        stderr_path=tmp_path / "stderr.txt",
    )
    assert result["exit_code"] == 0
    assert result["stdout_truncated"] is True
    assert result["stderr_truncated"] is True
    assert len((tmp_path / "stdout.txt").read_text()) == 25
    assert len((tmp_path / "stderr.txt").read_text()) == 10


def test_delegate_reports_truncated_output(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setattr(core, "validate_profile", lambda profile, policy=None: core.ValidatedProfile(profile, profile, str(tmp_path / profile)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)
    monkeypatch.setattr(core, "resolve_hermes_bin", lambda: sys.executable)

    def fake_run_capped(cmd, **kwargs):
        core.text_safe_write(kwargs["stdout_path"], '{"status":"ok","summary":"done","artifacts":[],"errors":[],"next_steps":[]}\n\nsession_id: sid999')
        core.text_safe_write(kwargs["stderr_path"], "")
        return {"exit_code": 0, "timed_out": False, "stdout_truncated": True, "stderr_truncated": False, "stdout_chars": 5, "stderr_chars": 0, "stdout_limit": 5, "stderr_limit": 5}

    monkeypatch.setattr(core, "run_capped_subprocess", fake_run_capped)
    result = core.delegate_profile("reviewer", "task", session_title="smoke")
    assert result["stdout_truncated"] is True
    status = core.profile_delegate_status(result["task_id"])
    assert status["stdout_truncated"] is True


def test_run_capped_subprocess_timeout_keeps_bounded_output(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_MAX_STDOUT_CHARS", "12")
    monkeypatch.setenv("PROFILE_DELEGATE_MAX_STDERR_CHARS", "12")
    marker = tmp_path / "grandchild.pid"
    code = (
        "import pathlib,subprocess,sys,time; "
        f"p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); pathlib.Path({str(marker)!r}).write_text(str(p.pid)); "
        "print('ready', flush=True); time.sleep(30)"
    )
    result = core.run_capped_subprocess(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={},
        timeout=1,
        stdout_path=tmp_path / "stdout.txt",
        stderr_path=tmp_path / "stderr.txt",
    )
    assert result["timed_out"] is True
    assert result["exit_code"] is None
    assert len((tmp_path / "stdout.txt").read_text()) <= 12
    grandchild_pid = int(marker.read_text())
    deadline = time.time() + 2
    while Path(f"/proc/{grandchild_pid}").exists() and time.time() < deadline:
        time.sleep(0.05)
    assert not Path(f"/proc/{grandchild_pid}").exists()



def test_delegate_background_returns_running_and_finishes(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setenv("PROFILE_DELEGATE_BACKGROUND_MODE", "thread")
    monkeypatch.setattr(core.shutil, "which", lambda name: "/usr/bin/hermes")
    monkeypatch.setattr(core.os, "access", lambda path, mode: True)
    monkeypatch.setattr(core, "validate_profile", lambda profile, policy=None: core.ValidatedProfile(profile, profile, str(tmp_path / profile)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)
    monkeypatch.setattr(core, "_push_profile_delegate_completion", lambda run_dir, final: None)

    def fake_run_capped(cmd, **kwargs):
        core.text_safe_write(kwargs["stdout_path"], '{"status":"ok","summary":"done","artifacts":[],"errors":[],"next_steps":[]}\n\nsession_id: sid_async')
        core.text_safe_write(kwargs["stderr_path"], "")
        return {"exit_code": 0, "timed_out": False, "stdout_truncated": False, "stderr_truncated": False, "stdout_chars": 92, "stderr_chars": 0, "stdout_limit": 200000, "stderr_limit": 100000}

    monkeypatch.setattr(core, "run_capped_subprocess", fake_run_capped)
    monkeypatch.setattr(core, "rename_session", lambda *a, **k: {"session_renamed": True, "rename_exit_code": 0, "rename_error": None})
    result = core.delegate_profile("reviewer", "task", session_title="async", background=True, origin_session_key="discord:guild:chan")
    assert result["mode"] == "async"
    assert result["status"] == "running"
    run_dir = Path(result["paths"]["run_dir"])

    for _ in range(50):
        status = json.loads((run_dir / "status.json").read_text())
        if status.get("status") == "completed":
            break
        time.sleep(0.05)
    assert status["status"] == "completed"
    saved = json.loads((run_dir / "request.json").read_text())
    assert saved["background"] is True
    assert saved["origin_session_key"] == "discord:guild:chan"
    assert json.loads((run_dir / "result.json").read_text())["session_id"] == "sid_async"


def test_detached_background_worker_finalizes_completed_run(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setenv("PROFILE_DELEGATE_BACKGROUND_TRANSPORT", "cli")
    monkeypatch.delenv("PROFILE_DELEGATE_BACKGROUND_MODE", raising=False)
    monkeypatch.setattr(core, "validate_profile", lambda profile, policy=None: core.ValidatedProfile(profile, profile, str(tmp_path / profile)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)
    monkeypatch.setenv("PROFILE_DELEGATE_HERMES_BIN", "/bin/echo")

    result = core.delegate_profile("reviewer", "task", session_title="detached", background=True, notify_on_complete=True)
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



def test_delegate_background_start_failure_marks_run_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setattr(core.shutil, "which", lambda name: "/usr/bin/hermes")
    monkeypatch.setattr(core.os, "access", lambda path, mode: True)
    monkeypatch.setattr(core, "validate_profile", lambda profile, policy=None: core.ValidatedProfile(profile, profile, str(tmp_path / profile)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)
    monkeypatch.setattr(core, "_start_background_run", lambda run_dir: (_ for _ in ()).throw(core.ProfileDelegateError("capacity", "async_concurrency_limit")))
    try:
        core.delegate_profile("reviewer", "task", session_title="async", background=True, origin_session_key="discord:guild:chan")
    except core.ProfileDelegateError as exc:
        assert exc.code == "async_concurrency_limit"
    else:
        raise AssertionError("expected async_concurrency_limit")
    runs = list((tmp_path / "runs").iterdir())
    assert len(runs) == 1
    status = json.loads((runs[0] / "status.json").read_text())
    result = json.loads((runs[0] / "result.json").read_text())
    assert status["status"] == "failed"
    assert status["error_code"] == "async_concurrency_limit"
    assert result["error_code"] == "async_concurrency_limit"
    assert result["execution_status"] == "failed"
    assert result["contract_status"] == "not_evaluated"


def test_push_profile_delegate_completion_queues_async_event(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_NOTIFY_MAX_SUMMARY_CHARS", "1000")
    run_dir = tmp_path / "runs" / "pd_20260101_010101_abc123"
    run_dir.mkdir(parents=True)
    request = {
        "task_id": run_dir.name,
        "profile": "reviewer",
        "session_title": "async smoke",
        "session_mode": "new",
        "origin_session_key": "discord:guild:chan:thread",
        "notify_on_complete": True,
        "dispatched_at_epoch": 1000.0,
    }
    core.json_safe_write(run_dir / "request.json", request)
    core.json_safe_write(run_dir / "status.json", {**request, "status": "completed"})
    final = {"success": True, "status": "completed", "result": {"status": "ok", "summary": "done", "artifacts": [], "errors": [], "next_steps": []}, "paths": core.base_paths(run_dir)}

    class Queue:
        def __init__(self):
            self.items = []
        def put(self, item):
            self.items.append(item)

    class Registry:
        completion_queue = Queue()

    import types
    fake_mod = types.SimpleNamespace(process_registry=Registry())
    monkeypatch.setitem(sys.modules, "tools.process_registry", fake_mod)
    core._push_profile_delegate_completion(run_dir, final)
    assert len(Registry.completion_queue.items) == 1
    evt = Registry.completion_queue.items[0]
    assert evt["type"] == "async_delegation"
    assert evt["session_key"] == "discord:guild:chan:thread"
    assert evt["delegation_id"] == run_dir.name
    status = json.loads((run_dir / "status.json").read_text())
    assert status["notification_status"] == "queued"
    assert status["notified_at"]


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

    listed = core.profile_delegate_list(scope="all")
    assert listed["count"] == 1

    dry = core.profile_delegate_prune(max_age_days=1, dry_run=True)
    assert dry["matched_count"] == 1
    assert run_dir.exists()
    real = core.profile_delegate_prune(max_age_days=1, dry_run=False)
    assert real["removed_count"] == 1
    assert not run_dir.exists()


def test_status_surfaces_only_safe_event_metadata_and_legacy_missing_journal(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(runs))
    run_dir = runs / "pd_20260101_010101_abc123"
    run_dir.mkdir(parents=True)
    core.json_safe_write(run_dir / "status.json", {
        "task_id": run_dir.name, "status": "completed", "phase": "completed",
        "event_schema_version": 1, "event_seq": 17, "event_stream_truncated": True,
        "observability_degraded": True, "observability_error": "disk_full",
        "turn_count": 2, "api_calls": 3, "tool_calls": 4,
        "usage": {"input": 5, "output": 6, "total": 11, "calls": 3},
        "message_text": "must not escape", "persisted_text": "also private",
    })
    core.json_safe_write(run_dir / "result.json", {"status": "ok", "summary": "canonical"})

    inspected = core.profile_delegate_status(run_dir.name)
    assert inspected["event_metadata"] == {
        "schema_version": 1, "seq": 17, "truncated": True, "degraded": True,
        "degradation_reason": "disk_full", "turn_count": 2, "api_calls": 3,
        "tool_calls": 4, "usage": {"input": 5, "output": 6, "total": 11, "calls": 3},
    }
    assert inspected["result"]["summary"] == "canonical"
    assert "must not escape" not in json.dumps(inspected)
    assert not (run_dir / "events.jsonl").exists()


@pytest.mark.parametrize("lifecycle", [None, "corrupt", "unknown", "running", "cancelling"])
def test_prune_skips_every_nonterminal_or_unreadable_run(tmp_path, monkeypatch, lifecycle):
    runs = tmp_path / "runs"
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(runs))
    run_dir = runs / "pd_20200101_000000_abcdef"
    run_dir.mkdir(parents=True)
    if lifecycle is None:
        pass
    elif lifecycle == "corrupt":
        (run_dir / "status.json").write_text("not json", encoding="utf-8")
    else:
        core.json_safe_write(run_dir / "status.json", {
            "status": lifecycle, "created_at": "2020-01-01T00:00:00+00:00",
        })

    result = core.profile_delegate_prune(max_age_days=1, dry_run=False)
    assert result["matched_count"] == result["removed_count"] == 0
    assert run_dir.exists()


def test_prune_rereads_under_shared_lock_and_skips_terminal_race(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(runs))
    run_dir = runs / "pd_20200101_000000_abcdef"
    run_dir.mkdir(parents=True)
    core.json_safe_write(run_dir / "status.json", {
        "status": "completed", "created_at": "2020-01-01T00:00:00+00:00",
    })
    real_open = core.os.open

    def race_on_lock(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if str(path).endswith("status.lock"):
            core.json_safe_write(run_dir / "status.json", {
                "status": "cancelling", "created_at": "2020-01-01T00:00:00+00:00",
            })
        return fd

    monkeypatch.setattr(core.os, "open", race_on_lock)
    result = core.profile_delegate_prune(max_age_days=1, dry_run=False)
    assert result["removed_count"] == 0 and run_dir.exists()


def test_prune_renames_to_tombstone_before_deleting(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(runs))
    run_dir = runs / "pd_20200101_000000_abcdef"
    run_dir.mkdir(parents=True)
    core.json_safe_write(run_dir / "status.json", {
        "status": "completed", "created_at": "2020-01-01T00:00:00+00:00",
    })
    deleted = []
    real_rmtree = core.shutil.rmtree

    def record_delete(path, *args, **kwargs):
        candidate = Path(path)
        deleted.append(candidate)
        assert candidate.parent == runs
        assert candidate.name.startswith(".tombstone-")
        assert not candidate.name.startswith("pd_")
        assert not run_dir.exists()
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(core.shutil, "rmtree", record_delete)
    result = core.profile_delegate_prune(max_age_days=1, dry_run=False)
    assert result["removed_count"] == 1 and len(deleted) == 1


def test_status_writer_waiting_on_renamed_run_fails_closed_without_resurrection(tmp_path, monkeypatch):
    run_dir = tmp_path / "pd_20200101_000000_abcdef"
    run_dir.mkdir()
    core.json_safe_write(run_dir / "status.json", {
        "task_id": run_dir.name, "status": "completed",
        "created_at": "2020-01-01T00:00:00+00:00",
    })
    tombstone = tmp_path / f".tombstone-{run_dir.name}-deterministic"
    real_flock = core.fcntl.flock
    renamed = False

    def rename_while_waiter_acquires(fd, operation):
        nonlocal renamed
        if operation == core.fcntl.LOCK_EX and not renamed:
            renamed = True
            core.os.rename(run_dir, tombstone)
        return real_flock(fd, operation)

    monkeypatch.setattr(core.fcntl, "flock", rename_while_waiter_acquires)
    with pytest.raises(core.ProfileDelegateError) as exc:
        core.merge_run_status(run_dir, {"notification_status": "queued"})
    assert exc.value.code in {"run_status_vanished", "run_identity_changed"}
    assert not run_dir.exists()
    assert tombstone.exists()


def test_prune_rejects_symlink_run_and_wrong_uid(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(runs))
    target = tmp_path / "target"
    target.mkdir()
    core.json_safe_write(target / "status.json", {
        "status": "completed", "created_at": "2020-01-01T00:00:00+00:00",
    })
    runs.mkdir()
    (runs / "pd_20200101_000000_symlink").symlink_to(target, target_is_directory=True)
    wrong_uid = runs / "pd_20200101_000001_baduid"
    wrong_uid.mkdir()
    core.json_safe_write(wrong_uid / "status.json", {
        "status": "completed", "created_at": "2020-01-01T00:00:00+00:00",
    })
    real_lstat = core.os.lstat

    def foreign_lstat(path, *args, **kwargs):
        info = real_lstat(path, *args, **kwargs)
        if Path(path) == wrong_uid:
            values = list(info)
            values[4] = core.os.getuid() + 1
            return os.stat_result(values)
        return info

    monkeypatch.setattr(core.os, "lstat", foreign_lstat)
    result = core.profile_delegate_prune(max_age_days=1, dry_run=False)
    assert result["removed_count"] == 0
    assert target.exists() and wrong_uid.exists()


def test_resolve_run_dir_rejects_bad_task_id(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    ok = tmp_path / "runs" / "pd_20260101_010101_abcdef12"
    ok.mkdir(parents=True)
    assert core.resolve_run_dir("pd_20260101_010101_abcdef12") == ok.resolve()
    try:
        core.resolve_run_dir("../../bad")
    except core.ProfileDelegateError as exc:
        assert exc.code == "validation_error"
    else:
        raise AssertionError("expected validation error")


def test_session_title_required_and_truncated():
    try:
        core.normalize_session_title("")
    except core.ProfileDelegateError as exc:
        assert exc.code == "validation_error"
    else:
        raise AssertionError("expected validation_error")
    assert core.normalize_session_title("x" * 80) == "x" * 50


def test_resume_mode_requires_session_id():
    try:
        core.validate_session_id("", required=True)
    except core.ProfileDelegateError as exc:
        assert exc.code == "validation_error"
    else:
        raise AssertionError("expected validation_error")
    try:
        core.coerce_session_mode("continue")
    except core.ProfileDelegateError as exc:
        assert exc.code == "validation_error"
    else:
        raise AssertionError("expected validation_error")


def test_transient_classifier_is_strict_and_deterministic():
    assert core.classify_transient_failure(exit_code=1, timed_out=False, stdout="RemoteProtocolError: incomplete chunked read", stderr="", parsed_result=None) == "incomplete_chunked_read"
    assert core.classify_transient_failure(exit_code=1, timed_out=False, stdout="API call failed after 3 retries: Connection error.", stderr="", parsed_result=None) == "connection_error"
    assert core.classify_transient_failure(exit_code=1, timed_out=False, stdout="API call failed after 3 retries: Connection error.", stderr="HTTP 401", parsed_result=None) is None
    assert core.classify_transient_failure(exit_code=-9, timed_out=False, stdout="API call failed after 3 retries: Connection error.", stderr="", parsed_result=None) is None


def test_transient_failure_resumes_same_session(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setattr(core.shutil, "which", lambda name: "/usr/bin/hermes")
    monkeypatch.setattr(core.os, "access", lambda path, mode: True)
    monkeypatch.setattr(core, "validate_profile", lambda profile, policy=None: core.ValidatedProfile(profile, profile, str(tmp_path / profile)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)
    monkeypatch.setattr(core.time, "sleep", lambda _s: None)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            stdout, code = "API call failed after 3 retries: Connection error.\nsession_id: stable_sid", 1
        else:
            stdout, code = '{"status":"ok","summary":"done","artifacts":[],"errors":[],"next_steps":[]}\nsession_id: stable_sid', 0
        core.text_safe_write(kwargs["stdout_path"], stdout)
        core.text_safe_write(kwargs["stderr_path"], "")
        return {"exit_code": code, "timed_out": False, "stdout_truncated": False, "stderr_truncated": False, "stdout_chars": len(stdout), "stderr_chars": 0, "stdout_limit": 200000, "stderr_limit": 100000, "stdout_diagnostic_tail": stdout, "stderr_diagnostic_tail": ""}

    monkeypatch.setattr(core, "run_capped_subprocess", fake_run)
    monkeypatch.setattr(core, "rename_session", lambda *a, **k: {"session_renamed": True})
    result = core.delegate_profile("reviewer", "task", session_title="recover")
    assert result["success"] is True
    assert len(calls) == 2
    assert calls[1][calls[1].index("--resume") + 1] == "stable_sid"
    assert [item["transient_reason"] for item in result["recovery_history"]] == ["connection_error", None]


def test_transient_failure_without_session_id_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setattr(core.shutil, "which", lambda name: "/usr/bin/hermes")
    monkeypatch.setattr(core.os, "access", lambda path, mode: True)
    monkeypatch.setattr(core, "validate_profile", lambda profile, policy=None: core.ValidatedProfile(profile, profile, str(tmp_path / profile)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        stdout = "API call failed after 3 retries: Connection error."
        core.text_safe_write(kwargs["stdout_path"], stdout)
        core.text_safe_write(kwargs["stderr_path"], "")
        return {"exit_code": 1, "timed_out": False, "stdout_truncated": False, "stderr_truncated": False, "stdout_chars": len(stdout), "stderr_chars": 0, "stdout_limit": 200000, "stderr_limit": 100000, "stdout_diagnostic_tail": stdout, "stderr_diagnostic_tail": ""}

    monkeypatch.setattr(core, "run_capped_subprocess", fake_run)
    result = core.delegate_profile("reviewer", "task", session_title="safe failure")
    assert len(calls) == 1
    assert result["error_code"] == "transient_resume_session_missing"
    assert result["result"]["execution_status"] == "failed"


def test_delegate_resume_uses_resume_flag_and_skips_rename(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setattr(core.shutil, "which", lambda name: "/usr/bin/hermes")
    monkeypatch.setattr(core.os, "access", lambda path, mode: True)
    monkeypatch.setattr(core, "validate_profile", lambda profile, policy=None: core.ValidatedProfile(profile, profile, str(tmp_path / profile)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)
    seen = {}

    def fake_run_capped(cmd, **kwargs):
        seen["cmd"] = cmd
        core.text_safe_write(kwargs["stdout_path"], '{"status":"ok","summary":"done","artifacts":[],"errors":[],"next_steps":[]}\n\nsession_id: sid123')
        core.text_safe_write(kwargs["stderr_path"], "")
        return {"exit_code": 0, "timed_out": False, "stdout_truncated": False, "stderr_truncated": False, "stdout_chars": 92, "stderr_chars": 0, "stdout_limit": 200000, "stderr_limit": 100000}

    monkeypatch.setattr(core, "run_capped_subprocess", fake_run_capped)
    monkeypatch.setattr(core, "rename_session", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not rename resume")))
    result = core.delegate_profile("reviewer", "task", session_title="seguir tests", session_mode="resume", session_id="sid123")
    assert result["success"] is True
    assert "--yolo" not in seen["cmd"]
    assert result["child_approval_mode"] == "deny"
    assert "--resume" in seen["cmd"]
    assert seen["cmd"][seen["cmd"].index("--resume") + 1] == "sid123"
    assert "--pass-session-id" in seen["cmd"]
    assert result["session_renamed"] is False


def test_delegate_approve_yolo_tool_arg_adds_yolo_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setattr(core.shutil, "which", lambda name: "/usr/bin/hermes")
    monkeypatch.setattr(core.os, "access", lambda path, mode: True)
    monkeypatch.setattr(core, "validate_profile", lambda profile, policy=None: core.ValidatedProfile(profile, profile, str(tmp_path / profile)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)
    seen = {}

    def fake_run_capped(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["env"] = kwargs["env"]
        core.text_safe_write(kwargs["stdout_path"], '{"status":"ok","summary":"done","artifacts":[],"errors":[],"next_steps":[]}\n\nsession_id: sid_yolo')
        core.text_safe_write(kwargs["stderr_path"], "")
        return {"exit_code": 0, "timed_out": False, "stdout_truncated": False, "stderr_truncated": False, "stdout_chars": 92, "stderr_chars": 0, "stdout_limit": 200000, "stderr_limit": 100000}

    monkeypatch.setattr(core, "run_capped_subprocess", fake_run_capped)
    monkeypatch.setattr(core, "rename_session", lambda *a, **k: {"session_renamed": True, "rename_exit_code": 0, "rename_error": None})
    result = core.delegate_profile("reviewer", "task", session_title="yolo", child_approval_mode="approve_yolo")
    assert result["success"] is True
    assert result["child_approval_mode"] == "approve_yolo"
    assert "--yolo" in seen["cmd"]
    assert seen["env"]["HERMES_YOLO_MODE"] == "1"
    assert seen["env"]["HERMES_ACCEPT_HOOKS"] == "1"


def test_delegate_new_renames_when_session_id_present(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setattr(core.shutil, "which", lambda name: "/usr/bin/hermes")
    monkeypatch.setattr(core.os, "access", lambda path, mode: True)
    monkeypatch.setattr(core, "validate_profile", lambda profile, policy=None: core.ValidatedProfile(profile, profile, str(tmp_path / profile)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)
    renamed = {}

    def fake_run_capped(cmd, **kwargs):
        core.text_safe_write(kwargs["stdout_path"], '{"status":"ok","summary":"done","artifacts":[],"errors":[],"next_steps":[]}\n\nsession_id: sid999')
        core.text_safe_write(kwargs["stderr_path"], "")
        return {"exit_code": 0, "timed_out": False, "stdout_truncated": False, "stderr_truncated": False, "stdout_chars": 92, "stderr_chars": 0, "stdout_limit": 200000, "stderr_limit": 100000}

    def fake_rename(hermes_bin, profile, session_id, title, cwd, env, timeout=30):
        renamed.update({"profile": profile, "session_id": session_id, "title": title})
        return {"session_renamed": True, "rename_exit_code": 0, "rename_error": None}

    monkeypatch.setattr(core, "run_capped_subprocess", fake_run_capped)
    monkeypatch.setattr(core, "rename_session", fake_rename)
    result = core.delegate_profile("reviewer", "task", session_title="x" * 80)
    assert result["success"] is True
    assert result["child_session_id"] == "sid999"
    assert result["session_title"] == "x" * 50
    assert result["session_renamed"] is True
    assert renamed == {"profile": "reviewer", "session_id": "sid999", "title": "x" * 50}


def test_delegate_new_missing_session_id_keeps_success_without_rename(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setattr(core.shutil, "which", lambda name: "/usr/bin/hermes")
    monkeypatch.setattr(core.os, "access", lambda path, mode: True)
    monkeypatch.setattr(core, "validate_profile", lambda profile, policy=None: core.ValidatedProfile(profile, profile, str(tmp_path / profile)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)

    def fake_run_capped(cmd, **kwargs):
        core.text_safe_write(kwargs["stdout_path"], '{"status":"ok","summary":"done","artifacts":[],"errors":[],"next_steps":[]}')
        core.text_safe_write(kwargs["stderr_path"], "")
        return {"exit_code": 0, "timed_out": False, "stdout_truncated": False, "stderr_truncated": False, "stdout_chars": 74, "stderr_chars": 0, "stdout_limit": 200000, "stderr_limit": 100000}

    monkeypatch.setattr(core, "run_capped_subprocess", fake_run_capped)
    result = core.delegate_profile("reviewer", "task", session_title="smoke")
    assert result["success"] is True
    assert result["session_renamed"] is False
    assert result["rename_error"] == "child_session_id_missing"


def test_chmod_best_effort_ignores_permission_error(tmp_path, monkeypatch):
    path = tmp_path / "x.txt"
    path.write_text("x", encoding="utf-8")
    monkeypatch.setattr(core.os, "chmod", lambda *a, **k: (_ for _ in ()).throw(PermissionError("nope")))
    core.chmod_best_effort(path, 0o600)


def test_execution_override_schema_contract():
    props = plugin._schema()["parameters"]["properties"]
    assert props["reasoning_effort"]["enum"] == ["none", "minimal", "low", "medium", "high", "xhigh", "max"]
    assert props["max_turns"]["minimum"] == 1
    assert props["max_turns"]["maximum"] == 10000
    for name in ("model", "provider", "reasoning_effort", "max_turns", "toolsets", "skills"):
        assert name in props
    assert props["toolsets"]["items"]["type"] == "string"
    assert props["skills"]["items"]["type"] == "string"


def test_execution_override_normalization_and_fail_closed_policy(monkeypatch):
    monkeypatch.delenv("PROFILE_DELEGATE_ALLOWED_TOOLSETS", raising=False)
    monkeypatch.delenv("PROFILE_DELEGATE_ALLOWED_SKILLS", raising=False)
    assert core.normalize_requested_execution(model="  openai/gpt-5  ", provider=" openai ", max_turns=9) == {
        "model": "openai/gpt-5", "provider": "openai", "reasoning_effort": None,
        "max_turns": 9, "toolsets": [], "skills": [],
    }
    assert core.normalize_requested_execution(reasoning_effort="max")["reasoning_effort"] == "max"
    for kwargs in ({"reasoning_effort": "ultra"}, {"max_turns": 0}, {"max_turns": True},
                   {"toolsets": ["file"]}, {"skills": ["hermes-agent"]},
                   {"toolsets": [""]}, {"skills": "hermes-agent"}):
        try:
            core.normalize_requested_execution(**kwargs)
        except core.ProfileDelegateError as exc:
            assert exc.code in {"validation_error", "execution_overrides_not_allowed"}
        else:
            raise AssertionError(f"expected validation error for {kwargs}")


def test_execution_override_allowlists_and_exact_argv(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOWED_TOOLSETS", "file,terminal")
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOWED_SKILLS", "hermes-agent,test-driven-development")
    requested = core.normalize_requested_execution(model="openai/gpt-5", provider="openai", max_turns=12,
        toolsets=["file", "terminal"], skills=["hermes-agent"])
    request = {"profile": "reviewer", "session_mode": "new", "requested_session_id": "",
               "child_approval_mode": "deny", "hermes_bin": "/usr/bin/hermes", "requested_execution": requested}
    cmd = core.build_child_command(request, tmp_path)
    assert Path(cmd[1]).name == "child_bootstrap.py"
    assert cmd[cmd.index("--approval-mode") + 1] == "deny"
    separator = cmd.index("--")
    assert cmd[separator + 1:] == [
        "/usr/bin/hermes", "-p", "reviewer", "chat", "-q", f"@file:{tmp_path / 'prompt.txt'}", "-Q",
        "--model", "openai/gpt-5", "--provider", "openai", "--max-turns", "12",
        "--toolsets", "file,terminal", "--skills", "hermes-agent",
        "--pass-session-id", "--source", "profile-delegate",
    ]


def test_reasoning_config_without_existing_scope_and_rejects_destination_symlink(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    managed_dir = core.prepare_reasoning_config(run_dir, "high")
    assert core.load_yaml_mapping(managed_dir / "config.yaml") == {"agent": {"reasoning_effort": "high"}}
    assert sorted(path.name for path in managed_dir.iterdir()) == ["config.yaml"]
    assert not (managed_dir / "config.yaml").is_symlink()

    unsafe = tmp_path / "unsafe"
    unsafe.mkdir()
    (unsafe / "reasoning_config").symlink_to(tmp_path / "external", target_is_directory=True)
    with pytest.raises(core.ProfileDelegateError, match="symlink"):
        core.prepare_reasoning_config(unsafe, "high")


def test_discover_managed_scope_rejects_nonblank_inherited_value_without_filesystem_lookup(monkeypatch):
    monkeypatch.setattr(core, "DEFAULT_MANAGED_SCOPE", Path("/definitely/missing/default-managed-scope"))

    assert core.discover_managed_scope({"HERMES_MANAGED_DIR": " relative-admin "}) == Path("relative-admin")


def test_discover_managed_scope_treats_existing_default_file_as_conflict(tmp_path, monkeypatch):
    default_scope = tmp_path / "hermes"
    default_scope.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(core, "DEFAULT_MANAGED_SCOPE", default_scope)

    assert core.discover_managed_scope({}) == default_scope


def test_reasoning_override_rejects_existing_scope_before_run_mutation(tmp_path, monkeypatch):
    root = tmp_path / "root"
    profile_home = root / "profiles" / "reviewer"
    profile_home.mkdir(parents=True)
    admin_managed = tmp_path / "admin-managed"
    admin_managed.mkdir()
    (admin_managed / "config.yaml").write_text("security: {tirith_enabled: true}\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_MANAGED_DIR", str(admin_managed))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    request = {
        "profile": "reviewer", "profile_home": str(profile_home), "timeout_seconds": 10,
        "workdir": str(tmp_path), "hermes_bin": "/usr/bin/hermes", "session_mode": "new",
        "requested_session_id": "", "session_title": "conflict", "delegate_depth": 0,
        "child_approval_mode": "deny", "requested_execution": {
            "model": None, "provider": None, "reasoning_effort": "high", "max_turns": None,
            "toolsets": [], "skills": [],
        },
    }
    core.json_safe_write(run_dir / "request.json", request)
    original_status = {**request, "status": "running"}
    core.json_safe_write(run_dir / "status.json", original_status)
    core.text_safe_write(run_dir / "prompt.txt", "prompt")
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setattr(core, "run_capped_subprocess", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")))

    with pytest.raises(core.ProfileDelegateError, match="managed scope") as exc_info:
        core._execute_delegate_run(run_dir)

    assert exc_info.value.code == "reasoning_managed_scope_conflict"
    assert not (run_dir / "reasoning_config").exists()
    assert json.loads((run_dir / "status.json").read_text()) == original_status


def test_reasoning_override_without_scope_keeps_canonical_home_and_session(tmp_path, monkeypatch):
    profile_home = tmp_path / "profiles" / "reviewer"
    profile_home.mkdir(parents=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    request = {
        "profile": "reviewer", "profile_home": str(profile_home), "timeout_seconds": 10,
        "workdir": str(tmp_path), "hermes_bin": "/usr/bin/hermes", "session_mode": "new",
        "requested_session_id": "", "session_title": "reasoning", "delegate_depth": 0,
        "child_approval_mode": "deny", "requested_execution": {
            "model": None, "provider": None, "reasoning_effort": "high", "max_turns": None,
            "toolsets": [], "skills": [],
        },
    }
    core.json_safe_write(run_dir / "request.json", request)
    core.json_safe_write(run_dir / "status.json", {**request, "status": "running"})
    core.text_safe_write(run_dir / "prompt.txt", "prompt")
    seen = {}
    def fake_run(cmd, **kwargs):
        seen["run_env"] = kwargs["env"]
        core.text_safe_write(kwargs["stdout_path"], '{"status":"ok","summary":"done","artifacts":[],"errors":[],"next_steps":[]}\n\nsession_id: canonical_sid')
        core.text_safe_write(kwargs["stderr_path"], "")
        return {"exit_code": 0, "timed_out": False, "stdout_truncated": False, "stderr_truncated": False,
                "stdout_chars": 1, "stderr_chars": 0, "stdout_limit": 200000, "stderr_limit": 100000}
    def fake_rename(*args, **kwargs):
        seen["rename_env"] = args[5]
        return {"session_renamed": True}
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setattr(core, "discover_managed_scope", lambda env: None)
    monkeypatch.setattr(core, "run_capped_subprocess", fake_run)
    monkeypatch.setattr(core, "rename_session", fake_rename)
    core._execute_delegate_run(run_dir)
    expected_home = str(profile_home.resolve())
    expected_managed = str(run_dir / "reasoning_config")
    assert seen["run_env"]["HERMES_HOME"] == expected_home
    assert seen["run_env"]["HERMES_MANAGED_DIR"] == expected_managed
    assert seen["rename_env"]["HERMES_HOME"] == expected_home
    assert seen["rename_env"]["HERMES_MANAGED_DIR"] == expected_managed
    assert core.load_yaml_mapping(run_dir / "reasoning_config" / "config.yaml") == {"agent": {"reasoning_effort": "high"}}
    assert json.loads((run_dir / "result.json").read_text())["session_id"] == "canonical_sid"


def test_default_profile_reasoning_override_rejected_before_run_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setattr(core, "validate_profile", lambda p, policy=None: core.ValidatedProfile("default", "default", str(tmp_path)))
    with pytest.raises(core.PreflightError) as exc_info:
        core.delegate_profile("default", "task", session_title="default override", reasoning_effort="high")
    assert "reasoning_effort" in exc_info.value.details["unsupported_fields"]
    assert exc_info.value.details["run_created"] is False
    assert not (tmp_path / "runs").exists()


def test_execution_metadata_persisted_sync(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setattr(core, "validate_profile", lambda p, policy=None: core.ValidatedProfile(p, p, str(tmp_path / p)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)
    monkeypatch.setattr(core, "resolve_hermes_bin", lambda: "/usr/bin/hermes")
    def fake_run(cmd, **kwargs):
        core.text_safe_write(kwargs["stdout_path"], '{"status":"ok","summary":"done","artifacts":[],"errors":[],"next_steps":[]}')
        core.text_safe_write(kwargs["stderr_path"], "")
        return {"exit_code": 0, "timed_out": False, "stdout_truncated": False, "stderr_truncated": False,
                "stdout_chars": 1, "stderr_chars": 0, "stdout_limit": 200000, "stderr_limit": 100000}
    monkeypatch.setattr(core, "run_capped_subprocess", fake_run)
    result = core.delegate_profile("reviewer", "task", session_title="override", model=" demo ", max_turns=3)
    run_dir = Path(result["paths"]["run_dir"])
    expected = {"model": "demo", "provider": None, "reasoning_effort": None, "max_turns": 3, "toolsets": [], "skills": []}
    assert result["requested_execution"] == expected
    assert json.loads((run_dir / "request.json").read_text())["requested_execution"] == expected
    assert json.loads((run_dir / "status.json").read_text())["requested_execution"] == expected
    assert json.loads((run_dir / "result.json").read_text())["requested_execution"] == expected


ORIGIN_A = {
    "platform": "discord",
    "source": "discord",
    "profile": "default",
    "session_id": "session-a",
    "ui_session_id": "ui-a",
    "session_key": "discord:guild:channel:thread",
}


def _write_inspection_run(runs, task_id, **overrides):
    run_dir = runs / task_id
    run_dir.mkdir(parents=True)
    status = {
        "artifact_schema_version": 2,
        "task_id": task_id,
        "profile": "builder",
        "session_title": "inspection run",
        "status": "completed",
        "created_at": "2026-07-17T10:00:00+00:00",
        "ended_at": "2026-07-17T10:01:00+00:00",
        "error_code": None,
        "origin": dict(ORIGIN_A),
        "origin_session_key": ORIGIN_A["session_key"],
        "background_worker_mode": "detached",
        "worker_pid": 123,
        "notification_status": "queued",
    }
    status.update(overrides)
    core.json_safe_write(run_dir / "status.json", status)
    core.text_safe_write(run_dir / "stdout.txt", "")
    core.text_safe_write(run_dir / "stderr.txt", "")
    return run_dir


def test_current_origin_reads_only_normalized_concurrency_safe_session_fields(monkeypatch):
    import types

    values = {
        "HERMES_SESSION_PLATFORM": " discord ",
        "HERMES_SESSION_SOURCE": "discord",
        "HERMES_SESSION_PROFILE": "default",
        "HERMES_SESSION_ID": "session-a",
        "HERMES_UI_SESSION_ID": "ui-a",
        "HERMES_SESSION_KEY": "discord:guild:channel:thread",
        "HERMES_SESSION_USER_ID": "must-not-persist",
    }
    fake = types.SimpleNamespace(get_session_env=lambda name, default="": values.get(name, default))
    monkeypatch.setitem(sys.modules, "gateway.session_context", fake)

    assert plugin._current_origin() == ORIGIN_A


def test_handler_passes_origin_without_overwriting_target_session_id(monkeypatch):
    seen = {}
    monkeypatch.setattr(plugin, "_current_origin", lambda: dict(ORIGIN_A))
    monkeypatch.setattr(plugin, "delegate_profile", lambda **kwargs: seen.update(kwargs) or {"success": True})

    data = json.loads(plugin._handler(
        {"profile": "reviewer", "task": "x", "session_title": "origin", "session_id": "target-session"},
        session_id="caller-session",
    ))

    assert data["success"] is True
    assert seen["session_id"] == "target-session"
    assert seen["origin"] == ORIGIN_A
    assert seen["origin_session_key"] == ORIGIN_A["session_key"]


def test_delegate_persists_schema_v3_origin_and_legacy_key(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setattr(core, "validate_profile", lambda p, policy=None: core.ValidatedProfile(p, p, str(tmp_path / p)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)
    monkeypatch.setattr(core, "resolve_hermes_bin", lambda: "/usr/bin/hermes")
    monkeypatch.setattr(core, "_start_background_run", lambda run_dir: None)

    result = core.delegate_profile(
        "reviewer", "task", session_title="origin persistence", background=True,
        origin={**ORIGIN_A, "session_id": "  session-a  ", "unexpected": "private"},
    )
    run_dir = Path(result["paths"]["run_dir"])
    request = json.loads((run_dir / "request.json").read_text())
    status = json.loads((run_dir / "status.json").read_text())

    for artifact in (request, status):
        assert artifact["artifact_schema_version"] == 3
        assert artifact["origin"]["session_id"] == "session-a"
        assert artifact["origin_session_key"] == ORIGIN_A["session_key"]
        assert "unexpected" not in artifact["origin"]


def test_normalize_persisted_origin_supports_v2_legacy_and_missing():
    assert core.normalize_persisted_origin({"origin": ORIGIN_A}) == ORIGIN_A
    legacy = core.normalize_persisted_origin({"origin_session_key": "discord:legacy"})
    assert legacy == {
        "platform": "", "source": "", "profile": "", "session_id": "",
        "ui_session_id": "", "session_key": "discord:legacy",
    }
    assert core.normalize_persisted_origin({}) == {
        "platform": "", "source": "", "profile": "", "session_id": "",
        "ui_session_id": "", "session_key": "",
    }


@pytest.mark.parametrize(
    ("run_origin", "caller_origin", "scope", "expected"),
    [
        ({**ORIGIN_A, "ui_session_id": "ui-a"}, ORIGIN_A, "current_session", (True, "ui_session_id")),
        ({**ORIGIN_A, "ui_session_id": "ui-other"}, ORIGIN_A, "current_session", (False, "ui_session_id")),
        ({**ORIGIN_A, "ui_session_id": "", "session_id": "session-a"}, ORIGIN_A, "current_session", (True, "session_id")),
        ({"session_key": ORIGIN_A["session_key"]}, ORIGIN_A, "current_session", (True, "session_key")),
        ({**ORIGIN_A, "session_id": "session-other"}, {**ORIGIN_A, "ui_session_id": ""}, "current_session", (False, "session_id")),
        ({**ORIGIN_A, "session_id": "session-other"}, ORIGIN_A, "current_lane", (True, "session_key")),
        ({}, ORIGIN_A, "current_session", (False, None)),
        ({}, {}, "all", (True, None)),
    ],
)
def test_origin_match_precedence_and_legacy_fallback(run_origin, caller_origin, scope, expected):
    assert core.origin_match(run_origin, caller_origin, scope) == expected


def test_activity_projection_is_read_only_and_handles_liveness(monkeypatch):
    assert core.derive_activity({"status": "completed", "worker_pid": 1}) == {
        "activity": "finished", "worker_alive": None,
    }
    monkeypatch.setattr(core.os, "kill", lambda pid, signal: None)
    assert core.derive_activity({"status": "running", "background_worker_mode": "detached", "worker_pid": 123}) == {
        "activity": "active", "worker_alive": True,
    }
    monkeypatch.setattr(core.os, "kill", lambda pid, signal: (_ for _ in ()).throw(ProcessLookupError()))
    assert core.derive_activity({"status": "running", "background_worker_mode": "detached", "worker_pid": 123}) == {
        "activity": "stale", "worker_alive": False,
    }
    monkeypatch.setattr(core.os, "kill", lambda pid, signal: (_ for _ in ()).throw(PermissionError()))
    assert core.probe_worker_alive(123) is True
    assert core.derive_activity({"status": "running", "background_worker_mode": "thread"}) == {
        "activity": "unknown", "worker_alive": None,
    }
    assert core.derive_activity({"status": "running", "background_worker_mode": "detached", "worker_pid": "bad"}) == {
        "activity": "unknown", "worker_alive": None,
    }


def test_list_defaults_to_current_session_and_composes_scope_filters(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(runs))
    _write_inspection_run(runs, "pd_20260717_100003_cccccc", session_title="same session")
    _write_inspection_run(
        runs, "pd_20260717_100002_bbbbbb", session_title="same lane older session",
        origin={**ORIGIN_A, "ui_session_id": "", "session_id": "session-old"},
    )
    _write_inspection_run(
        runs, "pd_20260717_100001_aaaaaa", profile="reviewer", session_title="other lane",
        status="running", origin={**ORIGIN_A, "ui_session_id": "ui-z", "session_id": "session-z", "session_key": "discord:other"},
    )

    current = core.profile_delegate_list(caller_origin=ORIGIN_A)
    assert current["scope_requested"] == "current_session"
    assert current["scope_effective"] == "current_session"
    assert current["origin_match_by"] == "ui_session_id"
    assert [item["session_title"] for item in current["runs"]] == ["same session"]
    assert current["runs"][0]["activity"] == "finished"
    assert current["runs"][0]["origin"] == ORIGIN_A

    lane = core.profile_delegate_list(scope="current_lane", caller_origin=ORIGIN_A)
    assert [item["session_title"] for item in lane["runs"]] == ["same session", "same lane older session"]

    all_running_reviewer = core.profile_delegate_list(
        scope="all", statuses=["running"], profile="reviewer", caller_origin=ORIGIN_A,
    )
    assert [item["session_title"] for item in all_running_reviewer["runs"]] == ["other lane"]


def test_list_applies_limit_after_filter_and_reports_unresolved_scope(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(runs))
    _write_inspection_run(runs, "pd_20260717_100003_cccccc", origin={**ORIGIN_A, "session_id": "other"})
    _write_inspection_run(runs, "pd_20260717_100002_bbbbbb")
    _write_inspection_run(runs, "pd_20260717_100001_aaaaaa")

    listed = core.profile_delegate_list(limit=1, caller_origin={**ORIGIN_A, "ui_session_id": ""})
    assert listed["count"] == 1
    assert listed["runs"][0]["task_id"] == "pd_20260717_100002_bbbbbb"

    unresolved = core.profile_delegate_list(caller_origin={})
    assert unresolved["count"] == 0
    assert unresolved["scope_effective"] == "unresolved"
    assert "scope='all'" in unresolved["warning"]

    unresolved_lane = core.profile_delegate_list(scope="current_lane", caller_origin={})
    assert unresolved_lane["count"] == 0
    assert unresolved_lane["scope_effective"] == "unresolved"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"scope": "everything"},
        {"scope": "all", "statuses": "running"},
        {"scope": "all", "statuses": ["queued"]},
    ],
)
def test_list_rejects_invalid_scope_and_status_filters(kwargs):
    with pytest.raises(core.ProfileDelegateError) as exc_info:
        core.profile_delegate_list(**kwargs)
    assert exc_info.value.code == "validation_error"


def test_list_preserves_corrupt_runs_for_explicit_global_inspection(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(runs))
    corrupt = runs / "pd_20260717_100001_aaaaaa"
    corrupt.mkdir(parents=True)
    (corrupt / "status.json").write_text("not json", encoding="utf-8")

    listed = core.profile_delegate_list(scope="all", statuses=["corrupt"])
    assert listed["count"] == 1
    assert listed["runs"][0]["status"] == "corrupt"


def test_status_enriches_origin_ownership_worker_and_notification_without_mutation(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(runs))
    run_dir = _write_inspection_run(
        runs, "pd_20260717_100001_aaaaaa", status="running", worker_pid=4321,
        notification_status="pending",
    )
    before = (run_dir / "status.json").read_bytes()
    monkeypatch.setattr(core.os, "kill", lambda pid, signal: None)

    same = core.profile_delegate_status(run_dir.name, caller_origin=ORIGIN_A)
    other = core.profile_delegate_status(run_dir.name, caller_origin={**ORIGIN_A, "ui_session_id": "ui-other"})
    unavailable = core.profile_delegate_status(run_dir.name, caller_origin={})

    assert same["session_title"] == "inspection run"
    assert same["origin"] == ORIGIN_A
    assert same["belongs_to_current_session"] is True
    assert same["origin_match_by"] == "ui_session_id"
    assert same["background_worker_mode"] == "detached"
    assert same["worker_pid"] == 4321
    assert same["worker_alive"] is True
    assert same["activity"] == "active"
    assert same["notification_status"] == "pending"
    assert other["belongs_to_current_session"] is False
    assert unavailable["belongs_to_current_session"] is None
    assert (run_dir / "status.json").read_bytes() == before


def test_status_lock_merge_preserves_fields_and_terminal_is_immutable(tmp_path):
    run_dir = tmp_path / "pd_20260717_100001_aaaaaa"
    run_dir.mkdir()
    core.json_safe_write(run_dir / "status.json", {"task_id": run_dir.name, "status": "running", "worker_pid": 12})
    core.merge_run_status(run_dir, {"phase": "model_running", "event_seq": 3})
    completed = core.merge_run_status(run_dir, {"status": "completed", "ended_at": "now"}, terminal=True)
    assert completed["worker_pid"] == 12 and completed["event_seq"] == 3
    after = core.merge_run_status(run_dir, {"status": "cancelling", "notification_status": "queued"})
    assert after["status"] == "completed" and after["notification_status"] == "queued"
    assert (run_dir / "status.lock").stat().st_mode & 0o777 == 0o600


def test_base_paths_and_launch_freeze_event_contract(tmp_path, monkeypatch):
    assert core.base_paths(tmp_path)["events"] == str(tmp_path / "events.jsonl")
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setenv("PROFILE_DELEGATE_BACKGROUND_MODE", "thread")
    monkeypatch.setenv("PROFILE_DELEGATE_PERSIST_MESSAGE_TEXT", "true")
    monkeypatch.setattr(core.shutil, "which", lambda name: "/usr/bin/hermes")
    monkeypatch.setattr(core.os, "access", lambda path, mode: True)
    monkeypatch.setattr(core, "validate_profile", lambda profile, policy=None: core.ValidatedProfile(profile, profile, str(tmp_path / profile)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)
    monkeypatch.setattr(core, "_start_background_run", lambda run_dir: None)
    result = core.delegate_profile("reviewer", "task", session_title="journal", background=True)
    request = json.loads((Path(result["paths"]["run_dir"]) / "request.json").read_text())
    assert request["persist_message_text"] is True


def test_legacy_status_remains_readable_and_matches_by_lane(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(runs))
    run_dir = runs / "pd_20260717_100001_aaaaaa"
    run_dir.mkdir(parents=True)
    core.json_safe_write(run_dir / "status.json", {
        "task_id": run_dir.name, "profile": "builder", "status": "running",
        "origin_session_key": ORIGIN_A["session_key"],
    })
    core.text_safe_write(run_dir / "stdout.txt", "")
    core.text_safe_write(run_dir / "stderr.txt", "")

    status = core.profile_delegate_status(run_dir.name, caller_origin=ORIGIN_A)
    assert status["origin"]["session_key"] == ORIGIN_A["session_key"]
    assert status["belongs_to_current_session"] is True
    assert status["origin_match_by"] == "session_key"
    assert status["activity"] == "unknown"


def test_list_and_status_handlers_capture_origin_and_schema_contract(monkeypatch):
    seen = {}
    monkeypatch.setattr(plugin, "_current_origin", lambda: dict(ORIGIN_A))
    monkeypatch.setattr(
        plugin, "profile_delegate_list",
        lambda **kwargs: seen.setdefault("list", kwargs) or {"success": True},
    )
    monkeypatch.setattr(
        plugin, "profile_delegate_status",
        lambda *args, **kwargs: seen.setdefault("status", (args, kwargs)) or {"success": True},
    )

    json.loads(plugin._list_handler({"scope": "all", "status": ["running"], "profile": "builder", "limit": 5}))
    json.loads(plugin._status_handler({"task_id": "pd_20260717_100001_aaaaaa", "tail_chars": 99}))

    assert seen["list"] == {
        "limit": 5, "scope": "all", "statuses": ["running"], "profile": "builder",
        "caller_origin": ORIGIN_A,
    }
    assert seen["status"][1]["caller_origin"] == ORIGIN_A
    list_props = plugin._list_schema()["parameters"]["properties"]
    assert list_props["scope"]["default"] == "current_session"
    assert list_props["scope"]["enum"] == ["current_session", "current_lane", "all"]
    assert list_props["status"]["items"]["enum"] == [
        "running", "cancelling", "completed", "failed", "cancelled", "timed_out", "corrupt",
    ]
    assert "profile" in list_props


def test_active_duplicate_lookup_reuses_only_active_identical_run(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    fingerprint = "f" * 64
    run_dir = tmp_path / "runs" / "pd_20260719_000000_aaaaaa"
    run_dir.mkdir(parents=True)
    core.json_safe_write(run_dir / "status.json", {
        "task_id": run_dir.name,
        "status": "running",
        "request_fingerprint": fingerprint,
        "created_at": core.now_iso(),
        "dispatched_at_epoch": core.time.time(),
        "background": True,
        "owner_pid": core.os.getpid(),
    })
    active = core._active_matching_run(fingerprint, 120)
    assert active is not None
    assert active["task_id"] == run_dir.name
    assert core._active_matching_run("0" * 64, 120) is None
    status = core.read_json_file(run_dir / "status.json")
    status["status"] = "completed"
    core.json_safe_write(run_dir / "status.json", status)
    assert core._active_matching_run(fingerprint, 120) is None


def test_preflight_aggregates_reasoning_toolsets_and_skills():
    policy = core.EffectivePolicy({
        "allowed_toolsets": [], "allowed_skills": [], "allow_model_override": True,
        "allow_provider_override": True, "allow_reasoning_override": True,
        "allow_child_approval_override": True,
    }, {})
    requested = {"model": None, "provider": None, "reasoning_effort": "none",
                 "max_turns": None, "toolsets": ["terminal"], "skills": ["x"]}
    with pytest.raises(core.PreflightError) as exc_info:
        core.validate_preflight(requested, policy, reasoning_mode="inherit",
                                capability_preset="build", target_profile="reviewer",
                                child_approval_explicit=False)
    assert exc_info.value.details["unsupported_fields"] == [
        "reasoning_mode", "reasoning_effort", "toolsets", "skills"
    ]
    assert exc_info.value.details["run_created"] is False


def test_reasoning_omission_inherits_and_none_is_explicit():
    assert core.normalize_reasoning_request(None, None) == ("inherit", None)
    assert core.normalize_reasoning_request(None, "none") == ("override", "none")


def test_identical_concurrent_background_requests_create_one_run(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setattr(core, "validate_profile", lambda p, policy=None: core.ValidatedProfile(p, p, str(tmp_path / p)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)
    monkeypatch.setattr(core, "resolve_hermes_bin", lambda: "/usr/bin/hermes")
    monkeypatch.setattr(core, "_start_background_run", lambda run_dir: None)
    origin = {"session_id": "same-origin"}
    barrier = threading.Barrier(2)
    results = []

    def invoke():
        barrier.wait()
        results.append(core.delegate_profile("reviewer", "same task", session_title="same",
                                             background=True, origin=origin))

    threads = [threading.Thread(target=invoke) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert len(results) == 2
    assert len({item["task_id"] for item in results}) == 1
    assert sorted(item["run_created"] for item in results) == [False, True]
    assert len(list((tmp_path / "runs").iterdir())) == 1

    fresh = core.delegate_profile("reviewer", "same task", session_title="same", background=True,
                                  origin=origin, duplicate_policy="new")
    assert fresh["run_created"] is True
    assert fresh["task_id"] != results[0]["task_id"]
    assert len(list((tmp_path / "runs").iterdir())) == 2


def test_effective_policy_precedence_and_public_output(monkeypatch):
    monkeypatch.setattr(core, "_plugin_entry", lambda: {
        "allowed_profiles": ["reviewer"], "allowed_toolsets": ["file"],
        "max_async": 3, "duplicate_guard": {"enabled": False, "active_window_seconds": 90},
    })
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOWED_PROFILES", "builder")
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOWED_TOOLSETS", "")
    monkeypatch.setenv("PROFILE_DELEGATE_MAX_ASYNC", "4")
    policy = core.load_effective_policy()
    assert policy.values["allowed_profiles"] == ["builder"]
    assert policy.values["allowed_toolsets"] == []
    assert policy.values["max_async"] == 4
    assert policy.values["duplicate_guard_enabled"] is False
    assert policy.sources["allowed_profiles"] == "env"
    assert policy.sources["duplicate_guard_enabled"] == "yaml"
    public = core.profile_delegate_policy(policy)
    assert public["limits"]["max_async"] == 4
    assert public["execution_overrides"]["allowed_toolsets"] == []
    assert "secret" not in json.dumps(public).lower()


def test_malformed_policy_fails_before_artifact_creation(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setattr(core, "_plugin_entry", lambda: {"max_async": "broken"})
    with pytest.raises(core.ProfileDelegateError) as exc_info:
        core.delegate_profile("reviewer", "task", session_title="bad config")
    assert exc_info.value.code == "configuration_error"
    assert not (tmp_path / "runs").exists()


def test_detached_max_async_uses_persisted_policy(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    active = tmp_path / "runs" / "pd_20260719_000000_active1"
    active.mkdir(parents=True)
    core.json_safe_write(active / "status.json", {
        "status": "running", "background_worker_mode": "detached", "worker_pid": 123,
    })
    pending = tmp_path / "runs" / "pd_20260719_000001_pending1"
    pending.mkdir()
    core.json_safe_write(pending / "request.json", {"effective_policy": {"limits": {"max_async": 1}}})
    monkeypatch.setattr(core, "probe_worker_alive", lambda pid: True)
    with pytest.raises(core.ProfileDelegateError) as exc_info:
        core._start_detached_background_worker(pending)
    assert exc_info.value.code == "async_concurrency_limit"


def test_identical_concurrent_sync_requests_create_one_run(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("PROFILE_DELEGATE_LOCKS_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("PROFILE_DELEGATE_ALLOW_ALL_PROFILES", "true")
    monkeypatch.setattr(core, "validate_profile", lambda p, policy=None: core.ValidatedProfile(p, p, str(tmp_path / p)))
    monkeypatch.setattr(core, "resolve_workdir", lambda workdir="", policy=None: tmp_path)
    monkeypatch.setattr(core, "resolve_hermes_bin", lambda: "/usr/bin/hermes")
    entered = threading.Event()
    release = threading.Event()

    def fake_execute(run_dir):
        entered.set()
        release.wait(timeout=5)
        return {"success": True, "mode": "sync", "task_id": run_dir.name, "status": "completed",
                "paths": core.base_paths(run_dir)}

    monkeypatch.setattr(core, "_execute_delegate_run", fake_execute)
    results = []
    first = threading.Thread(target=lambda: results.append(core.delegate_profile(
        "reviewer", "same task", session_title="same", origin={"session_id": "sync-origin"})))
    first.start()
    assert entered.wait(timeout=5)
    second = threading.Thread(target=lambda: results.append(core.delegate_profile(
        "reviewer", "same task", session_title="same", origin={"session_id": "sync-origin"})))
    second.start()
    second.join(timeout=5)
    release.set()
    first.join(timeout=5)
    assert len(results) == 2
    assert len({item["task_id"] for item in results}) == 1
    assert len(list((tmp_path / "runs").iterdir())) == 1


def test_terminal_owned_fields_resist_stale_snapshot_but_notification_merges(tmp_path):
    run_dir = tmp_path / "pd_20260721_120000_aaaaaa"
    run_dir.mkdir()
    core.json_safe_write(run_dir / "status.json", {"task_id": run_dir.name, "status": "running"})
    core.merge_run_status(run_dir, {
        "status": "completed", "phase": "completed", "ended_at": "terminal",
        "error_code": None, "exit_code": 0, "timed_out": False,
        "child_session_id": "terminal-child", "transport_alive": False,
        "transport_pid": 99,
    }, terminal=True)
    stale = core.merge_run_status(run_dir, {
        "status": "cancelling", "phase": "interrupting", "ended_at": "stale",
        "error_code": "stale", "exit_code": 9, "timed_out": True,
        "child_session_id": "stale-child", "transport_alive": True,
        "transport_pid": 100, "event_seq": 8, "notification_status": "queued",
    })
    assert stale["status"] == "completed"
    assert stale["phase"] == "completed" and stale["ended_at"] == "terminal"
    assert stale["error_code"] is None and stale["exit_code"] == 0 and stale["timed_out"] is False
    assert stale["child_session_id"] == "terminal-child"
    assert stale["transport_alive"] is False and stale["transport_pid"] == 99
    assert stale["event_seq"] == 8 and stale["notification_status"] == "queued"


def test_locked_field_merges_prevent_deterministic_lost_update(tmp_path):
    run_dir = tmp_path / "pd_20260721_120001_bbbbbb"
    run_dir.mkdir()
    core.json_safe_write(run_dir / "status.json", {"task_id": run_dir.name, "status": "running"})
    stale_parent = core.read_json_file(run_dir / "status.json")
    core.merge_run_status(run_dir, {"phase": "model_running", "event_seq": 5, "tool_calls": 2})
    stale_parent.update({"worker_pid": 123, "notification_status": "pending"})
    core.merge_run_status(run_dir, {"worker_pid": stale_parent["worker_pid"], "notification_status": stale_parent["notification_status"]})
    core.merge_run_status(run_dir, {"last_control": {"state": "accepted"}})
    core.merge_run_status(run_dir, {"status": "completed", "phase": "completed", "ended_at": "now"}, terminal=True)
    core.merge_run_status(run_dir, {"notification_status": "queued", "notified_at": "later"})
    final = core.read_json_file(run_dir / "status.json")
    assert final["worker_pid"] == 123 and final["event_seq"] == 5 and final["tool_calls"] == 2
    assert final["last_control"]["state"] == "accepted"
    assert final["status"] == "completed" and final["notification_status"] == "queued"


def test_required_status_merge_lock_failure_propagates_optional_enrichment_is_best_effort(tmp_path, monkeypatch):
    run_dir = tmp_path / "pd_20260721_120002_cccccc"
    run_dir.mkdir()
    core.json_safe_write(run_dir / "status.json", {"task_id": run_dir.name, "status": "running"})
    real_open = core.os.open
    def fail_lock(path, *args, **kwargs):
        if str(path).endswith("status.lock"):
            raise OSError("lock unavailable")
        return real_open(path, *args, **kwargs)
    monkeypatch.setattr(core.os, "open", fail_lock)
    with pytest.raises(OSError, match="lock unavailable"):
        core.merge_run_status(run_dir, {"status": "failed", "ended_at": "now"}, terminal=True)
    assert core.merge_run_status_best_effort(run_dir, {"event_seq": 3}) is False
    assert core.read_json_file(run_dir / "status.json")["status"] == "running"


def test_no_post_creation_direct_status_writes_remain():
    core_source = Path(core.__file__).read_text(encoding="utf-8")
    runner_source = Path(core.__file__).with_name("tui_runner.py").read_text(encoding="utf-8")
    assert core_source.count('json_safe_write(run_dir / "status.json"') == 2
    assert 'json_safe_write(run_dir / "status.json"' not in runner_source
