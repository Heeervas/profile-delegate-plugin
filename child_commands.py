"""Bounded child session commands; never interpret commands as model prompts."""
from __future__ import annotations

import ast
import functools
import importlib
import inspect
import os
import time
from pathlib import Path


def _core():
    return importlib.import_module('.core', __package__) if __package__ else importlib.import_module('core')


def parse(command):
    if not isinstance(command, str) or len(command) > 64:
        raise _core().ProfileDelegateError('command must be /fast fast or /fast normal', 'command_unsupported')
    parts = command.split()
    if len(parts) != 2 or parts[0] != '/fast' or parts[1] not in {'fast', 'normal'}:
        raise _core().ProfileDelegateError('supported commands: /fast fast, /fast normal; session scope only', 'command_unsupported')
    return parts[1]


def normalize(commands):
    if commands is None:
        return []
    if not isinstance(commands, list) or len(commands) > 8:
        raise _core().ProfileDelegateError('commands must be an array of at most 8 commands', 'validation_error')
    return ['/fast ' + parse(command) for command in commands]


def require_policy(policy, scope=None):
    c = _core()
    if not policy.values.get('allow_fast_override', False):
        raise c.ProfileDelegateError('caller policy disables fast overrides', 'command_not_allowed')
    scope = c.discover_managed_scope(os.environ) if scope is None else scope
    if scope is not None:
        try:
            agent = c.child_reasoning._read_managed_agent(scope)
        except Exception as exc:
            raise c.ProfileDelegateError('administrator configuration is unreadable or invalid', 'command_not_allowed') from exc
        if 'service_tier' in agent:
            raise c.ProfileDelegateError('administrator-managed service tier requires inheritance', 'command_not_allowed')


def require_runtime():
    """Admission checks signatures without importing the CLI or starting discovery."""
    try:
        import hermes_constants
        root = Path(hermes_constants.__file__).resolve().parent
        cli = ast.parse((root / 'hermes_cli/cli_agent_setup_mixin.py').read_text())
        tui = ast.parse((root / 'tui_gateway/server.py').read_text())
        cls = next(n for n in cli.body if isinstance(n, ast.ClassDef) and n.name == 'CLIAgentSetupMixin')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_resolve_turn_agent_config')
        factory = next(n for n in tui.body if isinstance(n, ast.FunctionDef) and n.name == '_make_agent')
        names = {n.arg for n in (*factory.args.args, *factory.args.kwonlyargs)}
        if [n.arg for n in method.args.args] == ['self', 'user_message'] and {'sid', 'platform_override', 'service_tier_override'} <= names:
            return
    except (ImportError, OSError, SyntaxError, StopIteration):
        pass
    raise _core().ProfileDelegateError('installed Hermes child command interfaces are incompatible', 'command_unavailable')


def apply_agent(agent, mode):
    """Use the resolved route, preserving all unrelated native request overrides."""
    from hermes_cli.models import resolve_fast_mode_overrides
    overrides = None
    if mode == 'fast':
        overrides = resolve_fast_mode_overrides(agent.model, provider=agent.provider, base_url=agent.base_url, tier='priority')
        if overrides is None:
            raise _core().ProfileDelegateError('fast mode is unavailable for the resolved child route', 'command_unavailable')
    agent.service_tier = 'priority' if mode == 'fast' else None
    existing = getattr(agent, 'request_overrides', None) or {}
    agent.request_overrides = {**{k: v for k, v in existing.items() if k not in {'service_tier', 'speed'}}, **(overrides or {})}


def install(request, *, tui=False):
    commands = normalize(request.get('commands'))
    if not commands and not (tui and request.get('command_policy') is True):
        return False
    c = _core()
    try:
        require_runtime()
        require_policy(c.EffectivePolicy({'allow_fast_override': request.get('command_policy') is True}, {}))
    except c.ProfileDelegateError:
        if commands:
            raise
        return False  # Inheritance remains usable when optional command support is unavailable.
    mode = parse(commands[-1]) if commands else None
    target = Path(request['profile_home']).resolve()
    from hermes_constants import get_hermes_home
    if tui:
        module = importlib.import_module('tui_gateway.server')
        name = '_make_agent'
        adapter = _tui_adapter(module, target, mode, get_hermes_home)
        from run_agent import AIAgent
        wire = AIAgent._build_api_kwargs
        if not callable(wire) or getattr(wire, '_profile_delegate_commands', False):
            raise c.ProfileDelegateError('child command request interface unavailable or already bound', 'command_unavailable')
        AIAgent._build_api_kwargs = _wire_adapter(wire)
    else:
        module = importlib.import_module('hermes_cli.cli_agent_setup_mixin').CLIAgentSetupMixin
        name = '_resolve_turn_agent_config'
        adapter = _cli_adapter(module, target, mode, get_hermes_home)
    original = getattr(module, name)
    if getattr(original, '_profile_delegate_commands', None) is not None:
        raise c.ProfileDelegateError('child command adapter already installed', 'command_unavailable')
    adapter._profile_delegate_commands = (str(target), mode)
    setattr(module, name, adapter)
    return True


def _cli_adapter(cls, target, mode, get_home):
    original = cls._resolve_turn_agent_config
    @functools.wraps(original)
    def resolve(cli, user_message):
        owned = Path(get_home()).resolve() == target
        if owned:
            cli.service_tier = 'priority' if mode == 'fast' else None
        route = original(cli, user_message)
        if owned and mode == 'fast' and not route.get('request_overrides'):
            raise _core().ProfileDelegateError('fast mode is unavailable for the resolved child route', 'command_unavailable')
        return route
    return resolve


def _tui_adapter(module, target, mode, get_home):
    original = module._make_agent
    signature = inspect.signature(original)
    pinned = set()
    @functools.wraps(original)
    def make_agent(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        sid = bound.arguments.get('sid')
        owned = Path(get_home()).resolve() == target and (bound.arguments.get('platform_override') == 'profile-delegate' or sid in pinned)
        first = owned and sid not in pinned
        if first and mode is not None:
            bound.arguments['service_tier_override'] = 'priority' if mode == 'fast' else ''
        agent = original(*bound.args, **bound.kwargs)
        if owned:
            pinned.add(sid)
            # Eager resume constructs before _init_session registers the record.
            # Resolve that same record at request time, never a detached placeholder.
            session = functools.partial(_command_session, module, sid, mode)
            if sid in module._sessions:
                if first and mode is not None:
                    module._sessions[sid]['create_service_tier_override'] = 'priority' if mode == 'fast' else ''
                session()
            agent._profile_delegate_command_session = session
        return agent
    return make_agent


def _command_session(module, sid, mode):
    session = module._sessions.get(sid)
    if session is None:
        raise _core().ProfileDelegateError('child command session record unavailable', 'command_unavailable')
    if mode is not None and session.get('create_service_tier_override') is None:
        # Native create stores None for inheritance, not an applied live selection.
        # Live config.set stores priority or ""; neither may be overwritten here.
        session['create_service_tier_override'] = 'priority' if mode == 'fast' else ''
    return session


def _wire_adapter(original):
    """Validate the final selected route immediately before native request assembly.

    Cold resume can build the restored route before config.set selects the requested
    model. The session pin follows native live changes and survives agent rebuilds.
    """
    @functools.wraps(original)
    def build(agent, *args, **kwargs):
        session = getattr(agent, '_profile_delegate_command_session', None)
        if callable(session):
            session = session()
        if session is not None:
            tier = session.get('create_service_tier_override')
            if tier in {None, 'auto', 'cold', 'ultrafast'}:
                return original(agent, *args, **kwargs)
            if tier not in {'priority', ''}:
                raise _core().ProfileDelegateError('child command session tier unavailable', 'command_unavailable')
            apply_agent(agent, 'fast' if tier == 'priority' else 'normal')
        return original(agent, *args, **kwargs)
    build._profile_delegate_commands = True
    return build


def command(task_id, text, caller_origin=None):
    c = _core()
    mode = parse(text)
    run_dir = c.resolve_run_dir(task_id)
    status = c.read_json_file(run_dir / 'status.json')
    c.authorize_run('command', caller_origin, status)
    request = c.read_json_file(run_dir / 'request.json')
    if request.get('command_policy') is not True:
        raise c.ProfileDelegateError('run has no fast override grant; start a new run', 'command_not_allowed')
    require_policy(c.load_effective_policy())
    require_runtime()
    _, pending = c._write_control_command(run_dir, 'command', {'command': '/fast ' + mode}, caller_origin)
    ack = c._wait_control_ack(run_dir, pending)
    state = ack.get('state') if ack else 'pending'
    return dict(success=state == 'applied', task_id=run_dir.name, command_id=pending['command_id'],
                state=state, delivery_state='applied' if state == 'applied' else 'unknown' if state in {'pending', 'delivery_unknown'} else 'not_applied', ack=ack)


def apply_live(coordinator, path, pending):
    c = _core()
    if coordinator.terminal_event and coordinator.turn_settled:
        c._ack_control(coordinator.run_dir, path, pending, 'rejected', 'turn already settled')
        return
    if coordinator.request.get('command_policy') is not True:
        raise c.ProfileDelegateError('run has no fast override grant', 'command_not_allowed')
    require_policy(c.load_effective_policy())
    mode = parse((pending.get('payload') or {}).get('command'))
    remaining = coordinator.deadline - time.monotonic()
    if remaining <= 0:
        c._ack_control(coordinator.run_dir, path, pending, 'rejected', 'task deadline exhausted')
        return
    reply = coordinator.client.call('config.set', {'session_id': coordinator.ui_session_id, 'key': 'fast', 'value': mode, 'scope': 'session'},
                                    timeout=min(15, remaining), on_event=coordinator.persist_event, stage='session_command')
    if reply.get('value') != mode or reply.get('scope') == 'global' or reply.get('confirm_required'):
        c._ack_control(coordinator.run_dir, path, pending, 'delivery_unknown', 'native command effect unconfirmed')
        return
    c._ack_control(coordinator.run_dir, path, pending, 'applied', 'session fast mode applied; affects subsequent requests')
