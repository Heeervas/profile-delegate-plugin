"""Resolved delegation domains and non-widening inherited request context.

Only the private bootstrap request supplies ancestry; model arguments do not.
"""
from pathlib import Path
import os
from typing import NoReturn

VERSION = 1
LIMITS = ('max_depth', 'max_concurrent', 'max_async')
ALLOWLISTS = ('allowed_toolsets', 'allowed_skills')


def _core():
    if __package__:
        from . import core
    else:
        import core
    return core


def refuse(message) -> NoReturn:
    raise _core().ProfileDelegateError(message, 'execution_context_invalid')


def inherited():
    """Validate markers against the actual private parent request before use."""
    c = _core()
    parent = os.getenv('PROFILE_DELEGATE_PARENT_TASK_ID', '')
    depth = c.current_depth()
    if not parent and depth == 0:
        return None
    path = os.getenv('PROFILE_DELEGATE_APPROVAL_REQUEST', '')
    if not parent or not path:
        refuse('nested delegation requires its private bootstrap request')
    request = c.operator_read_json(Path(path))
    ctx = request.get('execution_context')
    if not isinstance(ctx, dict) or ctx.get('version') != VERSION:
        refuse('nested execution context missing or unsupported')
    expected = (ctx.get('task_id') == parent == request.get('task_id')
                and ctx.get('depth') == depth - 1
                and ctx.get('target_home') == str(c.get_hermes_home_path())
                and ctx.get('root_task_id') == os.getenv('PROFILE_DELEGATE_ROOT_TASK_ID')
                and Path(path).resolve().parent == Path(ctx.get('runs_root', '')) / parent
                and Path(path).name in {'request.json', 'attempt_request.json'})
    if not expected:
        refuse('nested request identity/home/depth/root mismatch')
    validate_domains(ctx)
    validate_contents(ctx)
    return ctx


def validate_contents(ctx):
    ceiling, ancestors = ctx.get('ceilings'), ctx.get('ancestors')
    if not isinstance(ceiling, dict) or not isinstance(ancestors, list) or len(ancestors) > 21:
        refuse('malformed inherited ceilings/ancestors')
    for key in (*ALLOWLISTS, 'allowed_profiles', 'allowed_workdirs'):
        if not isinstance(ceiling.get(key), list) or any(not isinstance(v, str) for v in ceiling[key]):
            refuse('malformed inherited allowlist')
    validate_workdirs(ceiling.get('workdir_constraints'))
    for value in ancestors:
        if (not isinstance(value, dict) or not isinstance(value.get('home'), str)
                or not _core().valid_session_identity(value.get('session_id'))):
            refuse('malformed ancestor identity')


def validate_domains(ctx):
    for name in ('runs_root', 'locks_root'):
        value = ctx.get(name)
        if not isinstance(value, str) or str(Path(value).resolve()) != value:
            refuse('noncanonical execution domain')
        env = os.getenv('PROFILE_DELEGATE_' + name.upper())
        if env != value:
            refuse('nested execution domain conflicts with bootstrap')


def runs_root(request):
    ctx = request.get('execution_context')
    if ctx:
        return Path(ctx['runs_root'])
    return Path(request.get('runs_root') or (Path(request.get('profile_home', '')) / 'profile_delegate' / 'runs'))


def workdir_constraints(policy):
    return policy.values.get('workdir_constraints', [dict(
        roots=[str(Path(p).expanduser().resolve()) for p in policy.values['allowed_workdirs']],
        cwd=str(Path.cwd().resolve()))])


def validate_workdirs(constraints):
    if not isinstance(constraints, list) or not constraints or len(constraints) > 22:
        refuse('missing or excessive inherited workdir constraints')
    for rule in constraints:
        if (not isinstance(rule, dict) or not isinstance(rule.get('roots'), list)
                or any(not isinstance(p, str) or str(Path(p).resolve()) != p for p in rule['roots'])
                or not isinstance(rule.get('cwd'), str) or str(Path(rule['cwd']).resolve()) != rule['cwd']):
            refuse('malformed inherited workdir constraint')


def intersect(policy):
    """Keep local provenance; inherited constraints are never env overrides."""
    ctx = inherited()
    if ctx is None:
        return policy
    values = dict(policy.values)
    ceiling = ctx['ceilings']
    for key in LIMITS:
        bound = ceiling.get(key)
        if type(bound) is not int or bound < 0:
            refuse('invalid inherited limit')
        values[key] = min(values[key], bound)
    for key in ALLOWLISTS:
        values[key] = [v for v in values[key] if v in ceiling[key]]
    for key in ('allow_model_override', 'allow_provider_override', 'allow_reasoning_override', 'allow_child_approval_override'):
        if type(ceiling.get(key)) is not bool:
            refuse('malformed inherited override grant')
        values[key] = values[key] and ceiling[key]
    grant = ceiling.get('allow_fast_override', False)
    if type(grant) is not bool:
        refuse('malformed inherited fast override grant')
    values['allow_fast_override'] = values['allow_fast_override'] and grant
    if not ceiling['allow_all_profiles']:
        allowed = ceiling['allowed_profiles']
        values['allowed_profiles'] = allowed[:] if values['allow_all_profiles'] else [v for v in values['allowed_profiles'] if v in allowed]
        values['allow_all_profiles'] = False
    validate_workdirs(ceiling.get('workdir_constraints'))
    values['workdir_constraints'] = workdir_constraints(policy) + ceiling['workdir_constraints']
    return type(policy)(values, dict(policy.sources))


def resolve(request, policy):
    c = _core()
    prior = inherited()
    ancestors = list(prior['ancestors']) if prior else []
    origin = request['origin']
    sid = origin.get('session_id') or origin.get('session_key')
    if prior and not c.valid_session_identity(sid):
        refuse('nested caller requires an exact native session identity')
    if sid:
        ancestors.append({'home': str(c.get_hermes_home_path()), 'session_id': sid})
    if len(ancestors) > 21:
        refuse('ancestor evidence exceeds depth bound')
    keys = (*LIMITS, *ALLOWLISTS, 'allowed_profiles', 'allow_all_profiles', 'allowed_workdirs',
            'allow_model_override', 'allow_provider_override', 'allow_reasoning_override', 'allow_child_approval_override', 'allow_fast_override')
    return dict(version=VERSION, task_id='', root_task_id=prior['root_task_id'] if prior else '',
                parent_task_id=prior['task_id'] if prior else '', depth=c.current_depth(),
                caller_home=str(c.get_hermes_home_path()), target_home=request['target_home'],
                completion_owner_home=str(c.get_hermes_home_path()), origin=origin,
                runs_root=str(c.get_runs_root()), locks_root=str(c.get_locks_root()),
                ceilings={**{k: policy.values[k] for k in keys},
                          'workdir_constraints': workdir_constraints(policy)}, ancestors=ancestors)


def finalize(request, task_id):
    ctx = request['execution_context']
    ctx['task_id'] = task_id
    ctx['root_task_id'] = ctx['root_task_id'] or task_id
    request.update(runs_root=ctx['runs_root'], locks_root=ctx['locks_root'], root_task_id=ctx['root_task_id'])


def worker_env(request, reservation):
    c = _core()
    env = c.child_environment(int(request.get('delegate_depth') or 0))
    env['PROFILE_DELEGATE_DEPTH'] = str(int(request.get('delegate_depth') or 0))
    env['HERMES_HOME'] = str(c.get_hermes_home_path())
    for key in ('PROFILE_DELEGATE_PARENT_TASK_ID', 'PROFILE_DELEGATE_ROOT_TASK_ID', 'PROFILE_DELEGATE_APPROVAL_REQUEST'):
        if key in os.environ:
            env[key] = os.environ[key]
    env = child_env(request, env)
    env['PROFILE_DELEGATE_RUNS_ROOT'] = request.get('runs_root') or str(c.get_runs_root())
    if reservation is not None:
        env['PROFILE_DELEGATE_ASYNC_FD'] = str(reservation.handle.fileno())
    if reservation is None and 'PROFILE_DELEGATE_ASYNC_FD' in os.environ:
        env['PROFILE_DELEGATE_ASYNC_FD'] = os.environ['PROFILE_DELEGATE_ASYNC_FD']
    return env


def child_env(request, env):
    ctx = request.get('execution_context')
    if ctx:
        for key in (*LIMITS, *ALLOWLISTS, 'allowed_profiles', 'allow_all_profiles', 'allowed_workdirs'):
            env.pop('PROFILE_DELEGATE_' + key.upper(), None)
        env.update(PROFILE_DELEGATE_RUNS_ROOT=ctx['runs_root'], PROFILE_DELEGATE_LOCKS_ROOT=ctx['locks_root'])
    return env
