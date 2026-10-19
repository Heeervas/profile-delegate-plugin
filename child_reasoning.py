"""Child-only reasoning selection; administrator scopes and files remain unchanged."""
from __future__ import annotations

import ast
import copy
import functools
import importlib
import inspect
import os
import stat
from pathlib import Path

if __package__:
    from .contracts import ProfileDelegateError
else:
    from contracts import ProfileDelegateError

EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")


def _read_managed_agent(scope: Path) -> dict:
    if scope.is_symlink() or not scope.is_dir():
        raise ValueError("invalid managed directory")
    try:
        fd = os.open(scope / "config.yaml", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return {}
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1_048_576:
            raise ValueError("invalid managed file")
        import yaml

        class UniqueLoader(yaml.SafeLoader):
            def construct_mapping(self, node, deep=False):
                keys = [self.construct_object(key, deep=deep) for key, _ in node.value]
                if len(set(keys)) != len(keys):
                    raise ValueError("duplicate managed key")
                return super().construct_mapping(node, deep=deep)

        raw = handle.read(1_048_577)
        if len(raw) > 1_048_576:
            raise ValueError("oversized managed file")
        document = yaml.load(raw, Loader=UniqueLoader)
    document = {} if document is None else document
    if not isinstance(document, dict) or not isinstance(document.get("agent", {}), dict):
        raise ValueError("invalid managed mapping")
    return document.get("agent", {})


def managed_blocker(scope: Path | None) -> str | None:
    """Reject unreadable policy and administrator-pinned reasoning, not unrelated settings."""
    if scope is None:
        return None
    try:
        agent = _read_managed_agent(scope)
        if "reasoning_effort" in agent or agent.get("reasoning_overrides"):
            return "administrator-managed reasoning settings require inheritance"
        if "reasoning_overrides" in agent and not isinstance(agent["reasoning_overrides"], dict):
            raise ValueError("invalid managed reasoning overrides")
    except Exception:
        # YAML/file/parser failures must not expose managed contents or permit an override.
        return "administrator-managed configuration is unreadable or invalid"
    return None


@functools.lru_cache(maxsize=4)
def _check_interfaces(paths_and_signatures: tuple) -> bool:
    requirements = (("_resolve_cli_reasoning", {"cli"}), ("_make_agent", {"sid", "key", "reasoning_config_override", "platform_override"}))
    for (path, _signature), (name, required) in zip(paths_and_signatures, requirements):
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == name)
        names = {item.arg for item in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)}
        if not required <= names:
            return False
    return True


def compatibility_blocker() -> str | None:
    """Inspect interfaces without importing CLI/TUI and starting plugin discovery."""
    try:
        constants = importlib.import_module("hermes_constants")
        root = Path(constants.__file__).resolve().parent
        paths = (root / "hermes_cli/cli_model_switch_mixin.py", root / "tui_gateway/server.py")
        signatures = tuple((str(path), (path.stat().st_mtime_ns, path.stat().st_size)) for path in paths)
        if callable(constants.parse_reasoning_effort) and _check_interfaces(signatures):
            return None
    except (ImportError, AttributeError, OSError, ValueError, SyntaxError, StopIteration, TypeError):
        pass
    return "installed Hermes reasoning interfaces are incompatible with the child adapter"


def require_available(scope: Path | None) -> None:
    blocker = managed_blocker(scope) or compatibility_blocker()
    if blocker:
        raise ProfileDelegateError(blocker + "; omit reasoning_effort to inherit", "reasoning_override_unavailable")


def _cli_adapter(original, in_scope, selected):
    @functools.wraps(original)
    def resolve(cli):
        result = original(cli)
        if in_scope():
            cli.reasoning_config = copy.deepcopy(selected)
            cli._explicit_reasoning_config = copy.deepcopy(selected)
        return result

    return resolve


def _tui_adapter(original, in_scope, selected):
    signature = inspect.signature(original)
    @functools.wraps(original)
    def make_agent(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        owned = in_scope() and bound.arguments.get("platform_override") == "profile-delegate"
        if owned:
            bound.arguments["reasoning_config_override"] = copy.deepcopy(selected)
        agent = original(*bound.args, **bound.kwargs)
        if owned and agent.reasoning_config != selected:
            raise ProfileDelegateError("Hermes did not retain the requested reasoning effort", "reasoning_override_unavailable")
        return agent

    return make_agent


def install(request: dict, *, tui: bool = False) -> bool:
    """Bind only this task/profile before the child starts any inference."""
    execution = request.get("effective_execution") or request.get("requested_execution") or {}
    effort = execution.get("reasoning_effort")
    if effort is None or effort == "":
        return False
    if effort not in EFFORTS or not request.get("profile_home"):
        raise ProfileDelegateError("invalid child reasoning selection", "reasoning_override_unavailable")
    scope_value = os.environ.get("HERMES_MANAGED_DIR", "").strip()
    scope = Path(scope_value) if scope_value else (Path("/etc/hermes") if Path("/etc/hermes").exists() else None)
    require_available(scope)
    from hermes_constants import get_hermes_home, parse_reasoning_effort

    target = Path(request["profile_home"]).resolve()
    selected = parse_reasoning_effort(effort)
    if selected is None:
        raise ProfileDelegateError("Hermes cannot parse the requested reasoning effort", "reasoning_override_unavailable")
    module_name, name, factory = {
        False: ("hermes_cli.cli_model_switch_mixin", "_resolve_cli_reasoning", _cli_adapter),
        True: ("tui_gateway.server", "_make_agent", _tui_adapter),
    }[tui]
    module = importlib.import_module(module_name)
    original = getattr(module, name)
    marker = (str(target), effort)
    installed = getattr(original, "_profile_delegate_reasoning", None)
    if installed is not None:
        if installed != marker:
            raise ProfileDelegateError("child reasoning adapter is already bound to another task", "reasoning_override_unavailable")
        return True
    signature = inspect.signature(original)
    try:
        signature.bind("ui", "child", reasoning_config_override=selected, platform_override="profile-delegate") if tui else signature.bind(object())
    except (TypeError, ValueError) as exc:
        raise ProfileDelegateError("Hermes reasoning interface changed", "reasoning_override_unavailable") from exc

    def in_scope():
        return Path(get_hermes_home()).resolve() == target

    adapter = factory(original, in_scope, selected)
    adapter._profile_delegate_reasoning = marker
    setattr(module, name, adapter)
    return True
