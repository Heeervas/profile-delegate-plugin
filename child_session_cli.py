"""Owned CLI adapters installed before native argument normalization or history."""
import functools
import inspect
import os
from pathlib import Path

if __package__:
    from . import native_resolution, session_admission
else:
    import native_resolution
    import session_admission


def install(pin):
    import hermes_bootstrap
    hermes_bootstrap.harden_import_path()
    import cli
    from hermes_cli import main, cli_agent_setup_mixin as setup
    cls = getattr(cli, 'HermesCLI')
    required = {'_claim_active_session': ('self', 'surface', 'stderr'),
                '_init_agent': ('self', 'model_override', 'runtime_override', 'request_overrides'),
                '_preload_resumed_session': ('self',), '_load_resumed_history_late': ('self',),
                '_reopen_session': ('self',)}
    for name, parameters in required.items():
        function = getattr(cls, name, None)
        if not callable(function) or tuple(inspect.signature(function).parameters) != parameters:
            pin.fail('unsupported CLI boundary: ' + name)
    if '_compression_descendant' not in cls._follow_compression_chain.__code__.co_names:
        pin.fail('CLI late resolver binding changed')
    if tuple(inspect.signature(main._resolve_session_by_name_or_id).parameters) != ('name_or_id',):
        pin.fail('CLI argument resolution binding changed')
    install_argument_resolution(pin, main)

    def bind(owner):
        if pin.cli is not None and pin.cli is not owner:
            pin.fail('second CLI runtime')
        pin.cli = owner
        pin.check(getattr(owner, '_session_db', None))
        pin.bind_id(owner.session_id)
        if Path(os.getcwd()).resolve() != pin.cwd:
            pin.fail('CLI cwd differs from admitted workspace')
        if pin.request['session_mode'] == 'resume':
            row = session_admission.metadata(pin.home, pin.session_id)
            if not row or (row['cwd'] and Path(row['cwd']).resolve() != pin.cwd):
                pin.fail('CLI stored cwd changed')

    original_reopen = cls._reopen_session

    @functools.wraps(original_reopen)
    def reopen(owner):
        bind(owner)
        result = original_reopen(owner)
        pin.check(owner._session_db)
        return result
    cls._reopen_session = reopen
    original_claim = cls._claim_active_session

    @functools.wraps(original_claim)
    def claim(owner, *args, **kwargs):
        bind(owner)
        accepted = original_claim(owner, *args, **kwargs)
        if accepted:
            # Outside native catch-and-continue; true without ownership is refusal.
            pin.ownership()
        return accepted
    cls._claim_active_session = claim

    def descendant(db, session_id):
        pin.check(db)
        if pin.cli is None or db is not pin.cli._session_db or session_id != pin.session_id:
            pin.fail('CLI late history runtime/identity changed')
        final = native_resolution.resolve(pin.home, session_id)
        if final != pin.session_id:
            pin.fail('CLI late resolver changed durable identity')
        return final
    setup._compression_descendant = descendant

    install_stored_authority(pin, cls, bind)
    original_restore = cls._restore_session_state

    @functools.wraps(original_restore)
    def restore(owner, metadata, **kwargs):
        bind(owner)
        if metadata.get('id') != pin.session_id or (metadata.get('cwd') and Path(metadata['cwd']).resolve() != pin.cwd):
            pin.fail('CLI restore metadata/workspace differs')
        return original_restore(owner, metadata, **kwargs)
    cls._restore_session_state = restore
    install_history(pin, cls, bind)
    original_init = cls._init_agent

    @functools.wraps(original_init)
    def initialize(owner, *args, **kwargs):
        bind(owner)
        success = original_init(owner, *args, **kwargs)
        bind(owner)
        if success:
            if owner.agent is None:
                pin.fail('CLI initialization succeeded without an agent')
            pin.bind_agent(owner.agent)
            pin.ownership()
        return success
    cls._init_agent = initialize


def install_stored_authority(pin, cls, bind):
    original = cls._restore_session_yolo

    @functools.wraps(original)
    def restore_yolo(owner, metadata, **kwargs):
        bind(owner)
        if pin.request['native_approval']['bypass']:
            return original(owner, metadata, **kwargs)
        # Stored model_config is not a new source of delegated authority.
        return None
    cls._restore_session_yolo = restore_yolo


def install_argument_resolution(pin, main):
    original = main._resolve_session_by_name_or_id

    @functools.wraps(original)
    def lookup(value):
        pin.check()
        if pin.request['session_mode'] != 'resume' or value != pin.boundary['requested_id']:
            pin.fail('CLI selector differs from frozen request')
        return pin.session_id
    main._resolve_session_by_name_or_id = lookup


def install_history(pin, cls, bind):
    def wrap_history(name):
        original = getattr(cls, name)

        @functools.wraps(original)
        def guarded(owner, *args, **kwargs):
            bind(owner)
            db = owner._session_db
            from importlib import import_module
            module = import_module('.child_session_history', __package__) if __package__ else __import__('child_session_history')
            history = module.History(pin, db)
            names = (*module.History.PUBLIC, 'reopen_session')
            saved = {key: (key in vars(db), getattr(db, key)) for key in names}
            try:
                for key in names:
                    setattr(db, key, getattr(history, key))
                result = original(owner, *args, **kwargs)
                pin.check(db)
                return result
            finally:
                for key, (owned, value) in saved.items():
                    if owned:
                        setattr(db, key, value)
                    else:
                        delattr(db, key)
                bind(owner)
        setattr(cls, name, guarded)
    for name in ('_preload_resumed_session', '_load_resumed_history_late'):
        wrap_history(name)
