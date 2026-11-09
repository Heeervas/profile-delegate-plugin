"""Atomic domain permit allocation using the existing file-lock ownership.

Count every occupied numbered slot, including above a descendant's ceiling.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any
from pathlib import Path
import json
import os
import re
import threading


_pending_processes = {}
_pending_processes_lock = threading.Lock()


def reconcile_processes():
    """Release retained CLI references only on exact Popen-confirmed exit."""
    with _pending_processes_lock:
        for key, (process, handles, run_dir, alive_field) in list(_pending_processes.items()):
            try:
                exited = process.poll() is not None
            except Exception:
                exited = False
            if exited:
                _release_process_entry(key, (process, handles, run_dir, alive_field))


def _release_process_entry(key, entry):
    """Commit exact exit while the registry lock serializes all cleanup owners."""
    _process, handles, run_dir, alive_field = entry
    for handle in handles:
        handle.close()
    if run_dir is not None:
        try:
            with _core()._locked_run_status(run_dir) as status:
                status.update({alive_field: False, 'reaping_state': 'reaped'})
                _core()._write_locked_status_snapshot(run_dir, status)
        except Exception:
            pass  # Optional liveness enrichment cannot strand confirmed capacity.
    del _pending_processes[key]


def confirm_process_exit(process):
    """Consume successful exact Popen.wait evidence, without another observation."""
    with _pending_processes_lock:
        entry = _pending_processes.get(id(process))
        if entry is not None and entry[0] is process:
            _release_process_entry(id(process), entry)


def retain_process(process, run_dir, alive_field, reservation=None):
    """Keep independent references to all capacity occupied by this exact child."""
    with _pending_processes_lock:
        if id(process) in _pending_processes:
            return
        raw = os.getenv('PROFILE_DELEGATE_ASYNC_FD') if reservation is None else None
        fds = [] if raw is None else [int(raw)]
        slots = (_execution_fd.get(), _async_slot.get()) if reservation is None else (reservation,)
        for slot in slots:
            if slot is not None and slot.handle is not None:
                fds.append(slot.handle.fileno())
        handles = []
        try:
            for fd in set(fds):
                handles.append(os.fdopen(os.dup(fd), 'a+'))
        except BaseException:
            for handle in handles:
                handle.close()
            raise
        _pending_processes[id(process)] = (process, handles, run_dir, alive_field)
        if run_dir is not None:
            _core().merge_run_status_best_effort(run_dir, {alive_field: None, 'reaping_state': 'unknown'})

    def reap():
        try:
            process.wait()
        except Exception:
            return  # Registry remains the owner; the detached worker also drains it.
        confirm_process_exit(process)

    try:
        threading.Thread(target=reap, name='profile-delegate-cli-reaper', daemon=True).start()
    except RuntimeError:
        pass  # Caller stays bounded; retained owner or next admission reconciles.


def wait_for_processes(run_dir):
    """Only the detached owner waits; API/thread callers remain bounded.

    Failed wait or reaper startup never transfers ownership to a PID or a signal.
    Reconcile the retained Popen objects until exact exit can be observed.
    """
    pause = threading.Event()
    while True:
        reconcile_processes()
        with _pending_processes_lock:
            if not any(item[2] == run_dir for item in _pending_processes.values()):
                return
        pause.wait(0.05)


@contextmanager
def owned_process(process, run_dir, alive_field):
    """Bound caller unwind; keep the exact child and permit on uncertain reap."""
    try:
        yield process
    finally:
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        try:
            exited = getattr(process, 'returncode', None) is not None or process.poll() is not None
        except Exception:
            exited = False
        if not exited:
            retain_process(process, run_dir, alive_field)


_execution_fd: ContextVar[Any] = ContextVar('profile_delegate_execution_slot', default=None)
_async_slot: ContextVar[Any] = ContextVar('profile_delegate_async_slot', default=None)


def _core():
    if __package__:
        from . import core
    else:
        import core
    return core


@contextmanager
def _allocator(root, prefix):
    c = _core()
    if c.fcntl is None:
        raise c.ProfileDelegateError('domain capacity requires fcntl', 'configuration_error')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    c.chmod_best_effort(root, 0o700)
    with (root / (prefix + '-allocation.lock')).open('a+') as handle:
        c.chmod_best_effort(Path(handle.name), 0o600)
        try:
            c.fcntl.flock(handle.fileno(), c.fcntl.LOCK_EX | c.fcntl.LOCK_NB)
        except BlockingIOError as exc:
            code = 'concurrency_limit' if prefix == 'slot' else 'async_concurrency_limit'
            raise c.ProfileDelegateError('capacity admission busy; retry after the active admission', code) from exc
        try:
            yield
        finally:
            c.fcntl.flock(handle.fileno(), c.fcntl.LOCK_UN)


def close_reference(reservation):
    # Launcher and notification watcher can release the same reference together.
    with _pending_processes_lock:
        if reservation is not None and reservation.handle is not None:
            reservation.handle.close()
            reservation.handle = None


def inherited_fds():
    raw = os.getenv('PROFILE_DELEGATE_ASYNC_FD')
    values = [] if raw is None else [int(raw)]
    for slot in (_execution_fd.get(), _async_slot.get()):
        if slot is not None and slot.handle is not None:
            values.append(slot.handle.fileno())
    for fd in values:
        os.fstat(fd)
    return tuple(set(values))


def passed_fds(reservation):
    return () if reservation is None else (reservation.handle.fileno(),)


def acquire(maximum, *, prefix='slot', root=None):
    reconcile_processes()
    c = _core()
    root = Path(root or c.get_locks_root())
    code = 'concurrency_limit' if prefix == 'slot' else 'async_concurrency_limit'
    held, free = [], []
    with _allocator(root, prefix):
        paths = sorted(p for p in root.iterdir() if re.fullmatch(re.escape(prefix) + r'_\d+\.lock', p.name))
        if len(paths) > 100:
            raise c.ProfileDelegateError('capacity domain exceeds bounded slot count', code)
        try:
            for path in paths:
                if path.is_symlink():
                    raise c.ProfileDelegateError('unsafe capacity entry', code)
                handle = path.open('a+')
                try:
                    c.fcntl.flock(handle.fileno(), c.fcntl.LOCK_EX | c.fcntl.LOCK_NB)
                except BlockingIOError:
                    handle.close()
                    held.append(path)
                else:
                    free.append(handle)
            if len(held) >= maximum:
                raise c.ProfileDelegateError(f'profile delegation capacity reached ({maximum})', code)
            if free:
                handle = free.pop(0)
                slot = int(Path(handle.name).stem.rsplit('_', 1)[1])
            else:
                used = {int(p.stem.rsplit('_', 1)[1]) for p in paths}
                slot = next(i for i in range(100) if i not in used)
                handle = (root / f'{prefix}_{slot}.lock').open('a+')
                c.fcntl.flock(handle.fileno(), c.fcntl.LOCK_EX | c.fcntl.LOCK_NB)
            try:
                handle.seek(0)
                handle.truncate()
                json.dump({'pid': os.getpid(), 'identity': c._process_identity(os.getpid()), 'slot': slot}, handle)
                handle.flush()
                c.chmod_best_effort(Path(handle.name), 0o600)
                return c.ConcurrencySlot(Path(handle.name), handle, slot)
            except BaseException:
                handle.close()
                raise
        finally:
            for handle in free:
                handle.close()
