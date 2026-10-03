"""Risk-focused regressions for the in-progress steer-first remediation."""

import pytest
import argparse
import json

import core
import cli
import tui_runner
import importlib.util
from pathlib import Path


ORIGIN = {"ui_session_id": "ui-owned", "session_id": "sid-owned", "session_key": "lane"}


def test_child_environment_scrubs_caller_execution_overlays(monkeypatch):
    for key in ("HERMES_TUI_TOOLSETS", "HERMES_TUI_SKILLS", "HERMES_TUI_MAX_TURNS",
                "HERMES_MODEL", "HERMES_PROVIDER", "HERMES_MANAGED_DIR", "HERMES_MAX_ITERATIONS"):
        monkeypatch.setenv(key, "HOSTILE")
    monkeypatch.setenv("OPENAI_API_KEY", "credential-not-to-persist")
    monkeypatch.setenv("CUSTOM_1_API_KEY", "provider-credential")
    monkeypatch.setenv("SPARTAN_REASONING_BINDING_SECRET", "realm-binding")
    monkeypatch.setenv("SPARTAN_REASONING_REALM", "realm-name")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy")
    child = core.child_environment(0)
    assert all("HOSTILE" not in str(value) for value in child.values())
    assert child["OPENAI_API_KEY"] == "credential-not-to-persist"
    assert child["CUSTOM_1_API_KEY"] == "provider-credential"
    assert child["SPARTAN_REASONING_BINDING_SECRET"] == "realm-binding"
    assert child["SPARTAN_REASONING_REALM"] == "realm-name"
    assert child["HTTPS_PROXY"] == "http://proxy"
    tui = tui_runner._environment({"profile_home": "/tmp/target", "effective_execution": {}},
                                   __import__("pathlib").Path("/tmp/run"))
    assert tui["HERMES_HOME"] == "/tmp/target"
    assert "HERMES_TUI_TOOLSETS" not in tui

def test_operator_approval_policy_not_model_request(monkeypatch):
    monkeypatch.setattr(core, "_plugin_entry", lambda: {
        "allow_child_approval_override": True, "child_approval_mode": "approve_yolo",
    })
    policy = core.load_effective_policy()
    assert policy.values["child_approval_mode"] == "yolo"
    assert policy.values["allow_child_approval_override"] is True


def test_strict_origin_rejects_legacy_and_weaker_key_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path))
    run = tmp_path / "pd_20260927_000000_abcdef"
    run.mkdir()
    core.json_safe_write(run / "status.json", {"task_id": run.name, "status": "completed"})
    with pytest.raises(core.ProfileDelegateError, match="originating"):
        core.profile_delegate_status(run.name, caller_origin=ORIGIN)
    assert core._read_run_status(run.name, operator=True)["lookup_success"] is True
    core.json_safe_write(run / "status.json", {"task_id": run.name, "status": "completed", "origin": ORIGIN})
    assert core.profile_delegate_status(run.name, caller_origin=ORIGIN)["lookup_success"] is True
    with pytest.raises(core.ProfileDelegateError, match="originating"):
        core.profile_delegate_status(run.name, caller_origin={**ORIGIN, "ui_session_id": "wrong"})
    with pytest.raises(core.ProfileDelegateError, match="restricted"):
        core.profile_delegate_list(scope="all", caller_origin=ORIGIN)

def test_model_callable_surfaces_cannot_request_operator_bypass(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path))
    run = tmp_path / "pd_20260927_000000_abcdef"
    run.mkdir()
    core.json_safe_write(run / "status.json", {"task_id": run.name, "status": "completed"})
    with pytest.raises(TypeError):
        core.profile_delegate_status(run.name, operator=True)
    with pytest.raises(TypeError):
        core.profile_delegate_list(operator=True)
    assert not hasattr(core, "profile_delegate_reconcile")
    assert not hasattr(core, "profile_delegate_prune")
    spec = importlib.util.spec_from_file_location("profile_delegate_plugin_boundary", Path(__file__).with_name("__init__.py"))
    assert spec is not None and spec.loader is not None
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    monkeypatch.setattr(plugin, "_current_origin", lambda: ORIGIN)
    for handler, args in ((plugin._status_handler, {"task_id": run.name}),
                          (plugin._list_handler, {"scope": "all"}),
                          (plugin._reconcile_handler, {"task_id": run.name}),
                          (plugin._prune_handler, {"dry_run": False})):
        response = json.loads(handler({**args, "operator": True}))
        assert response["success"] is False
    calls = []
    class Context:
        def register_cli_command(self, **kwargs):
            pass
        def register_tool(self, **kwargs):
            calls.append(kwargs["name"])
    plugin.register(Context())
    assert "profile_delegate_reconcile" not in calls
    assert "profile_delegate_prune" not in calls


def test_task_selection_requires_explicit_caller_grant(monkeypatch):
    monkeypatch.setattr(core, "_plugin_entry", lambda: {"allow_child_approval_override": False})
    policy = core.load_effective_policy()
    requested = core.normalize_requested_execution(policy=policy, validate_policy=False)
    with pytest.raises(core.PreflightError) as error:
        core.validate_preflight(requested, policy, reasoning_mode="inherit", capability_preset="build",
                                target_profile="reviewer", child_approval_explicit=True)
    assert "child_approval_mode" in error.value.details["unsupported_fields"]


def test_transport_validation_before_config_import(monkeypatch):
    monkeypatch.setattr(core, "load_effective_policy", lambda: pytest.fail("config imported"))
    with pytest.raises(core.ProfileDelegateError) as error:
        core.delegate_profile("reviewer", "task", transport_mode="unknown")
    assert error.value.code == "validation_error"
    with pytest.raises(core.ProfileDelegateError) as error:
        core.delegate_profile("reviewer", "")
    assert error.value.code == "validation_error"


def test_dispatch_scans_foreign_stale_run_without_reconciliation(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_DELEGATE_RUNS_ROOT", str(tmp_path))
    foreign = tmp_path / "pd_20260927_000000_abcdef"
    own = tmp_path / "pd_20260927_000001_abcdef"
    foreign.mkdir()
    own.mkdir()
    stale = {"task_id": foreign.name, "status": "running", "background_worker_mode": "detached",
             "worker_pid": -1, "origin": {"session_id": "foreign"},
             "request_fingerprint": "same", "created_at": core.now_iso()}
    core.json_safe_write(foreign / "status.json", stale)
    core.json_safe_write(own / "request.json", {"effective_policy": {"limits": {"max_async": 1}}})
    core.json_safe_write(own / "status.json", {"task_id": own.name, "status": "running"})
    monkeypatch.setattr(core, "probe_worker_alive", lambda pid: False)
    monkeypatch.setattr(core, "_operator_reconcile", lambda task_id: pytest.fail("foreign run mutated"))
    monkeypatch.setattr(core.subprocess, "Popen", lambda *a, **kw: type("Worker", (), {"pid": 100})())
    monkeypatch.setattr(core, "merge_run_status", lambda *a, **kw: None)
    assert core._active_matching_run("same", 120) is None
    core._start_detached_background_worker(own)
    assert core.read_json_file(foreign / "status.json") == stale
    assert not (foreign / "result.json").exists()


def test_provider_realm_conflict_is_actionable_and_non_retryable():
    diagnostic = "HTTP 409: Reasoning chain belongs to a different provider realm; start a new session or branch"
    assert core.provider_realm_mismatch(diagnostic, "")
    assert core.classify_transient_failure(exit_code=1, timed_out=False, stdout=diagnostic,
                                            stderr="", parsed_result=None) is None
    assert not core.provider_realm_mismatch("HTTP 409: unrelated conflict", "")


def test_operator_cli_dispatch_legacy_oversize_and_symlink(tmp_path, monkeypatch, capsys):
    root = tmp_path / "runs"
    root.mkdir(mode=0o700)
    run = root / "pd_20260927_000000_abcdef"
    run.mkdir(mode=0o700)
    core.json_safe_write(run / "status.json", {"task_id": run.name, "status": "completed"})
    parser = argparse.ArgumentParser()
    cli.register_cli(parser)
    def invoke(*args):
        with pytest.raises(SystemExit) as exc:
            cli.profile_delegate_cli(parser.parse_args(list(args) + ["--runs-root", str(root)]))
        return exc.value.code, capsys.readouterr()
    code, output = invoke("operator-status", run.name)
    assert code == 0 and json.loads(output.out)["lookup_success"]
    code, output = invoke("operator-list")
    assert code == 0 and json.loads(output.out)["count"] == 1
    code, output = invoke("operator-reconcile", run.name)
    assert code == 0 and json.loads(output.out)["reason"] == "already_terminal"
    (run / "stdout.txt").write_bytes(b"x" * 2_000_000 + b"END")
    code, output = invoke("operator-status", run.name)
    assert code == 0 and json.loads(output.out)["stdout_tail"].endswith("END")
    assert len(json.loads(output.out)["stdout_tail"]) <= 4000
    (run / "stdout.txt").unlink()
    (run / "stdout.txt").symlink_to(tmp_path / "outside")
    code, _ = invoke("operator-status", run.name)
    assert code == 3
    (run / "stdout.txt").unlink()
    (run / "result.json").write_bytes(b" " * 1_048_577)
    code, _ = invoke("operator-status", run.name)
    assert code == 3
    (run / "result.json").unlink()
    (run / "result.json").symlink_to(tmp_path / "outside")
    code, _ = invoke("operator-status", run.name)
    assert code == 3
    (run / "result.json").unlink()
    (run / "status.json").write_bytes(b" " * 1_048_577)
    code, output = invoke("operator-list")
    assert code == 0 and json.loads(output.out)["runs"][0]["status"] == "corrupt"
    code, _ = invoke("operator-reconcile", run.name)
    assert code == 3
    alias = root / "pd_20260927_000002_abcdef"
    alias.symlink_to(run, target_is_directory=True)
    code, output = invoke("operator-list")
    assert code == 0 and json.loads(output.out)["count"] == 1
    code, _ = invoke("operator-status", alias.name)
    assert code == 3


@pytest.mark.parametrize("artifact", ["command", "ack"])
@pytest.mark.parametrize("hazard", ["oversize", "symlink"])
def test_operator_reconcile_rejects_unsafe_cancel_evidence(tmp_path, monkeypatch, capsys, artifact, hazard):
    root = tmp_path / "runs"
    root.mkdir(mode=0o700)
    run = root / "pd_20260927_000003_abcdef"
    run.mkdir(mode=0o700)
    status = {"task_id": run.name, "status": "running", "background_worker_mode": "detached",
              "worker_pid": 113903}
    core.json_safe_write(run / "status.json", status)
    command = run / "control" / "commands" / "000000000001-deadbeef.json"
    ack = run / "control" / "acks" / command.name
    core.json_safe_write(command, {"type": "cancel", "command_id": "deadbeef", "seq": 1})
    core.json_safe_write(ack, {"type": "cancel", "command_id": "deadbeef", "seq": 1,
                               "state": "accepted"})
    target = command if artifact == "command" else ack
    outside = tmp_path / "outside.json"
    outside.write_text('{"type":"cancel","command_id":"deadbeef","seq":1,"state":"accepted"}')
    target.unlink()
    if hazard == "symlink":
        target.symlink_to(outside)
    else:
        target.write_bytes(b" " * 1_048_577)
    monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: False)
    parser = argparse.ArgumentParser()
    cli.register_cli(parser)
    with pytest.raises(SystemExit) as exc:
        cli.profile_delegate_cli(parser.parse_args(["operator-reconcile", run.name,
                                                    "--runs-root", str(root)]))
    assert exc.value.code == 3
    assert json.loads((run / "status.json").read_text()) == status
    assert not (run / "result.json").exists()
    assert outside.read_text().startswith('{"type":"cancel"')


def test_operator_reconcile_rejects_unbounded_control_directory(tmp_path, monkeypatch):
    root = tmp_path / "runs"
    root.mkdir(mode=0o700)
    run = root / "pd_20260927_000004_abcdef"
    run.mkdir(mode=0o700)
    core.json_safe_write(run / "status.json", {"task_id": run.name, "status": "running",
                                               "background_worker_mode": "detached", "worker_pid": 113903})
    commands = run / "control" / "commands"
    commands.mkdir(parents=True)
    for index in range(130):
        (commands / f"{index:012d}-deadbeef.json").write_text("{}")
    monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: False)
    parser = argparse.ArgumentParser()
    cli.register_cli(parser)
    with pytest.raises(SystemExit) as exc:
        cli.profile_delegate_cli(parser.parse_args(["operator-reconcile", run.name,
                                                    "--runs-root", str(root)]))
    assert exc.value.code == 3
    assert json.loads((run / "status.json").read_text())["status"] == "running"
    assert not (run / "result.json").exists()


@pytest.mark.parametrize("artifact", ["status", "result"])
@pytest.mark.parametrize("hazard", ["symlink", "oversize"])
def test_operator_reconcile_rejects_artifact_changed_after_preflight(
    tmp_path, monkeypatch, capsys, artifact, hazard,
):
    root = tmp_path / "runs"
    root.mkdir(mode=0o700)
    run = root / "pd_20260927_000005_abcdef"
    run.mkdir(mode=0o700)
    status = {"task_id": run.name, "status": "running", "background_worker_mode": "detached",
              "worker_pid": 113903}
    core.json_safe_write(run / "status.json", status)
    original_result = {"status": "ok", "execution_status": "completed", "contract_status": "valid",
                       "summary": "done", "artifacts": [], "errors": [], "next_steps": []}
    core.write_result_artifact(run, original_result)
    target = run / f"{artifact}.json"
    before_status = (run / "status.json").read_bytes()
    before_result = (run / "result.json").read_bytes()
    outside = tmp_path / "outside.json"
    outside.write_text('{"status":"completed"}', encoding="utf-8")

    def replace_artifact():
        target.unlink()
        if hazard == "symlink":
            target.symlink_to(outside)
        else:
            target.write_bytes(b" " * 1_048_577)

    if artifact == "status":
        original_read = core.operator_read_json
        reads = 0

        def changed_before_second_status_read(path, *args, **kwargs):
            nonlocal reads
            if path == target:
                reads += 1
                if reads == 2:
                    replace_artifact()  # The first bounded read passed already.
            return original_read(path, *args, **kwargs)

        monkeypatch.setattr(core, "operator_read_json", changed_before_second_status_read)
    else:
        monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: (replace_artifact(), False)[1])

    parser = argparse.ArgumentParser()
    cli.register_cli(parser)
    with pytest.raises(SystemExit) as exc:
        cli.profile_delegate_cli(parser.parse_args(["operator-reconcile", run.name,
                                                    "--runs-root", str(root)]))
    assert exc.value.code == 3
    assert (run / ("result.json" if artifact == "status" else "status.json")).read_bytes() == (
        before_result if artifact == "status" else before_status
    )
    assert outside.read_text() == '{"status":"completed"}'
    if hazard == "symlink":
        assert target.is_symlink()
    else:
        assert target.stat().st_size == 1_048_577
    assert f"{artifact}.json" in capsys.readouterr().err


def test_operator_cli_reconciles_normal_dead_worker(tmp_path, monkeypatch, capsys):
    root = tmp_path / "runs"
    root.mkdir(mode=0o700)
    run = root / "pd_20260927_000006_abcdef"
    run.mkdir(mode=0o700)
    core.json_safe_write(run / "status.json", {
        "task_id": run.name, "status": "running", "background_worker_mode": "detached",
        "worker_pid": 113903,
    })
    monkeypatch.setattr(core, "probe_worker_alive", lambda _pid: False)
    parser = argparse.ArgumentParser()
    cli.register_cli(parser)
    with pytest.raises(SystemExit) as exc:
        cli.profile_delegate_cli(parser.parse_args(["operator-reconcile", run.name,
                                                    "--runs-root", str(root)]))
    assert exc.value.code == 0
    diagnosis = json.loads(capsys.readouterr().out)
    assert diagnosis["reason"] == "worker_died"
    assert diagnosis["reconciled"] is True
    assert core.operator_read_json(run / "status.json")["status"] == "failed"
    assert core.operator_read_json(run / "result.json")["execution_status"] == "failed"
