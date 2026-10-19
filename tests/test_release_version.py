"""Release metadata behavior against disposable real repository-file fixtures."""
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('release_version', Path(__file__).resolve().parents[1] / 'scripts/release_version.py')
assert SPEC is not None and SPEC.loader is not None
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


@pytest.fixture
def candidate(tmp_path):
    root = Path(__file__).resolve().parents[1]
    for name in release.FILES:
        text = (root / name).read_text()
        # Start at the real existing release, not the stale local intake 1.10.0.
        if name == 'CHANGELOG.md':
            text = '# Changelog\n\n## [Unreleased]\n\n- Optional worktrees.\n\n## [1.11.0]\n\n- Multi-dispatch.\n'
        else:
            text = text.replace('1.12.0', '1.11.0')
        (tmp_path / name).write_text(text)
    assert release.metadata_version(tmp_path) == '1.11.0'
    return tmp_path


@pytest.mark.parametrize(('bump', 'target'), [('patch', '1.11.1'), ('minor', '1.12.0'), ('major', '2.0.0')])
def test_bump_and_same_input_retry(candidate, bump, target):
    assert release.synchronize(candidate, '1.11.0', bump) == target
    before = {p.name: p.read_bytes() for p in candidate.iterdir()}
    assert release.metadata_version(candidate) == target
    assert release.synchronize(candidate, '1.11.0', bump) == target
    assert before == {p.name: p.read_bytes() for p in candidate.iterdir()}


@pytest.mark.parametrize('broken', ['mismatch', 'stale', 'empty-notes', 'existing-target', 'partial-write'])
def test_reject_before_any_write(candidate, broken):
    if broken == 'mismatch':
        p = candidate / 'README.md'
        p.write_text(p.read_text().replace('1.11.0', '9.0.0'))
    elif broken == 'stale':
        for name in release.FILES:
            p = candidate / name
            p.write_text(p.read_text().replace('1.11.0', '1.10.0'))
    elif broken == 'empty-notes':
        p = candidate / 'CHANGELOG.md'
        p.write_text(p.read_text().replace('- Optional worktrees.', ''))
    elif broken == 'existing-target':
        p = candidate / 'CHANGELOG.md'
        p.write_text(p.read_text() + '\n## [1.12.0]\n')
    else:
        p = candidate / 'pyproject.toml'
        p.write_text(p.read_text().replace('1.11.0', '1.12.0'))
    before = {p.name: p.read_bytes() for p in candidate.iterdir()}
    with pytest.raises(ValueError):
        release.synchronize(candidate, '1.11.0', 'minor')
    assert before == {p.name: p.read_bytes() for p in candidate.iterdir()}


@pytest.mark.parametrize('invalid', ['v1.11.0', '01.11.0', '1.11', '1.11.0;exit', '1.11.0-rc1'])
def test_invalid_base(candidate, invalid):
    with pytest.raises(ValueError, match='invalid stable semver'):
        release.synchronize(candidate, invalid, 'minor')
