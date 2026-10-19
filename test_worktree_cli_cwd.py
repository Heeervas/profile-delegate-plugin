"""Native CLI cwd seam with real config, terminal and SessionDB; no inference."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import core
from test_worktrees import repository as workspace_fixture, launch

repository = workspace_fixture
pytestmark = pytest.mark.integration


def test_native_cli_workspace_cwd_and_resume_without_workdir(repository):
    start = launch(repository, worktree=True)
    run = Path(start['paths']['request']).parent
    request = core.read_json_file(run / 'request.json')
    home = Path(request['profile_home'])
    home.mkdir(exist_ok=True)
    other = home / 'workspace'
    other.mkdir()
    (home / 'config.yaml').write_text('terminal:\n  backend: local\n  cwd: ' + str(other) + '\n')
    config_before = (home / 'config.yaml').read_bytes()
    Path(request['workdir'], 'base.txt').write_text('F7_BASE')
    request['hermes_bin'] = '/opt/hermes/.venv/bin/hermes'
    core.json_safe_write(run / 'request.json', request)
    env = {k: v for k, v in os.environ.items() if not k.startswith(('HERMES_', 'PROFILE_DELEGATE_', 'TERMINAL_'))}
    env.update(HERMES_HOME=str(home), PYTHONPATH='/opt/hermes', TERMINAL_CWD=str(other), TERMINAL_ENV='local',
               PROFILE_DELEGATE_RUNS_ROOT=str(run.parent), PROFILE_DELEGATE_ALLOWED_WORKDIRS=str(repository.parent))
    probe = Path(__file__).parent / 'scripts/probe_worktree_cli_cwd.py'
    result = subprocess.run([sys.executable, str(probe), str(run / 'request.json'), str(run)],
                            env=env, cwd=str(other), capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(result.stdout.splitlines()[-1])
    assert evidence['native_cwd'] == request['workdir']
    assert evidence['source'] == 'cli'
    assert evidence['resume_workdir_omitted'] and not evidence['provider_called']
    assert (home / 'config.yaml').read_bytes() == config_before
    evidence_path = os.environ.get('F7_EVIDENCE_PATH')
    if evidence_path:
        Path(evidence_path).write_text(json.dumps(evidence, indent=2) + '\n')


def test_workspace_scope_refuses_remote_backend(repository):
    start = launch(repository, worktree=True)
    request = core.read_json_file(Path(start['paths']['request']))
    home = Path(request['profile_home'])
    home.mkdir(exist_ok=True)
    (home / 'config.yaml').write_text('terminal:\n  backend: ssh\n')
    with pytest.raises(core.ProfileDelegateError, match='local terminal backend'):
        core.execution.bind_cli_workspace(request)


def test_generic_cli_keeps_historical_source_and_no_in(repository):
    start = launch(repository)
    request = core.read_json_file(Path(start['paths']['request']))
    cmd = core.build_child_command(request, Path(start['paths']['request']).parent)
    assert '--in' not in cmd
    assert cmd[cmd.index('--source') + 1] == 'profile-delegate'
