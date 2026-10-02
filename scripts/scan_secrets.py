"""Scan tracked and explicitly named intended-new source; never private artifacts."""
import re
import subprocess
import sys
from pathlib import Path

patterns = [r'github_pat_[A-Za-z0-9_]+', r'ghp_[A-Za-z0-9]{20,}', r'sk-[A-Za-z0-9]{20,}',
            r'AKIA[0-9A-Z]{16}', r'BEGIN (?:RSA|OPENSSH|EC|DSA)? ?PRIVATE KEY']
paths = set(subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0'))
paths.update(sys.argv[1:])
hits = []
for name in sorted(paths - {''}):
    path = Path(name)
    if '.artifacts' in path.parts or '.venv' in path.parts:
        continue
    if not path.is_file():
        continue
    data = path.read_bytes()
    if b'\0' in data[:4096]:
        continue
    if any(re.search(pattern, data.decode('utf-8', 'ignore')) for pattern in patterns):
        hits.append(name)
print(f'secret_hits={len(hits)}')
for name in hits:
    print(name)
sys.exit(bool(hits))
