"""Regressions from independent F1–F5 review; real Git, isolated provider seams."""
import json
from pathlib import Path

import pytest
import core
import worktrees
from test_worktrees import repository as workspace_fixture, launch, command

repository = workspace_fixture

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('driver', ['smudge', 'process'])
def test_external_filter_rejected_before_resources(repository, driver):
    root = repository
    (root / '.gitattributes').write_text('base.txt filter=probe\n')
    command(root, 'add', '.gitattributes')
    command(root, 'commit', '-qm', 'attributes')
    marker = root.parent / 'filter-ran'
    command(root, 'config', 'filter.probe.' + driver, f'printf ran > {marker}; /bin/cat')
    before = (root / '.git/config').read_bytes()
    branches = command(root, 'branch', '--list')
    with pytest.raises(core.ProfileDelegateError) as error:
        launch(root, worktree=True)
    assert error.value.code == 'workspace_external_filter'
    assert not marker.exists()
    assert not (root.parent / '.profile-delegate-worktrees').exists()
    assert not list(core.get_runs_root().glob('pd_*'))
    assert command(root, 'branch', '--list') == branches
    assert (root / '.git/config').read_bytes() == before


@pytest.mark.parametrize('batch_mode', [False, True])
def test_created_fact_survives_request_publication_failure(repository, monkeypatch, batch_mode):
    original = core.json_safe_write
    def write(path, value):
        if Path(path).name == 'request.json' and Path(path).exists():
            raise OSError('fixture request publication failure')
        return original(path, value)
    monkeypatch.setattr(core, 'json_safe_write', write)
    monkeypatch.setattr(core, '_persist_profile_delegate_completion', lambda *a: None)
    if batch_mode:
        import batch
        from test_preflight_contract import _plugin
        schema = _plugin()._multischema()['parameters']['properties']['tasks']['items']
        result = batch.multidelegate({'tasks': [dict(profile='worker', task='bounded', session_title='fixture', workdir=str(repository), worktree=True)]}, schema,
                                    {'session_key': 'cli:fixture', 'session_id': 'parent'})
        details = result['items'][0]
    else:
        with pytest.raises(core.ProfileDelegateError) as error:
            launch(repository, worktree=True)
        details = error.value.details
    assert details['workspace']['preparation_state'] == 'created'
    assert Path(details['workspace']['destination']).is_dir()
    assert details['publication_error']


@pytest.mark.parametrize('worker', [False, True])
def test_retry_refusal_retains_identity_and_association(repository, monkeypatch, worker):
    start = launch(repository, worktree=True)
    run = Path(start['paths']['request']).parent
    calls = []
    def process(cmd, **kw):
        calls.append(cmd)
        core.text_safe_write(kw['stdout_path'], 'temporary failure\nsession_id: native-child\n')
        core.text_safe_write(kw['stderr_path'], '')
        return dict(exit_code=1, timed_out=False, stdout_truncated=False, stderr_truncated=False)
    monkeypatch.setattr(core, 'run_capped_subprocess', process)
    monkeypatch.setattr(core, 'classify_transient_failure', lambda **kw: 'fixture-transient')
    monkeypatch.setattr(core, '_wait_for_transient_resume', lambda *a: 'ready')
    monkeypatch.setattr(worktrees, 'native_cwd', lambda *a: repository)
    completions = []
    monkeypatch.setattr(core, '_persist_profile_delegate_completion', lambda run, final: completions.append(final))
    if worker:
        monkeypatch.setattr(core, '_register_durable_notification', lambda *a: None)
        core._background_worker_main(str(run))
        final = completions[-1]
    else:
        final = core._execute_delegate_run(run)
    status = core.read_json_file(run / 'status.json')
    assert len(calls) == 1
    assert final['error_code'] == 'workspace_continuity_error'
    assert status['child_session_id'] == 'native-child'
    assert len(status['recovery_history']) == 1
    target = core.ValidatedProfile('worker', 'worker', status['profile_home'])
    assert core._resume_record_matches(core.read_json_file(run / 'request.json'), status, target, 'native-child')
    monkeypatch.setattr(worktrees, 'native_cwd', lambda *a: Path(status['workdir']))
    retained = worktrees.resume(target, 'native-child', status['origin'], '', core.load_effective_policy())
    assert retained['workspace'] == start['workspace']


def test_worker_failure_final_and_completion_include_workspace(repository, monkeypatch):
    start = launch(repository, worktree=True)
    run = Path(start['paths']['request']).parent
    final = core._mark_background_worker_failure(run, core.ProfileDelegateError('fixture', 'workspace_continuity_error'))
    assert final['workspace'] == start['workspace']
    assert not final['success']
    assert core.read_json_file(run / 'result.json')['workspace'] == start['workspace']
    event, completion = core._profile_delegate_completion_payload(run, final)
    assert completion['workspace'] == start['workspace']
    assert event['status'] != 'completed'


@pytest.mark.parametrize('damage', ['utf8', 'symlink', 'large', 'fifo'])
def test_shared_resume_scan_is_bounded_and_ignores_foreign(repository, monkeypatch, damage, request):
    start = launch(repository, worktree=True)
    run = Path(start['paths']['request']).parent
    core.merge_run_status(run, {'child_session_id': 'child'})
    bad = core.get_runs_root() / 'pd_foreign'
    bad.mkdir()
    request_path = bad / 'request.json'
    if damage == 'utf8':
        request_path.write_bytes(b'\xff')
    elif damage == 'symlink':
        request_path.symlink_to(run / 'request.json')
    elif damage == 'large':
        request_path.write_bytes(b' ' * 1_048_577)
    else:
        import os
        os.mkfifo(request_path)
        # Runtime package stamping reads plugin files; never retain a test FIFO.
        request.addfinalizer(lambda: request_path.unlink(missing_ok=True))
    (bad / 'status.json').write_text('{}')
    target = core.ValidatedProfile('worker', 'worker', core.read_json_file(run / 'request.json')['profile_home'])
    assert len(core.matching_resume_records(target, 'child')) == 1
    (bad / 'status.json').write_text(json.dumps({'child_session_id': 'child'}))
    with pytest.raises(core.ProfileDelegateError, match='Relevant resume evidence'):
        core.matching_resume_records(target, 'child')


@pytest.mark.parametrize('caller,allowed', [('parent', True), ('foreign', False), ('compressed', True)])
def test_generic_resume_authorizes_before_frozen_yolo(repository, monkeypatch, caller, allowed):
    from test_compression_continuity import database, row
    home = repository.parent / 'caller'
    database(home, [row('parent', reason='compression', source='cli', lane='cli:fixture'),
                    row('compressed', 'parent', source='cli', lane='cli:fixture'),
                    row('foreign', source='cli', lane='cli:fixture')])
    monkeypatch.setattr(core, 'get_hermes_home_path', lambda: home)
    start = launch(repository)
    run = Path(start['paths']['request']).parent
    stored = core.read_json_file(run / 'request.json')
    stored['native_approval'] = core.native_approval.snapshot('yolo', 'task', str(home), stored['profile_home'], {}, {})
    stored['child_approval_mode'] = 'yolo'
    core.json_safe_write(run / 'request.json', stored)
    status = core.read_json_file(run / 'status.json')
    core.json_safe_write(run / 'status.json', {**status, 'child_session_id': 'native-child', 'status': 'completed'})
    before = (run / 'request.json').read_bytes()
    original = core.resolve_request_approval
    consumed = []
    def approval(*args, **kwargs):
        consumed.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(core, 'resolve_request_approval', approval)
    args = dict(profile='worker', task='continue', session_title='resume', session_mode='resume',
                session_id='native-child', workdir=str(repository), preflight=True,
                origin={'session_key': 'cli:fixture', 'session_id': caller})
    if allowed:
        result = core.delegate_profile(**args)
        assert result['approval_policy'] == stored['native_approval']
        assert consumed == [True]
    else:
        with pytest.raises(core.ProfileDelegateError) as error:
            core.delegate_profile(**args)
        assert error.value.code == 'origin_mismatch'
        assert not consumed
    assert (run / 'request.json').read_bytes() == before
    assert len(list(core.get_runs_root().glob('pd_*'))) == 1


def test_worktree_moved_ref_is_not_duplicate(repository, monkeypatch):
    monkeypatch.setenv('PROFILE_DELEGATE_MAX_CONCURRENT', '3')
    monkeypatch.setenv('PROFILE_DELEGATE_MAX_ASYNC', '3')
    first = launch(repository, worktree=True)
    assert launch(repository, worktree=True)['task_id'] == first['task_id']
    command(repository, 'add', 'base.txt')
    command(repository, 'commit', '-qm', 'advance base')
    moved_sha = command(repository, 'rev-parse', 'HEAD')
    second = launch(repository, worktree=True)
    assert not second['deduplicated']
    assert second['task_id'] != first['task_id']
    assert second['workspace']['initial_sha'] == moved_sha
    assert command(Path(second['workspace']['destination']), 'rev-parse', 'HEAD') == moved_sha


def test_worktree_preparation_keeps_admitted_sha_when_ref_moves(repository, monkeypatch):
    admitted_sha = command(repository, 'rev-parse', 'HEAD')
    original = worktrees.prepare
    def prepare(request, run_dir, policy):
        command(repository, 'add', 'base.txt')
        command(repository, 'commit', '-qm', 'move between admission and preparation')
        return original(request, run_dir, policy)
    monkeypatch.setattr(worktrees, 'prepare', prepare)
    result = launch(repository, worktree=True)
    assert command(repository, 'rev-parse', 'HEAD') != admitted_sha
    assert result['workspace']['initial_sha'] == admitted_sha
    assert command(Path(result['workspace']['destination']), 'rev-parse', 'HEAD') == admitted_sha


@pytest.mark.parametrize('field', ['background', 'notify_on_complete', 'preflight', 'worktree'])
@pytest.mark.parametrize('value', ['false', 'true', 0, 1, None, [], {}])
@pytest.mark.parametrize('entry', ['handler', 'core'])
def test_single_admission_rejects_non_boolean(repository, monkeypatch, field, value, entry):
    from test_preflight_contract import _plugin
    args = dict(profile='worker', task='bounded', session_title='booleans', workdir=str(repository),
                background=True, notify_on_complete=False, transport_mode='simple', preflight=True)
    args[field] = value
    monkeypatch.setattr(core, '_start_background_run', lambda *a: pytest.fail('invalid boolean launched a child'))
    monkeypatch.setattr(core, '_execute_delegate_run', lambda *a: pytest.fail('invalid boolean launched a child'))
    if entry == 'handler':
        result = json.loads(_plugin()._handler(args))
        assert result['error_code'] == 'validation_error'
        assert field + ' must be a boolean' in result['error']
    else:
        with pytest.raises(core.ProfileDelegateError, match=field + ' must be a boolean') as error:
            core.delegate_profile(**args)
        assert error.value.code == 'validation_error'
    assert not list(core.get_runs_root().glob('pd_*'))


@pytest.mark.parametrize('entry', ['handler', 'core'])
@pytest.mark.parametrize('background,notify', [(False, False), (True, True)])
def test_single_admission_preserves_boolean_values(repository, entry, background, notify):
    from test_preflight_contract import _plugin
    args = dict(profile='worker', task='bounded', session_title='booleans', workdir=str(repository),
                background=background, notify_on_complete=notify, transport_mode='simple', preflight=True)
    result = json.loads(_plugin()._handler(args)) if entry == 'handler' else core.delegate_profile(**args)
    assert result['success']
    assert result['normalized_request']['background'] is background
    assert result['normalized_request']['notify_on_complete'] is notify
    assert not list(core.get_runs_root().glob('pd_*'))
