#!/usr/bin/env python3
"""Capture startup stacks using the retained CLI envelope, without provider calls.

Usage: PYTHONPATH=/opt/hermes python scripts/diagnose_worktree_startup.py
Example: /opt/hermes/.venv/bin/python scripts/diagnose_worktree_startup.py
Runs only native --help in the observed disposable checkout. Does not replay task.
"""
from pathlib import Path
import importlib.util
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.artifacts/worktree-mvp/real-acceptance'
spec = importlib.util.spec_from_file_location('worktree_startup_probe', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
core = sys.modules[spec.name + '.core']
launch = json.loads((OUT / 'cli-new.launch.json').read_text())
run = Path(launch['paths']['request']).parent
request = core.operator_read_json(run / 'request.json')
args = core.execution.bootstrap_command(request, run)
args[args.index('--events-path') + 1] = str(OUT / 'diagnostic-approval-events.jsonl')
args += ['--', request['hermes_bin'], '-p', request['profile'], '--help']
wrapper = 'import faulthandler,runpy,sys;faulthandler.dump_traceback_later(15,repeat=False);p=sys.argv[1];sys.argv=sys.argv[1:];runpy.run_path(p,run_name="__main__")'
command = [args[0], '-c', wrapper, *args[1:]]
env = core.prepare_child_environment(request, run)
try:
    result = subprocess.run(command, cwd=request['workdir'], env=env, text=True, capture_output=True, timeout=28)
    observed = {'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
except subprocess.TimeoutExpired as exc:
    observed = {'timed_out': True, 'stdout': (exc.stdout or b'').decode(errors='replace'), 'stderr': (exc.stderr or b'').decode(errors='replace')}
(OUT / 'startup-diagnostic.json').write_text(json.dumps(observed, indent=2) + '\n')
print(json.dumps(observed, indent=2))
