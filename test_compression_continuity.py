"""Compression permission regressions over disposable native-shaped databases."""
import json
import sqlite3
from contextlib import closing

import pytest

import core


@pytest.fixture(autouse=True)
def isolated_caller_home(tmp_path, monkeypatch):
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    token = set_hermes_home_override(tmp_path)
    try:
        yield
    finally:
        reset_hermes_home_override(token)


def database(home, rows, *, profiles=None):
    home.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(home / 'state.db')) as db:
        db.execute('CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT, session_key TEXT, parent_session_id TEXT, ended_at REAL, end_reason TEXT, model_config TEXT, profile_name TEXT, chat_type TEXT, origin_json TEXT)')
        db.executemany('INSERT INTO sessions VALUES (?,?,?,?,?,?,?,NULL,NULL,NULL)', rows)
        for sid, profile in (profiles or {}).items():
            db.execute('UPDATE sessions SET profile_name=? WHERE id=?', (profile, sid))
        db.commit()


def row(sid, parent=None, reason=None, markers=None, source='discord', lane='lane'):
    return (sid, source, lane, parent, 1 if reason else None, reason, json.dumps(markers or {}))


@pytest.mark.parametrize('field,value', [('profile_name', 'foreign'), ('session_key', None), ('chat_type', 'foreign'), ('origin_json', '{"platform":"foreign"}')])
def test_native_namespace_contradictions_refuse(tmp_path, field, value):
    database(tmp_path, [row('a', reason='compression'), row('b', 'a')], profiles={'a': 'builder', 'b': 'builder'})
    with closing(sqlite3.connect(tmp_path / 'state.db')) as db:
        db.execute("UPDATE sessions SET chat_type='group', origin_json=?", ('{"platform":"discord"}',))
        db.execute(f'UPDATE sessions SET {field}=? WHERE id=?', (value, 'b'))
        db.commit()
    assert not core.compression_continuation(tmp_path, 'a', 'b')


def test_malformed_start_metadata_refuses(tmp_path):
    database(tmp_path, [row('a', reason='compression'), row('b', 'a')])
    with closing(sqlite3.connect(tmp_path / 'state.db')) as db:
        db.execute('UPDATE sessions SET model_config=? WHERE id=?', ('[]', 'a'))
        db.commit()
    assert not core.compression_continuation(tmp_path, 'a', 'b')


@pytest.mark.parametrize('marker', ['_reset_from', '_branched_from', '_delegate_from'])
@pytest.mark.parametrize('value', [None, False, [], 42])
def test_malformed_markers_fail_closed(tmp_path, marker, value):
    database(tmp_path, [row('a', reason='compression'), row('b', 'a', markers={marker: value})])
    assert not core.compression_continuation(tmp_path, 'a', 'b')


@pytest.mark.parametrize('marker', ['_reset_from', '_branched_from', '_delegate_from'])
@pytest.mark.parametrize('generation', [1, 2])
@pytest.mark.parametrize('original', [None, 'older'])
def test_boundary_marker_must_be_inherited_on_every_edge(tmp_path, marker, generation, original):
    rows = [row(f'p{i}', f'p{i-1}' if i else None, 'compression' if i < 3 else None,
                markers={marker: original} if original else {}) for i in range(4)]
    database(tmp_path, rows)
    with closing(sqlite3.connect(tmp_path / 'state.db')) as db:
        db.execute('UPDATE sessions SET model_config=? WHERE id=?',
                   (json.dumps({marker: 'introduced'}), f'p{generation}'))
        db.commit()
    assert not core.compression_continuation(tmp_path, 'p0', 'p3')


@pytest.mark.parametrize('marker', ['_reset_from', '_branched_from', '_delegate_from'])
def test_initial_boundary_conversation_can_compress_repeatedly(tmp_path, marker):
    database(tmp_path, [row(f'p{i}', 'older' if i == 0 else f'p{i-1}',
                            'compression' if i < 3 else None, markers={marker: 'older'})
                        for i in range(4)])
    assert core.compression_continuation(tmp_path, 'p0', 'p3')


@pytest.mark.parametrize('broken', ['b', 'c'])
def test_incomplete_compression_after_candidate_is_not_proof(tmp_path, broken):
    database(tmp_path, [row('a', reason='compression'), row('b', 'a', 'compression'),
                        row('c', 'b', 'compression'), row('d', 'c')])
    with closing(sqlite3.connect(tmp_path / 'state.db')) as db:
        db.execute('UPDATE sessions SET ended_at=NULL WHERE id=?', (broken,))
        db.commit()
    assert not core.compression_continuation(tmp_path, 'a', 'b')


def test_long_chain_has_no_arbitrary_depth_cap(tmp_path):
    database(tmp_path, [row(f's{i}', f's{i-1}' if i else None, 'compression' if i < 149 else None)
                        for i in range(150)])
    assert core.compression_continuation(tmp_path, 's0', 's149')
    assert not core.compression_continuation(tmp_path, 's149', 's0')


def test_origin_display_metadata_may_change_not_namespace(tmp_path):
    database(tmp_path, [row('a', reason='compression'), row('b', 'a')])
    with closing(sqlite3.connect(tmp_path / 'state.db')) as db:
        for sid, message in [('a', 'one'), ('b', 'two')]:
            db.execute('UPDATE sessions SET origin_json=? WHERE id=?',
                       (json.dumps({'platform': 'discord', 'message_id': message, 'chat_name': message}), sid))
        db.commit()
    assert core.compression_continuation(tmp_path, 'a', 'b')


def test_parent_authorization_and_metadata_follow_compression(tmp_path, monkeypatch):
    database(tmp_path, [row('a', reason='compression'), row('b', 'a', 'compression'), row('c', 'b')])
    monkeypatch.setattr(core, 'get_hermes_home_path', lambda: tmp_path)
    status = {'origin': {'session_id': 'a', 'session_key': 'lane', 'source': 'discord'}}
    caller = {'session_id': 'c', 'session_key': 'lane', 'source': 'discord'}
    assert core.authorize_run('status', caller, status) == 'compression'
    with pytest.raises(core.ProfileDelegateError):
        core.authorize_run('cancel', {'session_id': 'a', 'session_key': 'lane'}, {'origin': caller})
    status['origin']['ui_session_id'] = 'ui-a'
    caller['ui_session_id'] = 'ui-b'
    with pytest.raises(core.ProfileDelegateError):
        core.authorize_run('steer', caller, status)


@pytest.mark.parametrize('rows', [
    [row('a', reason='new_session'), row('b', 'a')],
    [row('a', reason='compression'), row('b', 'a', markers={'_reset_from': 'a'})],
    [row('a', reason='compression'), row('b', 'a', markers={'_branched_from': 'a'})],
    [row('a', reason='compression'), row('b', 'a', source='tool')],
    [row('a', reason='compression'), row('b', 'a'), row('other', 'a')],
    [row('a', reason='compression'), row('b', 'missing')],
    [row('a', reason='compression'), row('b', 'a', lane='foreign')],
    [row('a', 'b', 'compression'), row('b', 'a', 'compression')],
])
def test_unproven_edges_are_denied(tmp_path, rows):
    database(tmp_path, rows)
    assert not core.compression_continuation(tmp_path, 'a', 'b')


def test_inherited_markers_and_home_isolation(tmp_path):
    home = tmp_path / 'one'
    database(home, [row('a', reason='compression', markers={'_branched_from': 'older'}), row('b', 'a', markers={'_branched_from': 'older'})])
    assert core.compression_continuation(home, 'a', 'b')
    assert not core.compression_continuation(tmp_path / 'missing', 'a', 'b')
    assert not (tmp_path / 'missing').exists()
    database(tmp_path / 'two', [row('a'), row('b')])
    assert not core.compression_continuation(tmp_path / 'two', 'a', 'b')



def test_dispatch_duplicate_reuse_and_reset_refusal(tmp_path, monkeypatch):
    database(tmp_path, [row('a', reason='compression'), row('b', 'a'), row('reset', 'a', markers={'_reset_from': 'a'})])
    monkeypatch.setattr(core, 'get_hermes_home_path', lambda: tmp_path)
    monkeypatch.setenv('PROFILE_DELEGATE_RUNS_ROOT', str(tmp_path / 'runs'))
    monkeypatch.setenv('PROFILE_DELEGATE_LOCKS_ROOT', str(tmp_path / 'locks'))
    monkeypatch.setenv('PROFILE_DELEGATE_ALLOW_ALL_PROFILES', 'true')
    monkeypatch.delenv('PROFILE_DELEGATE_PARENT_TASK_ID', raising=False)
    monkeypatch.setattr(core, 'validate_profile', lambda p, policy=None: core.ValidatedProfile(p, p, str(tmp_path / p)))
    monkeypatch.setattr(core, 'resolve_workdir', lambda workdir='', policy=None: tmp_path)
    monkeypatch.setattr(core, 'resolve_hermes_bin', lambda: '/usr/bin/hermes')
    monkeypatch.setattr(core, '_start_background_run', lambda run_dir: None)
    def dispatch(sid, task='same task'):
        return core.delegate_profile('reviewer', task, session_title='continuity', background=True,
                                     notify_on_complete=False, origin={'session_id': sid, 'session_key': 'lane', 'source': 'discord'})
    first = dispatch('a')
    assert dispatch('b')['task_id'] == first['task_id']
    status = core.profile_delegate_status(first['task_id'], caller_origin={'session_id': 'b', 'session_key': 'lane', 'source': 'discord'})
    assert status['belongs_to_current_session'] is True
    assert status['origin_match_by'] == 'compression'
    assert dispatch('reset')['task_id'] != first['task_id']
    assert dispatch('b', 'different task')['task_id'] != first['task_id']


@pytest.mark.parametrize('footer,success', [('b', True), ('foreign', False)])
def test_cli_resume_footer_requires_native_compression(tmp_path, monkeypatch, footer, success):
    target = tmp_path / 'reviewer'
    database(target, [row('a', reason='compression'), row('b', 'a'), row('foreign')], profiles={'a': 'reviewer', 'b': 'reviewer', 'foreign': 'reviewer'})
    monkeypatch.setenv('PROFILE_DELEGATE_RUNS_ROOT', str(tmp_path / 'runs'))
    monkeypatch.setenv('PROFILE_DELEGATE_LOCKS_ROOT', str(tmp_path / 'locks'))
    monkeypatch.setenv('PROFILE_DELEGATE_ALLOW_ALL_PROFILES', 'true')
    monkeypatch.delenv('PROFILE_DELEGATE_PARENT_TASK_ID', raising=False)
    monkeypatch.setattr(core, 'validate_profile', lambda p, policy=None: core.ValidatedProfile(p, p, str(target)))
    monkeypatch.setattr(core, 'resolve_workdir', lambda workdir='', policy=None: tmp_path)
    monkeypatch.setattr(core, 'resolve_hermes_bin', lambda: '/usr/bin/hermes')
    def run(cmd, **kwargs):
        core.text_safe_write(kwargs['stdout_path'], '{"status":"ok","summary":"done"}\nsession_id: '+footer)
        core.text_safe_write(kwargs['stderr_path'], '')
        return {'exit_code': 0, 'timed_out': False, 'stdout_limit': 200000, 'stderr_limit': 100000}
    monkeypatch.setattr(core, 'run_capped_subprocess', run)
    result = core.delegate_profile('reviewer', 'task', session_title='resume', session_mode='resume', session_id='a')
    assert result['success'] is success
    if success:
        assert result['child_session_id'] == 'b'
    else:
        assert result['error_code'] == 'resume_session_mismatch'


@pytest.mark.parametrize('proposed,success', [('b', True), ('foreign', False), (42, False), (None, False), ([], False)])
@pytest.mark.parametrize('stage', ['start', 'start-newer-reply', 'submit', 'close'])
def test_tui_callback_publishes_verified_identity(tmp_path, monkeypatch, proposed, success, stage):
    import os
    import tui_runner
    from contextlib import contextmanager
    database(tmp_path, [row('a', reason='compression', source='profile-delegate'), row('b', 'a', 'compression', source='profile-delegate'), row('c', 'b', 'compression', source='profile-delegate'), row('d', 'c', source='profile-delegate'), row('foreign', source='profile-delegate')], profiles={sid: 'reviewer' for sid in ('a', 'b', 'c', 'd', 'foreign')})
    run = tmp_path / 'pd_20260930_120000_aaaaaa'
    run.mkdir()
    request = {'task_id': run.name, 'timeout_seconds': 10, 'workdir': str(tmp_path),
               'profile': 'reviewer', 'session_mode': 'new', 'requested_session_id': '',
               'session_title': 'test', 'profile_home': str(tmp_path), 'hermes_bin': '/usr/bin/hermes',
               'effective_execution': {}, 'effective_capabilities': {}, 'child_approval_mode': 'deny'}
    core.json_safe_write(run / 'request.json', request)
    core.json_safe_write(run / 'status.json', {'task_id': run.name, 'status': 'running'})
    core.text_safe_write(run / 'prompt.txt', 'test')
    def identity_event(callback):
        for value in (('b', 'c', 'd') if success else (proposed,)):
            callback({'method': 'event', 'params': {'type': 'session.info', 'session_id': 'ui-1', 'payload': {'stored_session_id': value}}})
            if success and not stage.startswith('start'):
                assert core.read_json_file(run / 'status.json')['child_session_id'] == value

    class Client:
        stderr_tail = ''
        process = type('Process', (), {'pid': os.getpid(), 'poll': lambda self: 0})()
        def wait_ready(self, **kwargs): pass
        def read_event(self, timeout):
            return {'method': 'event', 'params': {'type': 'message.complete', 'session_id': 'ui-1', 'payload': {'status': 'complete', 'text': '{"status":"ok","summary":"done"}'}}}
        def call(self, *args, **kwargs):
            if stage == 'close':
                identity_event(kwargs['on_event'])
            return {}
        def close(self, **kwargs): pass
    @contextmanager
    def slot(limit):
        yield type('Slot', (), {'slot': 0})()
    monkeypatch.setattr(core, 'acquire_concurrency_slot', slot)
    monkeypatch.setattr(tui_runner, '_environment', lambda *args: {})
    monkeypatch.setattr(tui_runner.tui_rpc, 'launch_gateway', lambda **kwargs: Client())
    def start(*args, **kwargs):
        if stage.startswith('start'):
            identity_event(kwargs['on_event'])
        return {'ui_session_id': 'ui-1', 'child_session_id': 'd' if stage == 'start-newer-reply' else 'a'}
    monkeypatch.setattr(tui_runner.tui_rpc, 'start_session', start)
    def submit(*args, **kwargs):
        if stage == 'submit':
            identity_event(kwargs['on_event'])
        if success and stage != 'close':
            assert core.read_json_file(run / 'status.json')['child_session_id'] == 'd'
        return {}
    monkeypatch.setattr(tui_runner.tui_rpc, 'submit', submit)
    result = tui_runner.execute(run)
    assert result['success'] is success
    if success:
        assert result['child_session_id'] == 'd'
        assert core.read_json_file(run / 'result.json')['session_id'] == 'd'
        terminal = [json.loads(line) for line in (run / 'events.jsonl').read_text().splitlines()][-1]
        assert terminal['payload']['child_session_id'] == 'd'


@pytest.fixture
def dispatch_fixture(tmp_path, monkeypatch):
    """Public plugin dispatch with only unsafe model/process launch replaced."""
    monkeypatch.setenv('PROFILE_DELEGATE_RUNS_ROOT', str(tmp_path / 'runs'))
    monkeypatch.setenv('PROFILE_DELEGATE_LOCKS_ROOT', str(tmp_path / 'locks'))
    monkeypatch.setenv('PROFILE_DELEGATE_ALLOW_ALL_PROFILES', 'true')
    monkeypatch.delenv('PROFILE_DELEGATE_PARENT_TASK_ID', raising=False)
    monkeypatch.setattr(core, 'validate_profile', lambda p, policy=None: core.ValidatedProfile(p, p, str(tmp_path / 'target')))
    monkeypatch.setattr(core, 'resolve_workdir', lambda workdir='', policy=None: tmp_path)
    monkeypatch.setattr(core, 'resolve_hermes_bin', lambda: '/usr/bin/hermes')
    monkeypatch.setattr(core, '_start_background_run', lambda run_dir: None)
    monkeypatch.setattr(core, '_wait_control_ack', lambda *args: None)
    return lambda origin, **options: core.delegate_profile(
        'worker', 'same task', session_title='continuity', background=True,
        notify_on_complete=False, origin=origin, **options,
    )


def test_repeated_parent_public_surface_and_immutable_origin(tmp_path, monkeypatch, dispatch_fixture):
    database(tmp_path, [row('p0', reason='compression'), row('p1', 'p0', 'compression'),
                        row('p2', 'p1', 'compression'), row('p3', 'p2'),
                        row('reset', 'p0', markers={'_reset_from': 'p0'}),
                        row('branch', 'p0', markers={'_branched_from': 'p0'}), row('new')])
    monkeypatch.setattr(core, 'get_hermes_home_path', lambda: tmp_path)
    def origin(sid, **extra):
        return {'session_id': sid, 'source': 'discord', 'session_key': 'lane', **extra}
    first = dispatch_fixture(origin('p0'))
    run = core.resolve_run_dir(first['task_id'])
    for sid in ('p1', 'p2', 'p3'):
        caller = origin(sid)
        assert core.profile_delegate_status(first['task_id'], caller_origin=caller)['belongs_to_current_session'] is True
        listing = core.profile_delegate_list(caller_origin=caller)
        assert listing['count'] == 1 and listing['runs'][0]['task_id'] == first['task_id']
        assert dispatch_fixture(caller)['task_id'] == first['task_id']
        steer = core.profile_delegate_steer(first['task_id'], sid, caller_origin=caller)
        assert steer['state'] == 'pending' and steer['delivery_state'] == 'not_confirmed'
    # Publishing a result doesn't retarget immutable provenance or delivery lane.
    core.publish_terminal_run(run, {'status': 'ok', 'summary': 'done', 'execution_status': 'completed',
                                   'contract_status': 'valid', 'structured': True},
                              {'status': 'completed', 'child_session_id': 'latest-child'})
    final = core.profile_delegate_status(first['task_id'], caller_origin=origin('p3'))
    assert final['origin']['session_id'] == 'p0'
    assert final['result']['summary'] == 'done'
    assert core.profile_delegate_cancel(first['task_id'], caller_origin=origin('p3'))['idempotent'] is True
    for caller in (origin('reset'), origin('branch'), origin('new'), origin('p3', source='telegram'),
                   origin('p3', profile='foreign'), origin('p3', session_key='foreign')):
        with pytest.raises(core.ProfileDelegateError, match='denied'):
            core.profile_delegate_status(first['task_id'], caller_origin=caller)
        assert core.profile_delegate_list(caller_origin=caller)['count'] == 0


def test_context_local_home_authority_and_tui_keys(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    one, two = tmp_path / 'one', tmp_path / 'two'
    rows = [row('a', reason='compression', source='tui', lane='a'), row('b', 'a', source='tui', lane='b')]
    database(one, rows, profiles={'a': 'builder', 'b': 'builder'})
    database(two, [row('a', source='tui'), row('b', source='tui')], profiles={'a': 'builder', 'b': 'builder'})
    status = {'origin': {'session_id': 'a', 'ui_session_id': 'ui', 'source': 'tui', 'profile': 'builder', 'session_key': 'a'}}
    caller = {**status['origin'], 'session_id': 'b', 'session_key': 'b'}
    def check(home):
        token = set_hermes_home_override(home)
        try:
            try:
                return core.authorize_run('status', caller, status)
            except core.ProfileDelegateError:
                return 'denied'
        finally:
            reset_hermes_home_override(token)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(check, (one, two))) == ['compression', 'denied']
    token = set_hermes_home_override(one)
    try:
        for altered in ({**caller, 'ui_session_id': 'foreign'}, {**caller, 'profile': 'foreign'}):
            with pytest.raises(core.ProfileDelegateError):
                core.authorize_run('status', altered, status)
        with pytest.raises(core.ProfileDelegateError):
            core.authorize_run('status', caller, {**status, 'caller_home': str(two)})
    finally:
        reset_hermes_home_override(token)


def test_concurrent_compressed_admission_preserves_legacy_fingerprint(tmp_path, monkeypatch, dispatch_fixture):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    database(tmp_path, [row('p0', reason='compression'), row('p1', 'p0', 'compression'), row('p2', 'p1')])
    monkeypatch.setattr(core, 'get_hermes_home_path', lambda: tmp_path)
    origins = [{'session_id': sid, 'session_key': 'lane', 'source': 'discord'} for sid in ('p0', 'p1', 'p2')]
    first = dispatch_fixture(origins[0])
    before = core.read_json_file(core.resolve_run_dir(first['task_id']) / 'status.json')['request_fingerprint']
    barrier = Barrier(3)
    def call(origin):
        barrier.wait(timeout=5)
        return dispatch_fixture(origin)['task_id']
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert list(pool.map(call, origins)) == [first['task_id']] * 3
    assert core.read_json_file(core.resolve_run_dir(first['task_id']) / 'status.json')['request_fingerprint'] == before
    assert len(list(core.iter_run_dirs())) == 1


@pytest.mark.parametrize('observed', [True, False])
def test_cancel_observes_post_interrupt_rotation_without_claiming_silence(tmp_path, monkeypatch, observed):
    import os
    import time
    import tui_runner
    from test_tui_rpc import _execute_with_control
    database(tmp_path, [row('child-1', reason='compression', source='profile-delegate'),
                        row('child-2', 'child-1', source='profile-delegate')],
             profiles={'child-1': 'reviewer', 'child-2': 'reviewer'})
    holder = {}
    def factory(complete):
        class Client:
            stderr_tail = ''
            process = type('Process', (), {'pid': os.getpid(), 'poll': lambda self: 0})()
            def wait_ready(self, **kwargs): pass
            def call(self, *args, **kwargs): return {}
            def read_event(self, timeout):
                if not observed:
                    raise tui_runner.tui_rpc.TuiTransportError('timed out')
                return {'method': 'event', 'params': {'type': 'session.info', 'session_id': 'ui-1',
                        'payload': {'stored_session_id': 'child-2', 'profile_name': 'reviewer'}}}
            def close(self, **kwargs): holder['deadline'] = kwargs['deadline']
        return Client()
    def arrange():
        monkeypatch.setattr(tui_runner.tui_rpc, 'interrupt', lambda *args, **kwargs: {})
    started = time.monotonic()
    result, ack = _execute_with_control(tmp_path, monkeypatch, 'cancel', arrange, client_factory=factory)
    assert result['status'] == 'cancelled' and ack['state'] == 'accepted'
    expected = 'child-2' if observed else 'child-1'
    run = tmp_path / 'pd_control_cancel'
    assert core.read_json_file(run / 'status.json')['child_session_id'] == expected
    assert core.read_json_file(run / 'result.json')['session_id'] == expected
    assert result['result']['session_identity_evidence'] == ('post_interrupt_observed' if observed else 'last_observed_only')
    terminal = json.loads((run / 'events.jsonl').read_text().splitlines()[-1])
    assert terminal['payload']['child_session_id'] == expected
    assert holder['deadline'] <= started + tui_runner.CANCEL_GRACE_SECONDS + 0.2


@pytest.mark.parametrize('first_sid', ['p0', 'p1'])
def test_zero_run_concurrent_admission_both_creation_orders(tmp_path, monkeypatch, dispatch_fixture, first_sid):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    database(tmp_path, [row('p0', reason='compression'), row('p1', 'p0')])
    monkeypatch.setattr(core, 'get_hermes_home_path', lambda: tmp_path)
    entered, release = Event(), Event()
    original_write = core.json_safe_write
    def write(path, value):
        if path.name == 'request.json' and not entered.is_set():
            entered.set()
            assert release.wait(5)
        return original_write(path, value)
    monkeypatch.setattr(core, 'json_safe_write', write)
    def call(sid):
        return dispatch_fixture({'session_id': sid, 'session_key': 'lane', 'source': 'discord'})
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(call, first_sid)
        assert entered.wait(5)
        second = pool.submit(call, 'p1' if first_sid == 'p0' else 'p0')
        release.set()
        a, b = first.result(), second.result()
    # Old-first reuses forward; new-first cannot grant backward authority.
    assert (a['task_id'] == b['task_id']) is (first_sid == 'p0')
    assert len(list(core.iter_run_dirs())) == (1 if first_sid == 'p0' else 2)
    if first_sid == 'p1':
        with pytest.raises(core.ProfileDelegateError):
            core.profile_delegate_status(a['task_id'], caller_origin={'session_id': 'p0', 'source': 'discord', 'session_key': 'lane'})


@pytest.mark.parametrize('invalid', [None, False, 0, [], {}, ''])
def test_rpc_explicit_malformed_identity_never_falls_back(invalid):
    import tui_rpc
    class Client:
        def call(self, method, *args, **kwargs):
            return {'session_id': 'ui', 'resumed': invalid, 'stored_session_id': invalid, 'session_key': 'valid'}
    for mode in ('new', 'resume'):
        with pytest.raises(tui_rpc.TuiProtocolError):
            tui_rpc.start_session(Client(), profile='worker', mode=mode, session_id='valid', title='test', cwd='/tmp')


@pytest.mark.parametrize('mode', ['new', 'resume'])
@pytest.mark.parametrize('footer', ['', 'bad id'])
@pytest.mark.parametrize('channel', ['stdout', 'stderr', 'conflict'])
@pytest.mark.parametrize('transient', [False, True])
def test_present_invalid_footer_blocks_success_and_recovery(tmp_path, monkeypatch, dispatch_fixture, mode, footer, channel, transient):
    calls = []
    def run(cmd, **kwargs):
        calls.append(cmd)
        stdout = '{"status":"ok","summary":"legitimate output"}'
        stderr = ''
        if channel == 'stdout':
            stdout += '\nsession_id: ' + footer
        else:
            stderr = 'session_id: ' + footer
            if channel == 'conflict':
                stdout += '\nsession_id: a'
        if transient:
            stderr = 'API call failed after 3 retries: Connection error.\n' + stderr
        core.text_safe_write(kwargs['stdout_path'], stdout)
        core.text_safe_write(kwargs['stderr_path'], stderr)
        return {'exit_code': 1 if transient else 0, 'timed_out': False, 'stdout_limit': 200000, 'stderr_limit': 100000}
    monkeypatch.setattr(core, 'run_capped_subprocess', run)
    result = core.delegate_profile('worker', 'task', session_title='test', session_mode=mode,
                                   session_id='a' if mode == 'resume' else '')
    assert result['success'] is False
    assert result['error_code'] == 'resume_session_mismatch'
    assert len(calls) == 1


@pytest.mark.parametrize('mode', ['new', 'resume'])
@pytest.mark.parametrize('outcome', ['complete', 'nonzero', 'timeout', 'cancelled', 'foreign', 'malformed'])
def test_cli_multiple_recovery_rotations(tmp_path, monkeypatch, dispatch_fixture, mode, outcome):
    target = tmp_path / 'target'
    database(target, [row('a', reason='compression', source='cli'), row('b', 'a', 'compression', source='cli'),
                      row('c', 'b', 'compression', source='cli'), row('d', 'c', source='cli'), row('foreign', source='cli')],
             profiles={sid: 'worker' for sid in ('a', 'b', 'c', 'd', 'foreign')})
    monkeypatch.setattr(core, '_wait_for_transient_resume', lambda *args: 'ready')
    commands = []
    def run(cmd, **kwargs):
        commands.append(cmd)
        attempt = len(commands)
        footer = ('b', 'c', 'd')[attempt - 1]
        if attempt == 3 and outcome in ('foreign', 'malformed'):
            footer = 'foreign' if outcome == 'foreign' else 'bad/id'
        core.text_safe_write(kwargs['stdout_path'], ('{"status":"ok","summary":"done"}' if attempt == 3 else '') + '\nsession_id: ' + footer)
        core.text_safe_write(kwargs['stderr_path'], 'API call failed after 3 retries: Connection error.' if attempt < 3 else '')
        return {'exit_code': 1 if attempt < 3 or outcome == 'nonzero' else 0,
                'timed_out': attempt == 3 and outcome == 'timeout',
                'stop_reason': 'cancelled' if attempt == 3 and outcome == 'cancelled' else 'exited',
                'stdout_limit': 200000, 'stderr_limit': 100000}
    monkeypatch.setattr(core, 'run_capped_subprocess', run)
    result = core.delegate_profile('worker', 'task', session_title='test', session_mode=mode,
                                   session_id='a' if mode == 'resume' else '', timeout_seconds=120)
    assert len(commands) == 3
    assert '--resume' in commands[1] and 'b' in commands[1]
    assert '--resume' in commands[2] and 'c' in commands[2]
    assert result['success'] is (outcome == 'complete')
    assert result['child_session_id'] == ('c' if outcome in ('foreign', 'malformed') else 'd')
    assert result['recovery_history'][-1]['attempt'] == 3


def test_native_persistence_both_repeated_rotations(tmp_path, monkeypatch, dispatch_fixture):
    """Real host publication/SQLite, synthetic turns: NOT live TUI/model evidence."""
    from hermes_state import SessionDB
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    parent_home = tmp_path / 'native-parent'
    child_home = tmp_path / 'target'
    parent_home.mkdir()
    child_home.mkdir()
    token = set_hermes_home_override(parent_home)
    parent = SessionDB(parent_home / 'state.db')
    child = SessionDB(child_home / 'state.db')
    try:
        parent.create_session('p0', source='discord', profile_name='parent', session_key='lane')
        child.create_session('c0', source='profile-delegate', profile_name='worker')
        original = {'session_id': 'p0', 'session_key': 'lane', 'source': 'discord', 'profile': 'parent'}
        first = dispatch_fixture(original)
        run = core.resolve_run_dir(first['task_id'])
        for index in range(1, 4):
            for db, prefix, source, profile in ((parent, 'p', 'discord', 'parent'), (child, 'c', 'profile-delegate', 'worker')):
                before, after = f'{prefix}{index - 1}', f'{prefix}{index}'
                holder = f'fixture-{prefix}{index}'
                assert db.try_acquire_compression_lock(before, holder)
                db.publish_compression_child(parent_session_id=before, child_session_id=after, source=source,
                                             profile_name=profile, compression_lock_holder=holder,
                                             messages=[{'role': 'user', 'content': f'POST_ROTATION_{prefix}{index}'}])
                db.release_compression_lock(before, holder)
            caller = {**original, 'session_id': f'p{index}'}
            assert dispatch_fixture(caller)['task_id'] == first['task_id']
            assert core.profile_delegate_list(caller_origin=caller)['count'] == 1
            assert core.authorize_run('control', caller, core.read_json_file(run / 'status.json')) == 'compression'
            assert core.compression_continuation(child_home, 'c0', f'c{index}', profile='worker', ui_correlated=True)
            core.merge_run_status(run, {'child_session_id': f'c{index}'})
        assert child.resolve_resume_session_id('c0') == 'c3'
        assert child.get_messages('c3')[0]['content'] == 'POST_ROTATION_c3'
        core.publish_terminal_run(run, {'status': 'ok', 'summary': 'both rotated', 'structured': True,
                                       'execution_status': 'completed', 'contract_status': 'valid', 'session_id': 'c3'},
                                  {'status': 'completed', 'child_session_id': 'c3'})
        observed = core.profile_delegate_status(first['task_id'], caller_origin=caller)
        assert observed['child_session_id'] == 'c3'
        assert observed['result']['session_id'] == 'c3'
        assert observed['origin'] == core.normalize_origin(original)
        # A native-created branch is not compression, even on the same lane.
        parent.create_session('branch', source='discord', profile_name='parent', session_key='lane',
                              parent_session_id='p3', model_config={'_branched_from': 'p3'})
        with pytest.raises(core.ProfileDelegateError):
            core.authorize_run('control', {**caller, 'session_id': 'branch'}, core.read_json_file(run / 'status.json'))
    finally:
        child.close()
        parent.close()
        reset_hermes_home_override(token)


def test_detached_notification_watcher_keeps_context_home(tmp_path, monkeypatch):
    """Fake process exit, real native ledger: demonstrate named-home ownership."""
    import threading
    from hermes_state import SessionDB
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from tools import async_delegation
    launch, caller = tmp_path / 'launch', tmp_path / 'caller'
    launch.mkdir()
    caller.mkdir()
    for home in (launch, caller):
        with SessionDB(home / 'state.db'):
            pass
    monkeypatch.setenv('HERMES_HOME', str(launch))
    monkeypatch.setenv('PROFILE_DELEGATE_RUNS_ROOT', str(caller / 'runs'))
    monkeypatch.setenv('PROFILE_DELEGATE_LOCKS_ROOT', str(caller / 'locks'))
    monkeypatch.setattr(core, 'child_environment', lambda *args: {})
    run = caller / 'runs' / 'pd_20260930_120000_notify'
    run.mkdir(parents=True)
    core.json_safe_write(run / 'request.json', {'task_id': run.name, 'profile': 'worker',
                        'effective_policy': {'limits': {'max_async': 4}},
                        'notify_on_complete': True, 'origin_session_key': 'lane'})
    core.json_safe_write(run / 'status.json', {'task_id': run.name, 'status': 'running'})
    released = threading.Event()
    done = threading.Event()
    class Process:
        pid = 99999999
        def wait(self):
            assert released.wait(5)
            return 0
    monkeypatch.setattr(core.subprocess, 'Popen', lambda *args, **kwargs: Process())
    native_push = core._push_profile_delegate_completion
    def observed_push(*args):
        try:
            native_push(*args)
        finally:
            done.set()
    monkeypatch.setattr(core, '_push_profile_delegate_completion', observed_push)
    token = set_hermes_home_override(caller)
    try:
        assert core._register_durable_notification(run)
        core._start_detached_background_worker(run)
        core.publish_terminal_run(run, {'status': 'ok', 'summary': 'notification home fixture', 'structured': True,
                                       'execution_status': 'completed', 'contract_status': 'valid'}, {'status': 'completed'})
        released.set()
        assert done.wait(5)
        record = async_delegation.get_durable_delegation(run.name)
        assert record['state'] == 'completed'
        assert record['delivery_state'] == 'pending'  # enqueue is NOT consumption
        with closing(sqlite3.connect(launch / 'state.db')) as db:
            assert db.execute('SELECT COUNT(*) FROM async_delegations').fetchone()[0] == 0
    finally:
        released.set()
        reset_hermes_home_override(token)





def test_cli_native_source_rotation_is_footer_only(tmp_path):
    database(tmp_path, [row('a', reason='compression', source='profile-delegate', lane=None),
                        row('b', 'a', reason='compression', source='cli', lane=None),
                        row('c', 'b', source='cli', lane=None)], profiles={'a':'worker','b':'worker','c':'worker'})
    assert not core.compression_continuation(tmp_path, 'a', 'c', profile='worker')
    assert core.compression_continuation(tmp_path, 'a', 'c', profile='worker', cli_footer=True)
    assert not core.compression_continuation(tmp_path, 'a', 'c', profile='worker', source='profile-delegate', cli_footer=True)
    with closing(sqlite3.connect(tmp_path / 'state.db')) as db:
        db.execute("UPDATE sessions SET source='discord' WHERE id='b'")
        db.commit()
    assert not core.compression_continuation(tmp_path, 'a', 'c', profile='worker', cli_footer=True)
