"""Compare derived analyzer with a supplied immutable reference over real Git states.
Usage: python scripts/verify_analyzer_equivalence.py REFERENCE_SCRIPT OUTPUT_JSON
Reference must be the recorded upstream snapshot, not another derived copy.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / '.agents/quality-tooling/vendor/scripts/quality_report.py'


def report(script, repo, policy, base):
    result = subprocess.run([sys.executable, str(script), '--repo', str(repo), '--base', base,
                             '--scope', 'all', '--level', 'top', '--config', str(policy)],
                            capture_output=True, text=True)
    return result.returncode, json.loads(result.stdout) if result.stdout else result.stderr


def compare(reference, repo, policy, base, results, name):
    before = report(reference, repo, policy, base)
    after = report(VENDOR, repo, policy, base)
    assert before == after, (name, before, after)
    results.append({'case': name, 'exit': after[0], 'equal': True})
    return after[1]


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def source_cases(reference, repo, policy, base, results):
    for name, content in [('ordinary', 'x=2\n'), ('malformed', 'def broken(:\n'),
                          ('new-strong', 'def f(x):\n' + ''.join(f'    if x=={i}: return {i}\n' for i in range(20)))]:
        (repo / 'sample.py').write_text(content)
        compare(reference, repo, policy, base, results, name)
    (repo / 'sample.py').write_text('x=1\n')
    git(repo, 'mv', 'sample.py', 'renamed.py')
    compare(reference, repo, policy, base, results, 'rename')
    (repo / 'renamed.py').unlink()
    compare(reference, repo, policy, base, results, 'deleted')
    (repo / 'renamed.py').write_text('x=1\n')
    (repo / 'link.py').symlink_to('renamed.py')
    compare(reference, repo, policy, base, results, 'symlink-gap')
    (repo / 'link.py').unlink()


def external_cases(reference, repo, policy, base, results, original):
    for implementation in ['external_findings_v1', 'external_metrics_v2']:
        current = copy.deepcopy(original)
        current['scope']['languages'] = ['javascript']
        current['adapters'] = [original['adapters'][0], {'id': 'external', 'type': 'external_json',
            'implementation': implementation, 'languages': ['javascript'], 'required_at': 'standard', 'paths': ['evidence.json']}]
        policy.write_text(json.dumps(current))
        (repo / 'sample.js').write_text('let x=1;\n')
        missing = compare(reference, repo, policy, base, results, implementation + '-missing')
        payload = {'schema_version': '1.0' if implementation == 'external_findings_v1' else '2.0',
                   'adapter_id': 'external', 'adapter_version': '1', 'metric_spec': 'fixture_v1.complexity',
                   'tool_name': 'fixture', 'tool_version': '1', 'source_snapshot': missing['repository']['current'],
                   'coverage': {'files': [{'path': 'sample.js', 'language': 'javascript'}]}}
        if implementation == 'external_findings_v1':
            payload['findings'] = []
        else:
            payload.update(baseline_commit=base, measurements=[])
        artifact = repo / 'evidence.json'
        artifact.write_text(json.dumps(payload))
        valid = compare(reference, repo, policy, base, results, implementation + '-valid')
        assert valid['quality_status'] == 'QUALITY_PASS', valid
        item = {'metric': 'fixture_v1.complexity', 'path': 'sample.js', 'language': 'javascript',
                'symbol': 'f', 'symbol_kind': 'function', 'current': 20, 'baseline': None,
                'mapping_status': 'NEW', 'message': 'independent fixture'}
        current['thresholds']['fixture_v1.complexity'] = {'warning': 10, 'strong': 15}
        policy.write_text(json.dumps(current))
        payload['source_snapshot'] = report(reference, repo, policy, base)[1]['repository']['current']
        if implementation == 'external_findings_v1':
            item['severity'] = 'strong'
            payload['findings'] = [item]
        else:
            payload['measurements'] = [item]
        artifact.write_text(json.dumps(payload))
        strong = compare(reference, repo, policy, base, results, implementation + '-strong')
        assert strong['quality_status'] == 'QUALITY_FAIL', strong
        for key, value in [('source_snapshot', 'stale'), ('coverage', {'files': []})]:
            bad = {**payload, key: value}
            artifact.write_text(json.dumps(bad))
            compare(reference, repo, policy, base, results, implementation + '-' + key)
        artifact.write_text('{malformed')
        compare(reference, repo, policy, base, results, implementation + '-malformed')
        artifact.unlink()
        current['adapters'][1]['paths'] = ['../escape.json']
        policy.write_text(json.dumps(current))
        compare(reference, repo, policy, base, results, implementation + '-escape')


def main():
    reference = Path(sys.argv[1]).resolve()
    results = []
    original = json.loads(subprocess.check_output([sys.executable, '-c',
        'import yaml,json,sys;print(json.dumps(yaml.safe_load(open(sys.argv[1]))))', str(ROOT / '.agents/quality.yaml')], text=True))
    with tempfile.TemporaryDirectory(prefix='quality-equivalence-', dir=os.environ.get('TMPDIR')) as temp:
        repo = Path(temp)
        git(repo, 'init', '-q')
        git(repo, 'config', 'user.email', 'quality@example.invalid')
        git(repo, 'config', 'user.name', 'Quality fixture')
        (repo / 'sample.py').write_text('x=1\n')
        git(repo, 'add', '.')
        git(repo, 'commit', '-qm', 'fixture baseline')
        base = git(repo, 'rev-parse', 'HEAD')
        policy = repo / 'policy.json'
        policy.write_text(json.dumps(original))
        source_cases(reference, repo, policy, base, results)
        external_cases(reference, repo, policy, base, results, original)
    compare(reference, ROOT, ROOT / '.agents/quality.yaml', original['baseline']['ref'], results, 'exact-candidate-with-exception')
    Path(sys.argv[2]).write_text(json.dumps({'reference_sha256': hashlib.sha256(reference.read_bytes()).hexdigest(),
        'cases': results, 'all_equal': True}, indent=2) + '\n')


if __name__ == '__main__':
    main()
