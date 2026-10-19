"""Execute release orchestration in disposable Git repositories; mock GitHub/uv only.

Real quality, lock, registration and suites run separately via validation.md.
"""
import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


@pytest.fixture
def workflow(tmp_path):
    remote = tmp_path / 'origin.git'
    subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
    repo = tmp_path / 'repo'
    repo.mkdir()
    git(repo, 'init', '-b', 'main')
    git(repo, 'config', 'user.email', 'fixture@example.invalid')
    git(repo, 'config', 'user.name', 'Release fixture')
    for name in ('plugin.yaml', 'pyproject.toml', 'README.md', 'uv.lock'):
        (repo / name).write_text((ROOT / name).read_text().replace('1.12.0', '1.11.0'))
    (repo / 'CHANGELOG.md').write_text('## [Unreleased]\n\n- Worktrees\n\n## [1.11.0]\n')
    (repo / 'scripts').mkdir()
    shutil.copyfile(ROOT / 'scripts/release_version.py', repo / 'scripts/release_version.py')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'fixture base')
    git(repo, 'tag', 'v1.11.0')
    git(repo, 'remote', 'add', 'origin', str(remote))
    git(repo, 'push', 'origin', 'main', '--tags')
    git(repo, 'checkout', '--detach')
    helpers = tmp_path / 'bin'
    helpers.mkdir()
    for name, body in {'uv': 'exit 0', 'gh': 'if [ "$1 $2" = "pr list" ]; then printf "1\\n"; fi'}.items():
        p = helpers / name
        p.write_text('#!/bin/sh\n' + body + '\n')
        p.chmod(0o755)
    parsed = yaml.load((ROOT / '.github/workflows/release.yml').read_text(), Loader=yaml.BaseLoader)
    step = next(s for s in parsed['jobs']['prepare']['steps'] if s.get('id') == 'prepare')
    script = tmp_path / 'release.sh'
    script.write_text(step['run'])
    env = dict(os.environ, PATH=str(helpers) + os.pathsep + os.environ['PATH'], BASE_VERSION='1.11.0', BUMP='minor',
               GITHUB_SHA=git(repo, 'rev-parse', 'HEAD'), GITHUB_REF_NAME='main', GITHUB_OUTPUT=str(tmp_path / 'output'))
    return repo, remote, script, env


def run(workflow):
    repo, _, script, env = workflow
    return subprocess.run(['bash', str(script)], cwd=repo, env=env, capture_output=True, text=True)


def test_prepare_and_retry_reuses_exact_remote_tree(workflow):
    repo, remote, _, env = workflow
    first = run(workflow)
    assert first.returncode == 0, first.stderr
    branch = f'release/1.12.0-{env["GITHUB_SHA"]}'
    commit = git(remote, 'rev-parse', branch)
    assert git(remote, 'rev-parse', 'v1.11.0') == env['GITHUB_SHA']
    assert '1.12.0' in git(remote, 'show', f'{branch}:pyproject.toml')
    git(repo, 'checkout', '--detach', env['GITHUB_SHA'])
    retry = run(workflow)
    assert retry.returncode == 0, retry.stderr
    assert git(remote, 'rev-parse', branch) == commit


def test_stale_latest_refuses_without_push(workflow):
    repo, remote, _, env = workflow
    git(repo, 'tag', 'v1.12.0')
    result = run(workflow)
    assert result.returncode != 0
    assert git(remote, 'for-each-ref', '--format=%(refname)', 'refs/heads') == 'refs/heads/main'
    assert git(repo, 'rev-parse', 'HEAD') == env['GITHUB_SHA']


def test_existing_conflicting_branch_is_never_overwritten(workflow):
    repo, remote, _, env = workflow
    branch = f'release/1.12.0-{env["GITHUB_SHA"]}'
    git(repo, 'push', 'origin', f'HEAD:refs/heads/{branch}')
    result = run(workflow)
    assert result.returncode != 0
    assert git(remote, 'rev-parse', branch) == env['GITHUB_SHA']
