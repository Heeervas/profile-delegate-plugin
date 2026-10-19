#!/usr/bin/env python3
"""Exercise real worktree CLI/TUI creation and resume through the public handler.

Usage: PYTHONPATH=/opt/hermes /opt/hermes/.venv/bin/python scripts/accept_worktree_runtime.py PHASE
Example: ... accept_worktree_runtime.py preflight
Phases: preflight, cli-new, cli-resume, tui-new, tui-resume, inspect.
Uses the existing empty profile and its configured real provider. Never changes
permissions, environment lineage, profiles, gateway or plugin production code.
Only the disposable fixture, normal run artifacts and native sessions are written.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.artifacts/worktree-mvp/real-acceptance'
SOURCE = OUT / 'source'


def save(name, data):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    path.chmod(0o600)


def load(name):
    return json.loads((OUT / name).read_text())


def git(*args):
    return subprocess.check_output(['git', '-C', str(SOURCE), *args], text=True).strip()


def plugin():
    spec = importlib.util.spec_from_file_location(
        'real_worktree_acceptance', ROOT / '__init__.py',
        submodule_search_locations=[str(ROOT)],
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def config_hashes():
    paths = [Path('/opt/data/config.yaml'), Path('/opt/data/profiles/empty/config.yaml')]
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.exists()}


def prepare():
    if (OUT / 'fixture.json').exists():
        return load('fixture.json')
    if SOURCE.exists():
        raise RuntimeError('Unrecorded source exists: inspect effects, do not recreate')
    SOURCE.mkdir(parents=True, mode=0o700)
    git('init', '-q')
    git('config', 'user.name', 'Disposable worktree acceptance')
    git('config', 'user.email', 'acceptance@example.invalid')
    (SOURCE / 'base.txt').write_text('WORKTREE_SHARED_BASE\n')
    (SOURCE / 'alpha.py').write_text('def alpha():\n    return 1\n')
    (SOURCE / 'beta.py').write_text('def beta():\n    return 2\n')
    git('add', 'base.txt', 'alpha.py', 'beta.py')
    git('commit', '-qm', 'Disposable shared worktree acceptance base')
    value = {'sha': git('rev-parse', 'HEAD'), 'source': str(SOURCE), 'configs': config_hashes()}
    save('fixture.json', value)
    return value


def payload(phase, fixture):
    lane = phase.split('-')[0]
    text = (
        'This is an authorized disposable runtime acceptance, not a product implementation. '
        'The empty profile has no AGENTS_empty.md; report that gap briefly if required, '
        'but operate only in the assigned disposable checkout. '
        'Do not use delegation, network, browser, execute_code or edit configuration. '
        'Use terminal pwd to observe the actual cwd. Use read_file/write_file for fixture files. '
    )
    p = dict(profile='empty', session_title=f'Worktree real {phase}',
             timeout_seconds=300, max_turns=12, output_mode='json',
             child_approval_mode='deny', capability_preset='build',
             background=lane == 'tui', notify_on_complete=False,
             transport_mode='interactive' if lane == 'tui' else 'simple',
             output_contract='JSON status ok|blocked, summary, observed_cwd, observed_marker. Only ok after actual readback.')
    if phase.endswith('new'):
        p.update(workdir=str(SOURCE), worktree=True, base_ref=fixture['sha'])
        module = 'alpha' if lane == 'cli' else 'beta'
        value = 10 if lane == 'cli' else 20
        p['task'] = text + (
            f'Read base.txt and confirm WORKTREE_SHARED_BASE. Read {module}.py. '
            f'Change ONLY {module}.py to define {module}() returning integer {value}. '
            f'Write {lane}-marker.txt containing exactly WORKTREE_{lane.upper()}_REAL. '
            'Read both changed files back. Do not commit, modify the other module or touch the source checkout. '
            'Return the actual cwd and marker in JSON.'
        )
    else:
        retained = f'{lane}-retry-new.final.json'
        first = load(retained if (OUT / retained).exists() else f'{lane}-new.final.json')
        sid = first.get('child_session_id') or first.get('session_id')
        if not sid:
            raise RuntimeError('No observed child session ID; inspect before resume')
        p.update(session_mode='resume', session_id=sid)
        p['task'] = text + (
            f'Resume verification only: read {lane}-marker.txt from this cwd and confirm '
            f'WORKTREE_{lane.upper()}_REAL. Read {"alpha" if lane == "cli" else "beta"}.py '
            f'and confirm it still returns {10 if lane == "cli" else 20}. '
            f'Write {lane}-resumed.txt containing exactly WORKTREE_{lane.upper()}_RESUMED, '
            'then read it back. Do not create another checkout, edit modules, commit or change cwd. '
            'Return actual cwd and marker in JSON.'
        )
    return p


def public_call(mod, p):
    # Record BEFORE calling; never replay an interrupted ambiguous dispatch.
    name = 'preflight' if p.get('preflight') else p['session_title'].rsplit(' ', 1)[-1]
    response_file = OUT / f'{name}.launch.json'
    if response_file.exists() and not p.get('preflight'):
        raise RuntimeError(f'Existing dispatch evidence {response_file}; inspect, do not replay')
    save(f'{name}.request.json', p)
    result = json.loads(mod._handler(p))
    save(f'{name}.launch.json', result)
    if p.get('preflight') or not result.get('task_id') or not p['background']:
        if not p.get('preflight'):
            save(f'{name}.final.json', result)
        return result
    deadline = time.monotonic() + p['timeout_seconds'] + 40
    while time.monotonic() < deadline:
        observed = json.loads(mod._status_handler({'task_id': result['task_id'], 'tail_chars': 0}))
        save(f'{name}.observed.json', observed)
        if observed.get('status') not in {'running', 'queued', 'starting'}:
            save(f'{name}.final.json', observed)
            return observed
        time.sleep(1)
    raise RuntimeError('Acceptance observation deadline; inspect retained run before any replay')


def inspect():
    records = {}
    for p in sorted(OUT.glob('*.final.json')):
        d = json.loads(p.read_text())
        workspace = d.get('workspace')
        if not workspace and d.get('task_id'):
            request = Path(d['paths']['request'])
            workspace = json.loads(request.read_text()).get('workspace')
        records[p.stem] = {k: d.get(k) for k in ('success', 'status', 'task_status', 'child_session_id', 'session_id', 'error_code')}
        records[p.stem]['workspace'] = workspace
        if workspace:
            directory = Path(workspace['destination'])
            records[p.stem]['files'] = {q.name: q.read_text() for q in sorted(directory.glob('*.txt'))}
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['preflight', 'cli-new', 'cli-resume', 'tui-new', 'tui-resume', 'inspect'])
    args = parser.parse_args()
    if args.phase == 'inspect':
        print(json.dumps(inspect(), ensure_ascii=False, indent=2))
        return 0
    fixture = prepare()
    p = payload('cli-new' if args.phase == 'preflight' else args.phase, fixture)
    if args.phase == 'preflight':
        p['preflight'] = True
    result = public_call(plugin(), p)
    if config_hashes() != fixture['configs']:
        raise RuntimeError('Configuration bytes changed; investigate before continuing')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('success') else 1


if __name__ == '__main__':
    raise SystemExit(main())
