"""Read-only admission evidence for the native session writer boundary."""
from pathlib import Path
import os
import hashlib
import json
import io
import functools
import types

if __package__:
    from . import native_resolution
else:
    import native_resolution


def _core():
    if __package__:
        from . import core
    else:
        import core
    return core


def _registry_read(path):
    from hermes_cli import active_sessions as native
    import stat
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 262144:
            raise native_resolution.ResolutionError('unsafe native registry evidence')
        raw = handle.read(262145)
    if len(raw) > 262144:
        raise native_resolution.ResolutionError('native registry byte limit exceeded')
    function = native._read_entries
    namespace = dict(function.__globals__, open=lambda *a, **kw: io.StringIO(raw.decode('utf-8-sig')))
    receiver = types.FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    functools.update_wrapper(receiver, function)
    return receiver(path, strict=True)


def registry_entries(home, *, locked=False):
    """Read without pruning, creating registry files or borrowing another lease."""
    path = Path(home) / 'runtime' / 'active_sessions.json'
    if not path.exists():
        return []
    if path.is_symlink() or path.stat().st_size > 262144:
        raise native_resolution.ResolutionError('unsafe native registry evidence')
    if not locked:
        return _registry_read(path)
    lock = path.with_suffix('.lock')
    if not lock.is_file() or lock.is_symlink():
        raise native_resolution.ResolutionError('native registry lock unavailable')
    import fcntl
    with lock.open('rb') as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise native_resolution.ResolutionError('native ownership observation busy') from exc
        return _registry_read(path)


def exclude_ancestors(home, session_id, ancestors):
    for ancestor in ancestors:
        if ancestor['home'] == str(home) and ancestor['session_id'] == session_id:
            raise native_resolution.ResolutionError('live caller/ancestor session is not a child execution target')


def unowned(home, session_id):
    from hermes_cli import active_sessions as native
    for entry in registry_entries(home):
        if entry['session_id'] == session_id:
            alive = native._pid_liveness(entry['pid'], entry.get('process_start_time'))
            if alive is not False:
                raise native_resolution.ResolutionError('native session has a live or uncertain owner')


def metadata(home, session_id):
    """Exact admitted row only; no native SessionDB construction or token flush."""
    with native_resolution.Snapshot(home) as receiver:
        row = receiver._read_one('SELECT id,cwd,title FROM sessions WHERE id=?', (session_id,))
        return dict(row) if row else None


def retained_workdir(explicit, records):
    if explicit or not records:
        return explicit
    dirs = {r.get('workdir') for r, _ in records}
    if len(dirs) != 1 or None in dirs:
        raise _core().ProfileDelegateError('conflicting or missing retained cwd', 'workspace_continuity_error')
    return next(iter(dirs))


def request_proof(path, expected):
    from importlib import import_module
    module = import_module('.child_session', __package__) if __package__ else __import__('child_session')
    content = module.bounded_bytes(path)
    if json.loads(content) != expected:
        raise ValueError('retained request bytes changed during admission')
    return dict(path=str(path), sha256=hashlib.sha256(content).hexdigest())


def admit_attempt(value, request, run_dir):
    c = _core()
    stored = c.operator_read_json(run_dir / 'request.json')
    if (stored != request or request.get('task_id') != run_dir.name
            or Path(request['caller_home']) != c.get_hermes_home_path()):
        raise c.ProfileDelegateError('retry lost owning private request', 'native_session_admission_refused')
    # This is continuation within the currently owned run, not authority to start
    # a new run. Both inputs came from its exact persisted private request.
    boundary = _native_target(value)
    boundary['retained_requests'] = [request_proof(run_dir / 'request.json', request)]
    return boundary


def admit(request, records):
    c = _core()
    if request['session_mode'] != 'resume':
        return dict(version=1, requested_id='', admitted_id='', allowed_history_ids=[])
    try:
        boundary = _native_target(request)
        if not records:
            raise ValueError('resume lacks exact origin/frozen request evidence')
        boundary['retained_requests'] = retained_authority(request, records)
        return boundary
    except (ValueError, OSError, native_resolution.ResolutionError) as exc:
        raise c.ProfileDelegateError(str(exc), 'native_session_admission_refused') from exc


def _native_target(request):
    c = _core()
    home, original = Path(request['target_home']), request['requested_session_id']
    try:
        if not c.valid_session_identity(original):
            raise ValueError('delegated resume requires an exact durable ID, not a title or selector')
        exclude_ancestors(home, original, request['execution_context']['ancestors'])
        unowned(home, original)
        original_row = metadata(home, original)
        compression_only = bool(original_row and (original_row['title'] or '').strip() == 'Bot Chat')
        with native_resolution.Snapshot(home) as receiver:
            final = receiver.resolve(original, compression_only=compression_only)
            allowed = receiver.ancestry(final)
        exclude_ancestors(home, final, request['execution_context']['ancestors'])
        unowned(home, final)
        if final != original and not c.compression_continuation(home, original, final, profile=request['profile'], cli_footer=True):
            raise ValueError('native resolution is not an authorized bounded compression continuation')
        row = metadata(home, final)
        if not row or (row['cwd'] and Path(row['cwd']).resolve() != Path(request['workdir'])):
            raise ValueError('native retained cwd differs from authorized workspace')
        return dict(version=1, requested_id=original, admitted_id=final, allowed_history_ids=list(allowed),
                    compression_only=compression_only)
    except (ValueError, OSError, native_resolution.ResolutionError) as exc:
        raise c.ProfileDelegateError(str(exc), 'native_session_admission_refused') from exc


def retained_authority(request, records):
    c = _core()
    proofs = []
    for retained, _status in records:
        c.authorize_run('resume', request['origin'], retained)
        if retained.get('native_approval') != request['native_approval']:
            raise ValueError('conflicting retained frozen authority')
        if Path(retained.get('workdir', '')).resolve() != Path(request['workdir']):
            raise ValueError('retained resume workspace differs')
        path = c.get_runs_root() / retained['task_id'] / 'request.json'
        proofs.append(request_proof(path, retained))
    return proofs


def active_lease(home, session_id, lease, live_id):
    """Match the actual native lease and current PID/start in its pinned registry."""
    from hermes_cli import active_sessions as native
    expected = Path(home) / 'runtime'
    if (not isinstance(lease, native.ActiveSessionLease) or not lease.enabled or lease.released
            or lease.session_id != session_id or lease.state_path != expected / 'active_sessions.json'
            or lease.lock_path != expected / 'active_sessions.lock'):
        raise native_resolution.ResolutionError('missing, disabled, released or foreign native lease')
    entries = registry_entries(home, locked=True)
    matches = [e for e in entries if e['session_id'] == session_id]
    if len(matches) != 1:
        raise native_resolution.ResolutionError('native ownership is not exclusive')
    entry = matches[0]
    if (entry['lease_id'] != lease.lease_id or entry['pid'] != os.getpid()
            or entry.get('process_start_time') != native._own_start_time()
            or native._own_start_time() is None
            or (entry.get('metadata') or {}).get('live_session_id') != live_id):
        raise native_resolution.ResolutionError('native lease PID/start/live identity mismatch')
    return entry
