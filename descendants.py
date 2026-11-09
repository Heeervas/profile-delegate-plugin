"""Read-only direct-child snapshots; lineage is visibility, never authority."""


def _core():
    if __package__:
        from . import core
    else:
        import core
    return core


def direct_runs(run_dir, request):
    """Reuse the resolved runs domain; never follow directory symlinks."""
    c = _core()
    root = c.execution_context.runs_root(request)
    # iterdir raises for absent/non-directory domains. A normal early return
    # would falsely attest successful enumeration of an empty namespace.
    for path in sorted(root.iterdir(), key=lambda p: p.name):
        if path.is_symlink() or not path.is_dir():
            continue
        try:
            child = c.operator_read_json(path / 'request.json')
            if child.get('parent_task_id') != run_dir.name:
                continue
        except c.ProfileDelegateError:
            continue
        try:
            status = c.operator_read_json(path / 'status.json')
        except c.ProfileDelegateError:
            status = {}
        yield path, child, status


def _parent_origin(c, request, origin, session_id, ui_id):
    """An admitted historical origin survives only native-proven compression."""
    original = origin.get('session_id')
    if not original or origin.get('session_key') not in {original, ui_id}:
        return False
    return original == session_id or c.compression_continuation(
        c.Path(request['profile_home']), original, session_id,
        profile=request.get('profile'), ui_correlated=True,
    )


def return_obligations(run_dir, request, session_id, ui_id):
    """Validate direct private requests; root ancestry is never return authority."""
    c = _core()
    required, pending = set(), set()
    for path, child, status in direct_runs(run_dir, request):
        ctx = child.get('execution_context') or {}
        origin = child.get('origin') or {}
        expected = all((
            child.get('task_id') == path.name == ctx.get('task_id'),
            ctx.get('parent_task_id') == run_dir.name,
            ctx.get('caller_home') == request.get('profile_home'),
            ctx.get('completion_owner_home') == request.get('profile_home'),
            ctx.get('runs_root') == str(c.execution_context.runs_root(request)),
            origin == ctx.get('origin'),
            _parent_origin(c, request, origin, session_id, ui_id),
        ))
        if not expected:
            raise c.ProfileDelegateError('direct child return identity unavailable', 'nested_return_uncertain')
        if status.get('status') not in c.TERMINAL_RUN_STATUSES:
            pending.add(path.name)
        if child.get('background') and child.get('notify_on_complete'):
            required.add(path.name)
        if len(required | pending) > 256:
            raise c.ProfileDelegateError('direct child return inventory cap', 'nested_return_uncertain')
    return required, pending


def snapshot(run_dir, request=None):
    """A bounded ID/state snapshot, not a liveness or control grant."""
    c = _core()
    observed = {'observed_at': c.now_iso(), 'cascade': False, 'runs': [],
                'omitted_count': 0, 'recovery': 'exact_owner_or_local_operator'}
    try:
        request = request if request is not None else c.operator_read_json(run_dir / 'request.json')
        for path, child, status in direct_runs(run_dir, request):
            if len(observed['runs']) >= c.MAX_NESTED_DELEGATIONS:
                observed['omitted_count'] += 1
                continue
            detached = status.get('background_worker_mode') == 'detached'
            observed['runs'].append({
                'task_id': path.name, 'status': status.get('status', 'unknown'),
                'containment': 'detached' if detached else 'foreground_group_or_unknown',
                'transport_alive': status.get('transport_alive'),
                'result_available': (path / 'result.json').is_file(),
            })
        observed['available'] = True
    except (c.ProfileDelegateError, OSError, ValueError) as exc:
        observed['available'] = False
        observed['diagnostic'] = f'descendant namespace unavailable ({type(exc).__name__}); inspect the resolved runs_root with the exact owner or local operator'
    return observed
