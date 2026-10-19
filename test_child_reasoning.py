"""Reasoning overrides preserve administrator settings and native resume routing."""
import copy
import logging
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core

pytestmark = pytest.mark.integration


def test_browser_managed_scope_allows_reasoning_preflight(tmp_path, monkeypatch):
    managed = tmp_path / "managed"
    managed.mkdir()
    (managed / "config.yaml").write_text("browser: {cloud_provider: camofox}\n")
    monkeypatch.setenv("HERMES_MANAGED_DIR", str(managed))
    monkeypatch.setattr(core, "_plugin_entry", lambda: {"allow_reasoning_override": True})
    requested = core.normalize_requested_execution(reasoning_effort="high", validate_policy=False)
    core.validate_preflight(requested, core.load_effective_policy(), reasoning_mode="override",
                            capability_preset="build", target_profile="reviewer", child_approval_explicit=False)


def test_reasoning_child_preserves_managed_browser_environment(tmp_path, monkeypatch):
    managed = tmp_path / "managed"
    managed.mkdir()
    (managed / "config.yaml").write_text("browser: {cloud_provider: camofox}\n")
    values = {"HERMES_MANAGED_DIR": str(managed), "SPARTAN_BROWSER_POLICY_ENABLED": "1", "SPARTAN_HERMES_RUN_GID": "1000"}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    request = {"profile_home": str(tmp_path), "effective_execution": {"reasoning_effort": "high"}}
    for tui in (False, True):
        env = core.prepare_child_environment(request, tmp_path, tui=tui)
        assert {key: env.get(key) for key in values} == values
    assert not (tmp_path / "reasoning_config").exists()


@pytest.fixture
def adapter_context(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    import child_reasoning
    import hermes_constants
    from hermes_cli import cli_model_switch_mixin as cli_switch
    from tui_gateway import server

    monkeypatch.delenv("HERMES_MANAGED_DIR", raising=False)
    monkeypatch.setattr(child_reasoning, "require_available", lambda scope: None)
    home = [tmp_path]
    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: home[0])
    monkeypatch.setattr(cli_switch, "_resolve_cli_reasoning", cli_switch._resolve_cli_reasoning)
    monkeypatch.setattr(server, "_make_agent", server._make_agent)
    return child_reasoning, cli_switch, server, home


@pytest.mark.parametrize("effort", ["none", "minimal", "low", "medium", "high", "xhigh", "max"])
def test_cli_native_restore_retains_explicit_reasoning(effort, tmp_path, monkeypatch, adapter_context):
    adapter, cli_switch, _, home = adapter_context
    from hermes_constants import parse_reasoning_effort

    config = {"agent": {"reasoning_effort": "medium", "reasoning_overrides": {"fixture/resumed": "low"}}}
    cli = ModuleType("cli")
    cli.CLI_CONFIG = config
    cli.logger = logging.getLogger("reasoning-native-fixture")
    monkeypatch.setitem(sys.modules, "cli", cli)
    cli_obj = SimpleNamespace(model="fixture/start", provider="openai-api", agent=None,
                              _explicit_model_override=False, reasoning_config=parse_reasoning_effort(effort),
                              _explicit_reasoning_config=parse_reasoning_effort(effort), _console_print=lambda *_: None)
    row = {"model": "fixture/resumed", "model_config": {"gateway_runtime": {"provider": "openai-api"}}}
    cli_switch.CLIModelSwitchMixin._restore_session_model(cli_obj, row)
    assert cli_obj.reasoning_config == parse_reasoning_effort("low")
    request = {"profile_home": str(tmp_path), "effective_execution": {"reasoning_effort": effort}}
    assert adapter.install(request)
    installed = cli_switch._resolve_cli_reasoning
    assert adapter.install(request) and cli_switch._resolve_cli_reasoning is installed
    cli_obj.model = "fixture/start"
    cli_switch.CLIModelSwitchMixin._restore_session_model(cli_obj, row)
    assert cli_obj.reasoning_config == parse_reasoning_effort(effort)
    assert config == {"agent": {"reasoning_effort": "medium", "reasoning_overrides": {"fixture/resumed": "low"}}}
    home[0] = tmp_path / "other"
    cli_switch._resolve_cli_reasoning(cli_obj)
    assert cli_obj.reasoning_config == parse_reasoning_effort("low")


@pytest.mark.parametrize("effort", ["none", "minimal", "low", "medium", "high", "xhigh", "max"])
@pytest.mark.parametrize("stored_effort", [None, "low"])
def test_tui_adapter_preserves_native_deferred_route(effort, stored_effort, tmp_path, monkeypatch, adapter_context):
    adapter, _, server, home = adapter_context
    from hermes_constants import parse_reasoning_effort

    captured = []
    def constructor(sid, key, model_override=None, provider_override=None,
                    reasoning_config_override=None, platform_override=None, **kwargs):
        captured.append({"model": model_override, "provider": provider_override, "reasoning": reasoning_config_override})
        return SimpleNamespace(reasoning_config=reasoning_config_override)
    monkeypatch.setattr(server, "_make_agent", constructor)
    stored = {"model_override": {"model": "fixture/replacement"}, "provider_override": "openai-api"}
    if stored_effort:
        stored["reasoning_config_override"] = parse_reasoning_effort(stored_effort)
    current = {"resume_session_id": "child-proof", "resume_runtime_overrides": stored,
               "source": "profile-delegate", "cwd": str(tmp_path),
               "create_reasoning_override": parse_reasoning_effort(effort)}
    before = copy.deepcopy(current)
    kwargs = server._deferred_build_agent_kwargs(current, None)
    request = {"profile_home": str(tmp_path), "effective_execution": {"reasoning_effort": effort}}
    adapter.install(request, tui=True)
    result = server._make_agent("ui-proof", "child-proof", **kwargs)
    assert result.reasoning_config == parse_reasoning_effort(effort)
    assert captured[-1]["model"] == stored["model_override"]
    assert captured[-1]["provider"] == "openai-api"
    assert current == before
    # Other sources and other profiles retain the native supplied setting.
    server._make_agent("other", "other", reasoning_config_override={"effort": "low"}, platform_override="cli")
    assert captured[-1]["reasoning"] == {"effort": "low"}
    home[0] = tmp_path / "other"
    server._make_agent("other", "other", **kwargs)
    assert captured[-1]["reasoning"] == kwargs.get("reasoning_config_override")


@pytest.mark.parametrize("text", [
    "agent: {reasoning_effort: high}", "agent: {reasoning_effort: false}",
    "agent: {reasoning_overrides: {fixture: low}}", "agent: {reasoning_overrides: []}",
    "agent: []", "[invalid]", "agent: [", "agent: {}\nagent: {reasoning_effort: high}",
])
def test_managed_reasoning_and_invalid_policy_fail_closed(text, tmp_path):
    import child_reasoning
    managed = tmp_path / "managed"
    managed.mkdir()
    config = managed / "config.yaml"
    config.write_text(text)
    before = config.read_bytes()
    assert child_reasoning.managed_blocker(managed)
    assert config.read_bytes() == before


def test_managed_policy_links_missing_scope_and_overflow_fail_closed(tmp_path):
    import child_reasoning
    managed = tmp_path / "managed"
    managed.mkdir()
    config = managed / "config.yaml"
    config.symlink_to(tmp_path / "absent")
    assert child_reasoning.managed_blocker(managed)
    config.unlink()
    config.write_bytes(b" " * 1_048_577)
    assert child_reasoning.managed_blocker(managed)
    assert child_reasoning.managed_blocker(tmp_path / "missing")


def test_policy_explains_disabled_or_incompatible_reasoning(tmp_path, monkeypatch):
    import child_reasoning
    monkeypatch.setattr(core, "discover_managed_scope", lambda env: None)
    monkeypatch.setattr(core, "native_async_ledger_compatibility", lambda: {})
    monkeypatch.setattr(core, "_plugin_entry", lambda: {"allow_reasoning_override": False})
    policy = core.profile_delegate_policy()
    assert policy["reasoning_state"] == "inherit_only"
    assert policy["reasoning_blockers"] == ["caller policy disables reasoning overrides"]
    monkeypatch.setattr(core, "_plugin_entry", lambda: {"allow_reasoning_override": True})
    monkeypatch.setattr(child_reasoning, "compatibility_blocker", lambda: "runtime incompatible")
    requested = core.normalize_requested_execution(reasoning_effort="high", validate_policy=False)
    with pytest.raises(core.PreflightError, match="runtime incompatible") as exc:
        core.validate_preflight(requested, core.load_effective_policy(), reasoning_mode="override",
                                capability_preset="build", target_profile="reviewer", child_approval_explicit=False)
    assert exc.value.details["run_created"] is False
    assert exc.value.details["retry_patch"] == {"reasoning_mode": "inherit", "reasoning_effort": None}
    assert core.profile_delegate_policy()["reasoning_state"] == "inherit_only"


def test_inheritance_does_not_install_adapter(adapter_context):
    adapter, cli_switch, server, _ = adapter_context
    before = (cli_switch._resolve_cli_reasoning, server._make_agent)
    assert adapter.install({"effective_execution": {}}) is False
    assert before == (cli_switch._resolve_cli_reasoning, server._make_agent)


def test_incompatible_tui_signature_refuses_before_install(tmp_path, monkeypatch, adapter_context):
    adapter, _, server, _ = adapter_context
    def incompatible(sid, key):
        return None
    monkeypatch.setattr(server, "_make_agent", incompatible)
    with pytest.raises(core.ProfileDelegateError, match="interface changed"):
        adapter.install({"profile_home": str(tmp_path), "effective_execution": {"reasoning_effort": "high"}}, tui=True)
    assert server._make_agent is incompatible
