"""Request/ctx/record-bound guards on the effective installed TUI server.

Only child_bootstrap installs these adapters. Native session and turn leases
remain the owners; the history receiver never becomes an agent's DB handle.
"""
import functools
import inspect
from pathlib import Path

if __package__:
    from .child_session_history import History
    from . import session_admission
else:
    from child_session_history import History
    import session_admission


class Adapter:
    def __init__(self, pin, server):
        self.pin, self.server = pin, server
        self.ctx = None
        self.db = None

    def context(self, ctx):
        p = self.pin
        p.check(self.db)
        effective_db = ctx.db.original if isinstance(ctx.db, History) else ctx.db
        if (ctx is not self.ctx or ctx.target != p.session_id or effective_db is not self.db
                or Path(ctx.profile_home or p.home).resolve() != p.home):
            p.fail('TUI resume context/home/DB/ID changed')
        row = session_admission.metadata(p.home, p.session_id)
        if not row or (row['cwd'] and Path(row['cwd']).resolve() != p.cwd):
            p.fail('TUI retained cwd changed')
        p.prehistory_ownership()
        return row

    def record(self, sid, record):
        p = self.pin
        p.check()
        if not isinstance(record, dict):
            p.fail('TUI owned runtime record missing')
        if not p.session_id and p.request['session_mode'] == 'new':
            p.bind_id(record['session_key'])
        if p.ui_id is None:
            p.ui_id = sid
        if p.record is None:
            p.record = record
        if (sid != p.ui_id or record is not p.record or self.server._sessions.get(sid) is not record
                or record['session_key'] != p.session_id
                or Path(record.get('profile_home') or p.home).resolve() != p.home
                or Path(record['cwd']).resolve() != p.cwd):
            p.fail('TUI owned runtime record replaced or retargeted')

    def params(self, params, *, resume):
        p = self.pin
        p.check()
        if params.get('profile') != p.request['profile']:
            p.fail('TUI RPC profile differs from frozen request')
        home = self.server._profile_home(params['profile'])
        if Path(home or self.server._hermes_home).resolve() != p.home:
            p.fail('TUI RPC resolved home differs')
        if resume:
            allowed = {'profile', 'source', 'cols', 'session_id', 'omit_messages', 'inline_images',
                       'eager_build', 'defer_history'}
            if (set(params) - allowed or params.get('session_id') != p.boundary['requested_id']
                    or p.request['session_mode'] != 'resume' or self.ctx is not None):
                p.fail('unsupported or conflicting delegated resume RPC')
        else:
            if (p.request['session_mode'] != 'new' or p.record is not None
                    or any(k in params for k in ('parent_session_id', 'messages', 'history', 'seed', 'session_id'))
                    or Path(params.get('cwd', '')).resolve() != p.cwd):
                p.fail('unsupported delegated create RPC')

    def metadata(self, db, key):
        p = self.pin
        p.check(db)
        if key != p.session_id:
            p.fail('TUI metadata durable identity changed')
        row = db.get_session(key)
        if not row or row['id'] != key or (row.get('cwd') and Path(row['cwd']).resolve() != p.cwd):
            p.fail('TUI actual metadata/workspace differs from admission')
        p.check(db)
        return row

    def hook(self, name, factory):
        original = getattr(self.server, name)
        setattr(self.server, name, factory(original))

    def install_resume(self):
        s, p = self.server, self.pin
        original_handler = s._methods['session.resume']

        @functools.wraps(original_handler)
        def handler(rid, params):
            self.params(params, resume=True)
            private = dict(params, session_id=p.session_id)
            result = original_handler(rid, private)
            p.check()
            return result
        s._methods['session.resume'] = handler
        original_init = s._Resume.__init__

        @functools.wraps(original_init)
        def init(ctx, rid, params, target):
            p.check()
            if self.ctx is not None or target != p.session_id:
                p.fail('TUI second/unadmitted resume context')
            original_init(ctx, rid, params, target)
            self.ctx = ctx
        s._Resume.__init__ = init

        def locate(ctx):
            p.check(ctx.db)
            if ctx is not self.ctx or ctx.target != p.session_id:
                p.fail('TUI unowned locate')
            self.db = ctx.db
            self.context(ctx)
            ctx.found = self.metadata(ctx.db, p.session_id)
            if not ctx.found or ctx.found['id'] != p.session_id:
                p.fail('TUI exact admitted row missing')
            return None

        def follow(ctx):
            # Never call the suppressed native helper or accept a newly selected ID.
            self.context(ctx)
            ctx.found = self.metadata(ctx.db, p.session_id)
            if not ctx.found or ctx.found['id'] != p.session_id:
                p.fail('TUI admitted row disappeared')
        s._resume_locate, s._resume_follow_tip = locate, follow

        def no_reuse(ctx, *_args):
            self.context(ctx)
            p.fail('delegated execution cannot reattach a foreign live runtime')
        s._resume_reuse_live = s._resume_reuse_live_locked = no_reuse

        def guarded_context(original):
            @functools.wraps(original)
            def call(ctx, *args, **kwargs):
                self.context(ctx)
                result = original(ctx, *args, **kwargs)
                self.context(ctx)
                return result
            return call
        for name in ('_resume_cold', '_resume_eager', '_resume_deferred'):
            self.hook(name, guarded_context)
        for name in ('mint',):
            setattr(s._Resume, name, guarded_context(getattr(s._Resume, name)))

    def install_history(self):
        s, p = self.server, self.pin

        def history_context(original):
            @functools.wraps(original)
            def call(ctx, *args, **kwargs):
                # Nested native child_history calls reuse the same guarded receiver.
                original_db = ctx.db
                if isinstance(original_db, History):
                    return original(ctx, *args, **kwargs)
                self.context(ctx)
                ctx.db = History(p, original_db)
                try:
                    result = original(ctx, *args, **kwargs)
                    p.check(original_db)
                    return result
                finally:
                    ctx.db = original_db
            return call
        for name in ('read_history', 'child_history', 'display_prefix'):
            setattr(s._Resume, name, history_context(getattr(s._Resume, name)))
        s._resume_guard = history_context(s._resume_guard)
        original_todo = s._todo_state_from_db

        @functools.wraps(original_todo)
        def todo(db, key):
            if self.ctx is not None:
                self.context(self.ctx)
                if db is not self.db or key != p.session_id:
                    p.fail('TUI todo DB scope changed')
                db = History(p, db)
            result = original_todo(db, key)
            p.check()
            return result
        s._todo_state_from_db = todo
        original_schedule = s._schedule_resume_hydration

        @functools.wraps(original_schedule)
        def schedule(sid, stored_id, db, **kwargs):
            self.context(self.ctx)
            record = s._sessions.get(sid)
            self.record(sid, record)
            if stored_id != p.session_id or db is not self.db:
                p.fail('TUI deferred DB/ID changed')
            receiver = History(p, db, lambda: self.record(sid, record))
            return original_schedule(sid, stored_id, receiver, **kwargs)
        s._schedule_resume_hydration = schedule
        original_load = s._load_resume_transcript

        @functools.wraps(original_load)
        def load(db, stored_id, **kwargs):
            if not isinstance(db, History) or db.pin is not p:
                p.fail('TUI hydration lost explicit request receiver')
            db.check()
            result = original_load(db, stored_id, **kwargs)
            db.check()
            return result
        s._load_resume_transcript = load

    def install_runtime(self):
        s, p = self.server, self.pin
        original_create = s._methods['session.create']

        @functools.wraps(original_create)
        def create(rid, params):
            self.params(params, resume=False)
            result = original_create(rid, dict(params, cwd_explicit=True))
            payload = result.get('result') or {}
            sid = payload.get('session_id')
            if sid:
                record = s._sessions.get(sid)
                p.bind_id(record['session_key'])
                self.record(sid, record)
            p.check()
            return result
        s._methods['session.create'] = create
        original_record = s._deferred_session_record

        @functools.wraps(original_record)
        def make_record(key, **kwargs):
            p.bind_id(key)
            if Path(kwargs['cwd']).resolve() != p.cwd:
                p.fail('TUI record workspace differs')
            return original_record(key, **kwargs)
        s._deferred_session_record = make_record
        original_claim = s._claim_or_reuse_live

        @functools.wraps(original_claim)
        def claim(sid, key, record, lease):
            p.bind_id(key)
            p.check()
            if s._find_live_session_by_key(key, record.get('profile_home')) is not None:
                p.fail('TUI foreign live runtime cannot be reused')
            result = original_claim(sid, key, record, lease)
            if result is not None:
                p.fail('TUI concurrent foreign runtime winner')
            self.record(sid, record)
            return result
        s._claim_or_reuse_live = claim
        original_hydrate = s._hydrate_session_cwd

        @functools.wraps(original_hydrate)
        def hydrate(sid, key, db, home):
            p.bind_id(key)
            p.check(db)
            record = s._sessions.get(sid)
            self.record(sid, record)
            if p.request['session_mode'] == 'resume':
                self.context(self.ctx)
            if Path(home or p.home).resolve() != p.home:
                p.fail('TUI hydrate home changed')
            original_get = None
            actual_db = db if db is not None else s._get_db()
            if actual_db is not None:
                original_get = actual_db.get_session
                def get_metadata(target):
                    p.check(actual_db)
                    if target != p.session_id:
                        p.fail('TUI hydrate metadata identity changed')
                    row = original_get(target)
                    if row and row.get('cwd') and Path(row['cwd']).resolve() != p.cwd:
                        p.fail('TUI hydrate retained cwd changed')
                    return row
                actual_db.get_session = get_metadata
            try:
                result = original_hydrate(sid, key, db, home)
            finally:
                if original_get is not None and actual_db is not None:
                    actual_db.get_session = original_get
            self.record(sid, record)
            return result
        s._hydrate_session_cwd = hydrate

    def install_claim(self):
        s, p = self.server, self.pin
        original = s._ensure_active_session_slot

        @functools.wraps(original)
        def ensure(sid, record):
            # Do not hold this across hydration/build waits. Only the native
            # acquire -> record attachment interval must be indivisible to readers.
            with p.claim_lock:
                self.record(sid, record)
                p.prehistory_ownership()  # Never take over another runtime's lease.
                previous = record.get('active_session_lease')
                result = original(sid, record)
                if result is None:
                    lease = record.get('active_session_lease')
                    session_admission.active_lease(p.home, p.session_id, lease, sid)
                    try:
                        self.record(sid, record)
                    except BaseException:
                        if previous is None:
                            lease.release()  # Only the just-validated exact own claim.
                        raise
                return result
        s._ensure_active_session_slot = ensure

    def install_build(self):
        s, p = self.server, self.pin

        def build_guard(original):
            @functools.wraps(original)
            def call(sid, record):
                self.record(sid, record)
                return original(sid, record)
            return call
        self.hook('_start_agent_build', build_guard)
        original_await = s._await_resume_history

        @functools.wraps(original_await)
        def await_history(sid, record):
            result = original_await(sid, record)
            self.record(sid, record)
            return result
        s._await_resume_history = await_history
        original_make = s._make_agent

        @functools.wraps(original_make)
        def make(sid, key, *args, **kwargs):
            p.bind_id(key)
            if p.ui_id is not None and sid != p.ui_id:
                p.fail('TUI build runtime differs')
            p.ui_id = sid
            p.check(kwargs.get('session_db') or s._get_db())
            if kwargs.get('session_id', key) != key:
                p.fail('TUI factory durable identity changed')
            cwd = kwargs.get('cwd_override')
            if cwd and Path(cwd).resolve() != p.cwd:
                p.fail('TUI build workspace changed')
            agent = original_make(sid, key, *args, **kwargs)
            p.bind_agent(agent)
            return agent
        s._make_agent = make
        original_in_context = s._make_agent_in_context

        @functools.wraps(original_in_context)
        def in_context(sid, key, **kwargs):
            p.check(kwargs.get('session_db'))
            if self.ctx is not None:
                self.context(self.ctx)
            return original_in_context(sid, key, **kwargs)
        s._make_agent_in_context = in_context
        original_admit = s._admit_prompt_turn

        @functools.wraps(original_admit)
        def admit(sid, record, *args, **kwargs):
            self.record(sid, record)
            result = original_admit(sid, record, *args, **kwargs)
            if result is not None:
                p.bind_agent(record['agent'])
                p.ownership()
            return result
        s._admit_prompt_turn = admit


def install(pin):
    from tui_gateway import server as s
    from hermes_state import SessionDB
    from typing import Any, cast
    s = cast(Any, s)
    required = {'_ensure_active_session_slot': ('sid', 'session'),
                '_resume_locate': ('ctx',), '_resume_follow_tip': ('ctx',),
                '_resume_guard': ('ctx',), '_resume_cold': ('ctx',), '_resume_eager': ('ctx',),
                '_resume_deferred': ('ctx',), '_schedule_resume_hydration':
                ('sid', 'stored_id', 'db', 'close_db', 'model_history_only'),
                '_start_agent_build': ('sid', 'session'), '_await_resume_history': ('sid', 'current'),
                '_hydrate_session_cwd': ('sid', 'key', 'session_db', 'profile_home'),
                '_load_resume_transcript': ('db', 'stored_id', 'model_history_only'),
                '_make_agent_in_context': ('sid', 'key', 'kwargs'),
                '_admit_prompt_turn': ('sid', 'session', 'text', 'image_paths', 'queued_prompt_generation', 'display_kind', 'display_metadata')}
    handler = s._methods.get('session.resume')
    if handler is None or handler.__globals__ is not vars(s):
        pin.fail('TUI registered resume handler is not server-bound')
    assert handler is not None
    if not {'_Resume', '_resume_locate', '_resume_follow_tip', '_resume_guard'}.issubset(handler.__code__.co_names):
        pin.fail('TUI registered resume call graph changed')
    for name, params in required.items():
        fn = getattr(s, name, None)
        if not callable(fn) or tuple(inspect.signature(fn).parameters) != params or fn.__globals__ is not vars(s):
            pin.fail('unsupported effective TUI boundary: ' + name)
    for name in ('read_history', 'child_history', 'display_prefix', 'mint'):
        if getattr(s._Resume, name).__globals__ is not vars(s):
            pin.fail('TUI context methods no longer server-bound')
    for name in ('get_resume_conversations', 'get_messages_as_conversation', 'get_ancestor_display_prefix'):
        if '_fetch_conversation_rows' not in getattr(SessionDB, name).__code__.co_names:
            pin.fail('native history getter changed: ' + name)
    try:
        inspect.signature(s._make_agent).bind('ui', 'durable', session_id='durable', session_db=object(),
            cwd_override=str(pin.cwd), platform_override='profile-delegate')
    except (TypeError, ValueError) as exc:
        pin.fail('unsupported effective TUI agent factory: ' + str(exc))
    adapter = Adapter(pin, s)
    adapter.install_resume()
    adapter.install_history()
    adapter.install_runtime()
    adapter.install_claim()
    adapter.install_build()
    return adapter
