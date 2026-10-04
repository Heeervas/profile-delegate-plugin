"""Producer vocabulary remains usable by both read-only consumers."""
import os
import sys

import core
import pytest
import spectator


def test_unknown_phase_is_still_rejected():
    with pytest.raises(spectator.SpectatorError, match='unknown phase'):
        spectator._validate_status({'task_id':'pd_20261002_000000_abcdef', 'status':'running', 'phase':'unexpected'})


def test_cli_producer_inspect_during_execution(tmp_path, monkeypatch):
    task_id = 'pd_20261002_000000_abcdef'
    run = tmp_path / task_id
    run.mkdir(mode=0o700)
    core.json_safe_write(run / 'status.json', {'task_id':task_id, 'status':'running'})
    real_merge = core.merge_run_status_best_effort
    phases = []

    def merge(directory, fields):
        real_merge(directory, fields)
        if fields.get('phase') in {'child_running', 'child_stopped'}:
            spectator.inspect_run(run)
            phases.append(fields['phase'])

    monkeypatch.setattr(core, 'merge_run_status_best_effort', merge)
    outcome = core.run_capped_subprocess([sys.executable, '-c', 'pass'], tmp_path,
        dict(os.environ), 2, run / 'stdout.txt', run / 'stderr.txt', run_dir=run)
    assert outcome['exit_code'] == 0
    spectator.inspect_run(run)
    assert phases and set(phases) == {'child_running'}
    assert core.read_json_file(run / 'status.json')['phase'] == 'child_stopped'
