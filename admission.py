"""Normalize one public request and inspect policy/workspace without allocating a run."""
from pathlib import Path
import hashlib
import os


def _core():
    if __package__:
        from . import core
    else:
        import core
    return core


def normalize_transport(raw):
    c = _core()
    transport = c.ensure_text(raw['transport_mode'] or 'auto').strip().lower()
    if type(raw['preflight']) is not bool:
        raise c.ProfileDelegateError('preflight must be a boolean', 'validation_error')
    if transport not in {'auto', 'interactive', 'simple'}:
        raise c.ProfileDelegateError('transport_mode must be auto, interactive, or simple', 'validation_error')
    if transport == 'interactive' and (not raw['background'] or c._background_mode() != 'detached'):
        raise c.ProfileDelegateError('interactive transport requires detached background=true', 'validation_error')
    if transport == 'auto' and raw['background'] and c._background_mode() != 'detached':
        raise c.ProfileDelegateError('auto background requires detached interactive worker; choose simple explicitly', 'transport_unavailable')
    return transport


def normalize(raw):
    c = _core()
    transport = normalize_transport(raw)
    mode = c.coerce_session_mode(raw['session_mode'])
    sid = c.validate_session_id(raw['session_id'], required=mode == 'resume')
    if mode == 'new' and sid:
        raise c.ProfileDelegateError('session_mode=new forbids session_id; use resume or omit session_id', 'validation_error')
    task = c.bounded_text('task', raw['task'], c.MAX_TASK_CHARS).strip()
    if not task:
        raise c.ProfileDelegateError('task must be non-empty', 'validation_error')
    text = (task, c.bounded_text('context', raw['context'], c.MAX_CONTEXT_CHARS),
            c.bounded_text('output_contract', raw['output_contract'], c.MAX_OUTPUT_CONTRACT_CHARS))
    requested_mode, output_mode = c.resolve_output_mode(raw['output_mode'], text[2])
    reasoning_mode, reasoning = c.normalize_reasoning_request(raw['reasoning_mode'], raw['reasoning_effort'])
    try:
        approval = c.native_approval.selector(raw['child_approval_mode']) if raw['child_approval_mode'] is not None else None
    except ValueError as exc:
        raise c.ProfileDelegateError(str(exc), 'validation_error') from exc
    duplicate = c.ensure_text(raw['duplicate_policy'] or 'reuse').strip().lower()
    if duplicate not in {'reuse', 'new'}:
        raise c.ProfileDelegateError('duplicate_policy must be reuse or new', 'validation_error')
    request = dict(session_title=c.normalize_session_title(raw['session_title']), session_mode=mode,
                   requested_session_id=sid, requested_transport=transport, reasoning_mode=reasoning_mode,
                   requested_output_mode=requested_mode, resolved_output_mode=output_mode,
                   background=bool(raw['background']), notify_on_complete=bool(raw['notify_on_complete']),
                   origin=c.normalize_origin(raw['origin'], raw['origin_session_key']))
    return request, text, reasoning, approval, duplicate


def admit(raw):
    c = _core()
    options = c.worktrees.options(raw['worktree'], raw['base_ref'], raw['branch'], raw['session_mode'], raw['workdir'], raw['capability_preset'])
    request, text, reasoning, approval, duplicate = normalize(raw)
    policy = c.load_effective_policy()
    depth, max_depth = c.enforce_depth_policy(policy)
    target = c.validate_profile(raw['profile'], policy)
    parent = c.ensure_text(os.getenv('PROFILE_DELEGATE_PARENT_TASK_ID', ''))[:c.MAX_SESSION_ID_CHARS]
    if parent and Path(target.home).resolve() == c.get_hermes_home_path().resolve():
        raise c.ProfileDelegateError('recursive same-home delegation would contend with its ancestor', 'same_profile_delegation_not_supported')
    execution = c.normalize_requested_execution(model=raw['model'], provider=raw['provider'], reasoning_effort=reasoning,
                                               max_turns=raw['max_turns'], toolsets=raw['toolsets'], skills=raw['skills'], policy=policy, validate_policy=False)
    c.validate_preflight(execution, policy, reasoning_mode=request['reasoning_mode'], capability_preset=raw['capability_preset'],
                         target_profile=target.canonical, child_approval_explicit=approval is not None and approval != 'deny')
    records = c.matching_resume_records(target, request['requested_session_id']) if request['session_mode'] == 'resume' else None
    envelope = c.resolve_request_approval(policy, target, request['session_mode'], request['requested_session_id'], approval, records)
    effective, capabilities = c.resolve_capability_preset(raw['capability_preset'], execution)
    cwd, workspace = c.worktrees.resolve_workspace(request, target, raw['workdir'], options, policy, records)
    request.update(c.worktrees.projection({'workspace': workspace}))
    request.update(profile=target.canonical, requested_profile=target.requested, profile_home=target.home, target_home=str(Path(target.home).resolve()),
                   caller_home=str(c.get_hermes_home_path().resolve()), workdir=str(cwd), hermes_bin=c.resolve_hermes_bin(),
                   timeout_seconds=c.coerce_timeout(raw['timeout_seconds'], policy), delegate_depth=depth, delegate_max_depth=max_depth,
                   parent_task_id=parent, child_approval_mode=envelope['effective'], native_approval=envelope, approval_policy=envelope,
                   capability_preset=capabilities['preset'], effective_capabilities=capabilities, requested_execution=execution,
                   effective_execution=effective, origin_session_key=request['origin']['session_key'])
    if request['background'] and request['notify_on_complete'] and not raw['preflight']:
        c.require_native_async_ledger_compatibility()
    return request, policy, text, options, duplicate


def fingerprint_payload(request, text, options):
    keys = ('profile', 'session_title', 'requested_output_mode', 'resolved_output_mode', 'workdir', 'timeout_seconds',
            'background', 'notify_on_complete', 'requested_execution', 'capability_preset', 'child_approval_mode', 'native_approval')
    payload = {key: request[key] for key in keys}
    payload.update(origin=next((request['origin'][k] for k in ('ui_session_id', 'session_id', 'session_key') if request['origin'][k]), ''),
                   session_mode=request['session_mode'], session_id=request['requested_session_id'], transport_mode=request['requested_transport'])
    payload.update({key + '_sha256': hashlib.sha256(value.encode()).hexdigest() for key, value in zip(('task', 'context', 'contract'), text)})
    if options:
        payload['workspace_options'] = options
    return payload


def preflight_result(request, duplicate):
    selected = 'interactive' if request['background'] and request['requested_transport'] != 'simple' else 'simple'
    keys = ('profile', 'session_title', 'session_mode', 'timeout_seconds', 'workdir', 'background', 'notify_on_complete', 'capability_preset')
    return dict(success=True, preflight=True, run_created=False,
                normalized_request={**{k: request[k] for k in keys}, 'session_id': request['requested_session_id'],
                                    'output_mode': request['resolved_output_mode'], 'duplicate_policy': duplicate,
                                    'transport_mode': request['requested_transport'], 'selected_transport': selected},
                requested_execution=request['requested_execution'], preflight_execution=request['effective_execution'],
                runtime_observed_execution='unknown', preflight_capabilities=request['effective_capabilities'],
                runtime_observed_capabilities='unknown', approval_policy=request['approval_policy'], retry_shape=None,
                **_core().worktrees.projection(request))
