"""Batch contract regressions at the real singular admission/artifact seam."""
import json
from pathlib import Path
import pytest
import core
from test_preflight_contract import _plugin
from test_profile_delegate import mock_delegate_admission


@pytest.fixture
def setup_batch(tmp_path, monkeypatch):
    mock_delegate_admission(tmp_path, monkeypatch)
    monkeypatch.setenv('PROFILE_DELEGATE_MAX_CONCURRENT', '3')
    monkeypatch.setenv('PROFILE_DELEGATE_MAX_ASYNC', '3')
    monkeypatch.setattr(core, 'require_native_async_ledger_compatibility', lambda: {})
    monkeypatch.setattr(core, '_persist_profile_delegate_completion', lambda *a: None)
    plugin = _plugin()
    monkeypatch.setattr(plugin, '_current_origin', lambda: {'session_key': 'cli:batch', 'session_id': 'batch-parent'})
    return plugin, tmp_path


def task(**kwargs):
    return dict(profile='reviewer', task='Read only', session_title='batch', **kwargs)


def invoke(plugin, tasks, **kwargs):
    return json.loads(plugin._multihandler(dict(tasks=tasks, **kwargs), origin={'session_key': 'evil'}, session_id='not-child'))


@pytest.mark.parametrize('bad', [{'session_id': 'resume'}, {'session_mode': 'new'}, {'background': True}, {'max_turns': True}, {'task': 1}, {'origin': {}}])
def test_invalid_item_zero_runs(setup_batch, bad):
    plugin, root = setup_batch
    second = {**task(), **bad}
    result = invoke(plugin, [task(), second])
    assert result['status'] == 'rejected'
    assert [i['dispatch_status'] for i in result['items']] == ['not_started', 'failed']
    assert not list((root / 'runs').glob('pd_*'))


def test_preflight_same_profile_workdirs_and_no_writes(setup_batch, monkeypatch):
    plugin, root = setup_batch
    monkeypatch.setattr(core, 'resolve_workdir', lambda workdir='', policy=None: Path(workdir))
    dirs = [root / 'worktree-a', root / 'worktree-b']
    for directory in dirs:
        directory.mkdir()
    result = invoke(plugin, [task(workdir=str(d)) for d in dirs], preflight=True)
    assert result['status'] == 'validated'
    assert all(i['validation_status'] == 'validated' and not i['run_created'] for i in result['items'])
    assert not list((root / 'runs').glob('pd_*'))


@pytest.mark.parametrize('unexpected', [False, True])
def test_post_creation_failure_preserves_handle_and_siblings(setup_batch, monkeypatch, unexpected):
    plugin, root = setup_batch
    seen = []
    def launch(directory):
        seen.append(directory)
        if len(seen) == 2:
            if unexpected:
                raise RuntimeError('launch failed')
            raise core.ProfileDelegateError('full', 'async_limit')
    monkeypatch.setattr(core, '_start_background_run', launch)
    result = invoke(plugin, [task(duplicate_policy='new') for _ in range(3)])
    assert result['status'] == 'partial'
    assert [i['dispatch_status'] for i in result['items']] == ['started', 'failed', 'not_started']
    failed = result['items'][1]
    assert failed['run_created'] and failed['task_id'] == seen[1].name
    assert Path(failed['paths']['status']).is_file()
    assert json.loads(Path(failed['paths']['status']).read_text())['status'] == 'failed'
    first = json.loads(Path(result['items'][0]['paths']['request']).read_text())
    assert first['origin']['session_id'] == 'batch-parent'
    assert first['session_mode'] == 'new' and first['requested_session_id'] == ''


def test_schema_independence_and_registration():
    plugin = _plugin()
    a = plugin._multischema()
    a['parameters']['properties']['tasks']['items']['properties']['task']['type'] = 'bad'
    assert plugin._schema()['parameters']['properties']['task']['type'] == 'string'


@pytest.mark.parametrize('mode', ['json', 'markdown', 'text'])
def test_prompt_verified_deliverables_and_recovery(mode):
    prompt = core.build_prompt('task', 'context', '', mode)
    assert 'include every requested deliverable' in prompt
    assert 'Task:\ntask' in prompt
    recovery = core.build_recovery_prompt(3, mode, mode != 'json')
    assert 'observable state' in recovery and 'report blocked' in recovery
    assert 'final automatic recovery' in recovery


def test_review_preset_filters_actual_definitions(monkeypatch):
    import sys
    import types
    import child_bootstrap
    names = ['read_file', 'profile_delegate', 'profile_multidelegate', 'write_file']
    module = types.ModuleType('model_tools')
    module.get_tool_definitions = lambda: [{'function': {'name': name}} for name in names]
    monkeypatch.setitem(sys.modules, 'model_tools', module)
    for name in ('run_agent', 'cli'):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    child_bootstrap._install_capability_filter(core.REVIEW_BLOCKED_TOOLS, lambda **kw: None)
    assert module.get_tool_definitions() == [{'function': {'name': 'read_file'}}]


def test_dedupe_and_late_worker_rejection_are_individual(setup_batch, monkeypatch):
    plugin, root = setup_batch
    launches = []
    def launch(directory):
        launches.append(directory)
    monkeypatch.setattr(core, '_start_background_run', launch)
    result = invoke(plugin, [task(), task()])
    assert result['status'] == 'accepted'
    assert [i['dispatch_status'] for i in result['items']] == ['started', 'reused']
    assert result['items'][0]['task_id'] == result['items'][1]['task_id']
    assert len(launches) == 1
    core.publish_terminal_run(launches[0], core.failure_result('late capacity', 'concurrency_limit'),
                              {'status': 'failed', 'phase': 'failed', 'error_code': 'concurrency_limit'})
    assert result['status'] == 'accepted'  # immutable dispatch receipt, not execution success
    assert core.read_json_file(launches[0] / 'status.json')['error_code'] == 'concurrency_limit'


def test_actual_artifacts_honor_distinct_workdirs(setup_batch, monkeypatch):
    plugin, root = setup_batch
    dirs = [root / 'tree-a', root / 'tree-b']
    for d in dirs:
        d.mkdir()
    monkeypatch.setattr(core, 'resolve_workdir', lambda workdir='', policy=None: Path(workdir))
    monkeypatch.setattr(core, '_start_background_run', lambda directory: None)
    result = invoke(plugin, [task(workdir=str(d)) for d in dirs])
    assert result['status'] == 'accepted'
    assert len({i['task_id'] for i in result['items']}) == 2
    assert [core.read_json_file(Path(i['paths']['request']))['workdir'] for i in result['items']] == [str(d) for d in dirs]


def test_no_origin_or_incompatible_ledger_creates_no_runs(setup_batch, monkeypatch):
    plugin, root = setup_batch
    monkeypatch.setattr(plugin, '_current_origin', lambda: {})
    assert invoke(plugin, [task()])['error_code'] == 'origin_required'
    monkeypatch.setattr(plugin, '_current_origin', lambda: {'session_key': 'cli:batch'})
    def incompatible():
        raise core.ProfileDelegateError('incompatible', 'native_async_ledger_incompatible')
    monkeypatch.setattr(core, 'require_native_async_ledger_compatibility', incompatible)
    assert invoke(plugin, [task()])['error_code'] == 'native_async_ledger_incompatible'
    assert not list((root / 'runs').glob('pd_*'))


@pytest.mark.parametrize('publication_fails', [False, True])
def test_initial_write_failure_keeps_created_handle(setup_batch, monkeypatch, publication_fails):
    plugin, root = setup_batch
    original = core.json_safe_write
    writes = []
    def write(path, value):
        if path.name == 'request.json':
            writes.append(path.parent)
            if len(writes) == 2:
                raise OSError('initial write failed')
        return original(path, value)
    monkeypatch.setattr(core, 'json_safe_write', write)
    monkeypatch.setattr(core, '_start_background_run', lambda directory: None)
    if publication_fails:
        def fail(*args, **kwargs):
            raise OSError('terminal publication failed')
        monkeypatch.setattr(core, 'publish_terminal_run', fail)
    result = invoke(plugin, [task(duplicate_policy='new') for _ in range(3)])
    assert result['status'] == 'partial'
    assert [i['dispatch_status'] for i in result['items']] == ['started', 'failed', 'not_started']
    failed = result['items'][1]
    assert failed['run_created'] and failed['task_id'] == writes[1].name
    assert Path(failed['paths']['run_dir']).is_dir()
    if publication_fails:
        assert 'terminal publication failed' in failed['publication_error']


@pytest.mark.parametrize('payload', [{}, {'tasks': []}, {'tasks': [task()] * 4}, {'tasks': [task()], 'preflight': 'true'}, {'tasks': [task()], 'origin': {}}])
def test_root_boundaries_zero_runs(setup_batch, payload):
    plugin, root = setup_batch
    result = json.loads(plugin._multihandler(payload))
    assert result['status'] == 'rejected' and result['error_code'] == 'validation_error'
    assert not list((root / 'runs').glob('pd_*'))


def test_new_tool_registered_explicitly():
    from scripts.validate_release import FakeContext
    plugin = _plugin()
    ctx = FakeContext()
    plugin.register(ctx)
    assert 'profile_multidelegate' in ctx.tools
    rejected = json.loads(ctx.tools['profile_multidelegate']['handler']({'tasks': []}))
    assert rejected['status'] == 'rejected'


def test_overrides_preserved_per_item_and_denied_atomically(setup_batch, monkeypatch):
    plugin, root = setup_batch
    monkeypatch.setattr(core, '_start_background_run', lambda directory: None)
    result = invoke(plugin, [task(model='model-a', max_turns=2), task(model='model-b', max_turns=3)])
    assert result['status'] == 'accepted'
    requests = [core.read_json_file(Path(i['paths']['request'])) for i in result['items']]
    assert [r['requested_execution']['model'] for r in requests] == ['model-a', 'model-b']
    assert [r['requested_execution']['max_turns'] for r in requests] == [2, 3]
    before = set((root / 'runs').iterdir())
    monkeypatch.setattr(core, '_plugin_entry', lambda: {'allow_model_override': False})
    result = invoke(plugin, [task(), task(model='forbidden')])
    assert result['status'] == 'rejected'
    assert set((root / 'runs').iterdir()) == before


def test_transport_incompatibility_zero_runs(setup_batch, monkeypatch):
    plugin, root = setup_batch
    monkeypatch.setattr(core, '_background_mode', lambda: 'thread')
    result = invoke(plugin, [task()])
    assert result['status'] == 'rejected'
    assert result['items'][0]['error_code'] == 'validation_error'
    assert not list((root / 'runs').glob('pd_*'))
