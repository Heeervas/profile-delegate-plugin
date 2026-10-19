#!/usr/bin/env python3
"""Synchronize release metadata. Usage: python scripts/release_version.py --base-version 1.11.0 --bump minor.

Run in a disposable checkout; retry with the SAME base and bump. No Git/network writes.
"""
from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ('plugin.yaml', 'pyproject.toml', 'README.md', 'CHANGELOG.md', 'uv.lock')


def semver(value: str) -> tuple[int, int, int]:
    if not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value):
        raise ValueError(f'invalid stable semver: {value!r}')
    major, minor, patch = map(int, value.split('.'))
    return major, minor, patch


def next_version(base: str, bump: str) -> str:
    parts = list(semver(base))
    index = {'major': 0, 'minor': 1, 'patch': 2}[bump]
    parts[index] += 1
    parts[index + 1:] = [0] * (2 - index)
    return '.'.join(map(str, parts))


def metadata_version(root: Path) -> str:
    version = tomllib.loads((root / 'pyproject.toml').read_text())['project']['version']
    semver(version)
    manifest = re.findall(r'^version: [\"\']?([0-9.]+)[\"\']?$', (root / 'plugin.yaml').read_text(), re.M)
    readme = re.findall(r'^Version: `([^`]+)`$', (root / 'README.md').read_text(), re.M)
    lock = tomllib.loads((root / 'uv.lock').read_text())
    package = [p['version'] for p in lock['package'] if p['name'] == 'profile-delegate']
    if manifest != [version] or readme != [version] or package != [version]:
        raise ValueError('manifest/pyproject/README/uv.lock version mismatch')
    if f'## [{version}]' not in (root / 'CHANGELOG.md').read_text():
        raise ValueError('CHANGELOG release entry missing')
    if lock['requires-python'].replace(' ', '') != '>=3.11,<3.15':
        raise ValueError('uv.lock Python support mismatch')
    return version


def replace_once(text: str, pattern: str, replacement: str) -> str:
    result, count = re.subn(pattern, lambda _: replacement, text, flags=re.M)
    if count != 1:
        raise ValueError(f'expected exactly one metadata marker: {pattern}')
    return result


def synchronize(root: Path, base: str, bump: str) -> str:
    target = next_version(base, bump)
    current = metadata_version(root)
    if current == target:
        return target
    if current != base:
        raise ValueError(f'stale candidate {current}; expected {base} or retry target {target}')
    texts = {name: (root / name).read_text() for name in FILES}
    texts['plugin.yaml'] = replace_once(texts['plugin.yaml'], r'^version: .*$', f'version: "{target}"')
    texts['pyproject.toml'] = replace_once(texts['pyproject.toml'], r'^version = ".*"$', f'version = "{target}"')
    texts['README.md'] = replace_once(texts['README.md'], r'^Version: `.*`$', f'Version: `{target}`')
    texts['uv.lock'] = replace_once(texts['uv.lock'], rf'(?<=name = "profile-delegate"\n)version = "{re.escape(base)}"', f'version = "{target}"')
    changelog = texts['CHANGELOG.md']
    if f'## [{target}]' in changelog:
        raise ValueError('target changelog entry already exists before bump')
    unreleased = changelog.split('## [Unreleased]\n', 1)
    if len(unreleased) != 2 or not unreleased[1].split('\n## [', 1)[0].strip():
        raise ValueError('nonempty Unreleased release notes required')
    texts['CHANGELOG.md'] = replace_once(changelog, r'^## \[Unreleased\]$', f'## [Unreleased]\n\n## [{target}]')
    # Validate every transformation before writing any file. CI uses a disposable checkout;
    # interrupted partial writes fail consistency on retry instead of incrementing again.
    for name, text in texts.items():
        (root / name).write_text(text)
    metadata_version(root)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-version', required=True)
    parser.add_argument('--bump', choices=('patch', 'minor', 'major'), required=True)
    args = parser.parse_args()
    print(synchronize(ROOT, args.base_version, args.bump))


if __name__ == '__main__':
    main()
