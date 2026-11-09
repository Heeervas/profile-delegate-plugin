"""Child-only immutable writer pin; native active/durable leases remain owners."""
import copy
from contextlib import contextmanager
import functools
import hashlib
import json
import os
import threading
from pathlib import Path
from typing import NoReturn

if __package__:
    from . import native_approval, native_resolution, session_admission
else:
    import native_approval
    import native_resolution
    import session_admission


def bounded_bytes(path):
    import stat
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1_048_576:
            raise native_resolution.ResolutionError('unsafe or oversized frozen evidence')
        content = handle.read(1_048_577)
        if len(content) > 1_048_576:
            raise native_resolution.ResolutionError('oversized frozen evidence')
        return content


def bounded_digest(path):
    return hashlib.sha256(bounded_bytes(path)).digest()


class WriterPin:
    def __init__(self, request, path):
        self.request = copy.deepcopy(request)
        self.path = Path(path).resolve()
        content = bounded_bytes(self.path)
        if json.loads(content) != request:
            raise native_resolution.ResolutionError('private request changed before binding')
        self.digest = hashlib.sha256(content).digest()
        self.home = Path(request['target_home'])
        self.cwd = Path(request['workdir'])
        self.boundary = self.request['native_boundary']
        self.session_id = self.boundary['admitted_id']
        self.cli = self.agent = self.record = None
        self.ui_id = None
        self.error = None
        self.claim_lock = threading.RLock()
        self.check()

    def fail(self, reason) -> NoReturn:
        self.error = self.error or str(reason)
        raise native_resolution.ResolutionError('delegated native writer refused: ' + self.error)

    def check(self, db=None, *, resolve=True):
        from hermes_constants import get_hermes_home
        if self.error:
            self.fail(self.error)
        try:
            if get_hermes_home().resolve() != self.home or Path(os.environ['HERMES_HOME']).resolve() != self.home:
                self.fail('target home changed')
            if bounded_digest(self.path) != self.digest:
                self.fail('private frozen request changed')
            self.check_authority()
            self.check_workspace(db)
            if self.session_id:
                session_admission.exclude_ancestors(self.home, self.session_id, self.request['execution_context']['ancestors'])
                if resolve and (self.request['session_mode'] == 'resume' or (self.home / 'state.db').is_file()):
                    final = native_resolution.resolve(self.home, self.session_id,
                                                      compression_only=self.boundary.get('compression_only', False))
                    if final != self.session_id:
                        self.fail('native durable identity drift; fresh authorized admission required')
        except Exception as exc:
            self.fail(exc)

    def check_authority(self):
        envelope = native_approval.validate(self.request['native_approval'])
        if Path(envelope['target']).resolve() != self.home:
            self.fail('frozen target does not match native home')
        for proof in self.boundary.get('retained_requests', []):
            if bounded_digest(Path(proof['path'])).hex() != proof['sha256']:
                self.fail('retained origin/frozen authority changed')

    def check_workspace(self, db):
        if db is not None and Path(db.db_path).resolve() != self.home / 'state.db':
            self.fail('native DB substituted')
        if not self.cwd.is_dir() or self.cwd.resolve() != self.cwd:
            self.fail('authorized workspace disappeared or changed')
        if self.request.get('workspace'):
            from importlib import import_module
            module = import_module('.worktrees', __package__) if __package__ else __import__('worktrees')
            module.verify(self.request['workspace'])

    def bind_id(self, session_id):
        from importlib import import_module
        c = import_module('.core', __package__) if __package__ else __import__('core')
        if not c.valid_session_identity(session_id):
            self.fail('native identity missing')
        if self.session_id and self.session_id != session_id:
            self.fail('native identity differs from admitted identity')
        self.session_id = session_id
        self.check()

    def bind_agent(self, agent):
        if agent._session_db is None:
            self.fail('native agent DB unavailable')
        self.check(agent._session_db)
        self.bind_id(agent.session_id)
        if self.agent is not None and self.agent is not agent:
            # Rebuilds are allowed only after the former owned agent was retired.
            if self.record and self.record.get('agent') is self.agent:
                self.fail('concurrent native agent substitution')
        self.agent = agent
        cwd = getattr(agent, 'session_cwd', None)
        if cwd and Path(cwd).resolve() != self.cwd:
            self.fail('native agent workspace differs')

    def check_native_authority(self):
        from tools import approval
        if bool(approval._YOLO_MODE_FROZEN) != self.request['native_approval']['bypass']:
            self.fail('native process approval bypass differs from frozen authority')
        if not self.request['native_approval']['bypass'] and approval.is_session_yolo_enabled(self.session_id):
            self.fail('native session bypass exceeds frozen authority')

    def prehistory_ownership(self):
        # TUI claim persistence and record publication are one observation boundary.
        # This is runtime coordination, not another native session/registry lock.
        with self.claim_lock:
            lease = None
            live = self.session_id
            if self.cli is not None:
                lease = self.cli._active_session_lease
            elif self.record is not None:
                lease = self.record.get('active_session_lease')
                live = self.ui_id
            if lease is None:
                session_admission.unowned(self.home, self.session_id)
            else:
                session_admission.active_lease(self.home, self.session_id, lease, live)

    def ownership(self):
        self.check_native_authority()
        self.check(self.agent._session_db if self.agent is not None else None)
        if self.cli is not None:
            if self.cli.session_id != self.session_id:
                self.fail('CLI final identity changed')
            lease, live = self.cli._active_session_lease, self.session_id
        elif self.record is not None:
            if self.record.get('session_key') != self.session_id or self.record.get('agent') is not self.agent:
                self.fail('TUI final record identity changed')
            if Path(self.record.get('profile_home') or self.home).resolve() != self.home:
                self.fail('TUI final record home changed')
            if Path(self.record['cwd']).resolve() != self.cwd:
                self.fail('TUI workspace changed')
            lease, live = self.record.get('active_session_lease'), self.ui_id
        else:
            self.fail('no owned native runtime')
        try:
            session_admission.active_lease(self.home, self.session_id, lease, live)
        except Exception as exc:
            self.fail(exc)
        if self.agent is not None and self.agent.session_id != self.session_id:
            self.fail('agent final identity changed')


@contextmanager
def late_history_guard(pin, agent):
    from importlib import import_module
    module = import_module('.child_session_history', __package__) if __package__ else __import__('child_session_history')
    db = agent._session_db
    names = ('resolve_resume_session_id', 'get_messages_as_conversation')
    saved = {key: (key in vars(db), getattr(db, key)) for key in names}
    history = module.History(pin, db)

    def resolve(session_id):
        pin.ownership()
        if session_id != pin.session_id:
            pin.fail('late durable resolver identity differs from admission')
        # Actual native algorithm on the strict read-only receiver. Never adopt
        # its new identity on the writable agent/DB or return it to the producer.
        final = native_resolution.resolve(pin.home, session_id)
        if final != pin.session_id:
            pin.fail('late durable native identity drift')
        pin.ownership()
        return final
    db.resolve_resume_session_id = resolve
    db.get_messages_as_conversation = history.get_messages_as_conversation
    try:
        yield
    finally:
        for name, (owned, value) in saved.items():
            if owned:
                setattr(db, name, value)
            else:
                delattr(db, name)


def install_durable(pin):
    from agent import turn_facade_lease as native
    original = native.admit_durable_turn_lease
    import inspect
    if tuple(inspect.signature(original).parameters) != ('agent', 'session_id', 'relay_turn_id', 'task_context', 'conversation_history'):
        pin.fail('unsupported native durable-turn admission')

    @functools.wraps(original)
    def admit(agent, **kwargs):
        if agent is not pin.agent:
            return original(agent, **kwargs)
        pin.ownership()
        with late_history_guard(pin, agent):
            admission = original(agent, **kwargs)
        try:
            pin.ownership()
            if kwargs['task_context'].get('session_id') != pin.session_id or kwargs['session_id'] != pin.session_id:
                pin.fail('native durable task-context identity changed')
            if admission.early_result is None:
                lease = admission.lease
                if lease is None or lease.agent is not agent or lease.db is not agent._session_db:
                    pin.fail('native durable turn lease absent or borrowed')
                with native_resolution.Snapshot(pin.home) as receiver:
                    key = receiver._session_turn_lease_key_on_conn(receiver.connection, pin.session_id)
                    row = receiver._read_one('SELECT holder,expires_at FROM session_turn_leases WHERE conversation_id=?', (key,))
                    import time
                    if not row or row['holder'] != lease.holder or row['expires_at'] <= time.time():
                        pin.fail('native durable turn lease not held for final compression root')
            return admission
        except BaseException:
            if admission.lease is not None:
                admission.lease.release()
            raise
    native.admit_durable_turn_lease = admit


def install(request, path, *, tui=False):
    pin = WriterPin(request, path)
    install_durable(pin)
    if tui:
        from importlib import import_module
        module = import_module('.child_session_tui', __package__) if __package__ else __import__('child_session_tui')
        module.install(pin)
    else:
        from importlib import import_module
        module = import_module('.child_session_cli', __package__) if __package__ else __import__('child_session_cli')
        module.install(pin)
    return pin
