"""Real Git workspace and admission regressions; native seams explicitly isolated."""
import json
from pathlib import Path
import subprocess

import pytest

import core
import worktrees
from test_preflight_contract import _plugin
from test_profile_delegate import mock_delegate_admission

pytestmark = pytest.mark.integration


def command(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


@pytest.fixture
def repository(tmp_path, monkeypatch):
    root = tmp_path / 'source'
    root.mkdir()
    command(root, 'init', '-q')
    command(root, 'config', 'user.email', 'fixture@example.invalid')
    command(root, 'config', 'user.name', 'Fixture')
    (root / 'base.txt').write_text('committed')
    command(root, 'add', 'base.txt')
    command(root, 'commit', '-qm', 'fixture')
    (root / 'base.txt').write_text('dirty')
    (root / 'untracked').write_text('not included')
    mock_delegate_admission(tmp_path, monkeypatch, hermes_bin='/usr/bin/hermes')
    monkeypatch.setattr(core, 'resolve_workdir', lambda workdir='', policy=None: Path(workdir).resolve())
    monkeypatch.setenv('PROFILE_DELEGATE_ALLOWED_WORKDIRS', str(tmp_path))
    monkeypatch.setattr(core, '_start_background_run', lambda directory: None)
    monkeypatch.setattr(core, 'require_native_async_ledger_compatibility', lambda: {})
    # Admission fixtures do not grant production parent authority.
    from tools import approval
    monkeypatch.setattr(approval, 'check_all_command_guards', lambda *a: {'approved': True})
    return root


def launch(root, **kw):
    return core.delegate_profile(profile='worker', task='bounded change', session_title='workspace',
                                 workdir=str(root), background=True, notify_on_complete=False,
                                 transport_mode='simple', origin={'session_key': 'cli:fixture', 'session_id': 'parent'}, **kw)


def test_creation_dirty_exclusion_dedupe_and_status(repository):
    root = repository
    before = command(root, 'status', '--porcelain')
    dry = launch(root, worktree=True, branch='feature', preflight=True)
    assert dry['workspace']['preparation_state'] == 'planned'
    assert 'destination' not in dry['workspace']
    assert not (root.parent / '.profile-delegate-worktrees').exists()
    result = launch(root, worktree=True, branch='feature')
    workspace = result['workspace']
    dest = Path(workspace['destination'])
    assert workspace['preparation_state'] == 'created'
    assert (dest / 'base.txt').read_text() == 'committed'
    assert not (dest / 'untracked').exists()
    assert command(root, 'status', '--porcelain') == before
    assert command(dest, 'rev-parse', 'HEAD') == workspace['initial_sha']
    assert command(dest, 'branch', '--show-current') == 'feature'
    assert json.loads(Path(result['paths']['request']).read_text())['workdir'] == str(dest)
    assert launch(root, worktree=True, branch='feature', preflight=True)['success']
    reused = launch(root, worktree=True, branch='feature')
    assert reused['deduplicated'] and reused['task_id'] == result['task_id']
    assert reused['workspace'] == workspace
    status = core.profile_delegate_status(result['task_id'], caller_origin={'session_key': 'cli:fixture', 'session_id': 'parent'})
    assert status['workspace'] == workspace
    with pytest.raises(core.ProfileDelegateError) as error:
        launch(root, worktree=True, branch='feature', duplicate_policy='new')
    assert error.value.details['run_created'] and error.value.details['workspace']['preparation_state'] == 'unknown'
    assert dest.exists()


@pytest.mark.parametrize('args', [dict(worktree='true'), dict(worktree=1), dict(base_ref='HEAD'),
                                  dict(worktree=True, base_ref=''), dict(worktree=True, base_ref='--help'),
                                  dict(worktree=True, branch='--help'), dict(worktree=True, branch='bad..name'),
                                  dict(worktree=True, capability_preset='review')])
def test_options_rejected_without_workspace(repository, args):
    with pytest.raises(core.ProfileDelegateError):
        launch(repository, preflight=True, **args)
    assert not (repository.parent / '.profile-delegate-worktrees').exists()


def test_source_policy_symlink_and_parent_denial(repository, monkeypatch):
    root = repository
    sub = root / 'sub'
    sub.mkdir()
    with pytest.raises(core.ProfileDelegateError, match='exact'):
        launch(sub, worktree=True, preflight=True)
    monkeypatch.setenv('PROFILE_DELEGATE_ALLOWED_WORKDIRS', str(root))
    with pytest.raises(core.ProfileDelegateError, match='not under'):
        launch(root, worktree=True, preflight=True)
    monkeypatch.setenv('PROFILE_DELEGATE_ALLOWED_WORKDIRS', str(root.parent))
    from tools import approval
    monkeypatch.setattr(approval, 'check_all_command_guards', lambda *a: {'approved': False, 'message': 'parent denied'})
    with pytest.raises(core.ProfileDelegateError, match='parent denied') as error:
        launch(root, worktree=True)
    assert error.value.code == 'workspace_approval_required'
    assert not (root.parent / '.profile-delegate-worktrees').exists()


def test_batch_projects_workspace_and_partial_failure(repository, monkeypatch):
    import batch
    root = repository
    monkeypatch.setenv('PROFILE_DELEGATE_MAX_CONCURRENT', '3')
    monkeypatch.setenv('PROFILE_DELEGATE_MAX_ASYNC', '3')
    monkeypatch.setattr(core, '_persist_profile_delegate_completion', lambda *a: None)
    schema = _plugin()._multischema()['parameters']['properties']['tasks']['items']
    tasks = [dict(profile='worker', task=f'change {i}', session_title='batch worktree', workdir=str(root),
                  worktree=True, base_ref=command(root, 'rev-parse', 'HEAD'), branch=f'batch-{i}') for i in range(3)]
    origin = {'session_key': 'cli:fixture', 'session_id': 'parent'}
    dry = batch.multidelegate({'tasks': tasks, 'preflight': True}, schema, origin)
    assert all(i['workspace']['preparation_state'] == 'planned' for i in dry['items'])
    assert not (root.parent / '.profile-delegate-worktrees').exists()
    calls = []
    def start(directory):
        calls.append(directory)
        if len(calls) == 2:
            raise RuntimeError('fixture launch failed')
    monkeypatch.setattr(core, '_start_background_run', start)
    result = batch.multidelegate({'tasks': tasks}, schema, origin)
    assert result['status'] == 'partial'
    assert [i['dispatch_status'] for i in result['items']] == ['started', 'failed', 'not_started']
    for item in result['items'][:2]:
        assert item['workspace']['preparation_state'] == 'created'
        assert Path(item['workspace']['destination']).is_dir()
    assert result['items'][0]['workspace']['destination'] != result['items'][1]['workspace']['destination']
    assert json.loads((calls[0] / 'status.json').read_text())['status'] == 'running'


def test_resume_checks_native_cwd_not_original_branch(repository, monkeypatch):
    root = repository
    launched = launch(root, worktree=True)
    path = Path(launched['paths']['status'])
    status = json.loads(path.read_text())
    status.update(child_session_id='native-child', status='completed')
    path.write_text(json.dumps(status))
    dest = Path(launched['workspace']['destination'])
    command(dest, 'checkout', '--detach', '-q')
    monkeypatch.setattr(worktrees, 'native_cwd', lambda *a: dest)
    target = core.ValidatedProfile('worker', 'worker', str(root.parent / 'worker'))
    origin = {'session_key': 'cli:fixture', 'session_id': 'parent'}
    request = worktrees.resume(target, 'native-child', origin, '', core.load_effective_policy())
    assert request['workdir'] == str(dest)
    with pytest.raises(core.ProfileDelegateError, match='retained'):
        worktrees.resume(target, 'native-child', origin, str(root), core.load_effective_policy())
    with pytest.raises(core.ProfileDelegateError):
        worktrees.resume(target, 'native-child', {'session_id': 'foreign'}, '', core.load_effective_policy())
    monkeypatch.setattr(worktrees, 'native_cwd', lambda *a: root)
    with pytest.raises(core.ProfileDelegateError, match='native cwd'):
        worktrees.before_continue(request, 'native-child')


def test_generic_never_calls_git(repository, monkeypatch):
    monkeypatch.setattr(worktrees, 'git', lambda *a: pytest.fail('generic delegation must not consult Git'))
    result = launch(repository, preflight=True)
    assert result['success'] and 'workspace' not in result


def test_git_failure_after_effect_retains_observed_created_workspace(repository, monkeypatch):
    original = worktrees.git
    def failing(root, *args, **kwargs):
        result = original(root, *args, **kwargs)
        if args[:2] == ('worktree', 'add'):
            raise core.ProfileDelegateError('lost acknowledgement after Git effect', 'workspace_error')
        return result
    monkeypatch.setattr(worktrees, 'git', failing)
    with pytest.raises(core.ProfileDelegateError) as error:
        launch(repository, worktree=True)
    details = error.value.details
    assert details['run_created'] and details['workspace']['preparation_state'] == 'created'
    assert Path(details['workspace']['destination']).is_dir()
    request = json.loads(Path(details['paths']['request']).read_text())
    assert request['workdir'] == details['workspace']['destination']
    assert json.loads(Path(details['paths']['status']).read_text())['status'] == 'failed'


def test_policy_symlink_escape_and_bare_are_rejected(repository, monkeypatch):
    root = repository
    outside = root.parent / 'outside'
    outside.mkdir()
    container = root.parent / '.profile-delegate-worktrees'
    container.symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv('PROFILE_DELEGATE_ALLOWED_WORKDIRS', str(root) + ',' + str(container))
    # An allowed resolved destination still must not traverse a symlink.
    with pytest.raises(core.ProfileDelegateError, match='symlink'):
        launch(root, worktree=True)
    bare = root.parent / 'bare'
    command(root, 'clone', '--bare', '-q', str(root), str(bare))
    monkeypatch.setenv('PROFILE_DELEGATE_ALLOWED_WORKDIRS', str(root.parent))
    with pytest.raises(core.ProfileDelegateError, match='non-bare'):
        launch(bare, worktree=True, preflight=True)


def test_internal_continuation_refuses_changed_native_cwd_before_process(repository, monkeypatch):
    launched = launch(repository, worktree=True)
    run = Path(launched['paths']['request']).parent
    request = json.loads((run / 'request.json').read_text())
    request.update(session_mode='resume', requested_session_id='child')
    (run / 'request.json').write_text(json.dumps(request))
    monkeypatch.setattr(worktrees, 'native_cwd', lambda *a: repository)
    monkeypatch.setattr(core, 'run_capped_subprocess', lambda *a, **kw: pytest.fail('must refuse before native launch'))
    final = core._execute_delegate_run(run)
    assert not final['success']
    assert final['error_code'] == 'workspace_continuity_error'


def test_native_readonly_resolves_effective_session_cwd(tmp_path):
    from hermes_state import SessionDB
    from contextlib import closing
    import hashlib
    database = tmp_path / 'state.db'
    with closing(SessionDB(database)) as db:
        db.create_session('workspace-native', source='cli', cwd=str(tmp_path))
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    assert worktrees.native_cwd(tmp_path, 'workspace-native') == tmp_path
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    with pytest.raises(core.ProfileDelegateError, match='unavailable'):
        worktrees.native_cwd(tmp_path, 'missing')
