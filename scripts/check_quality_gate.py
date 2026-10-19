# Enforce trusted governance and freshly measure the candidate. Usage: python check_quality_gate.py --repo . --trusted-base SHA
# Example: python ../trusted/scripts/check_quality_gate.py --repo . --trusted-base "$BASE_SHA"
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys
import tempfile

TOOLING = pathlib.Path(__file__).resolve().parents[1] / ".agents" / "quality-tooling"
sys.path.insert(0, str(TOOLING / "vendor" / "scripts"))
from validate_quality_policy import validate_policy

POLICY = ".agents/quality.yaml"
PROTECTED = (".agents/quality-tooling/", "scripts/check_quality_gate.py", ".github/workflows/quality.yml")


def git(repo: pathlib.Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)


def immutable_commit(repo: pathlib.Path, value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("baseline must be an explicit immutable 40-character Git SHA")
    resolved = git(repo, "rev-parse", "--verify", f"{value}^{{commit}}").decode().strip()
    if resolved != value:
        raise ValueError("baseline SHA must identify a commit directly")
    return resolved


def check_governance(repo: pathlib.Path, trusted_base: str) -> dict:
    immutable_commit(repo, trusted_base)
    try:
        raw = git(repo, "show", f"{trusted_base}:{POLICY}")
    except subprocess.CalledProcessError as exc:
        raise ValueError("trusted base lacks quality policy; separately reviewed governance adoption required") from exc
    schema = TOOLING / "vendor" / "schemas" / "quality-policy-v1.schema.json"
    with tempfile.TemporaryDirectory() as directory:
        path = pathlib.Path(directory) / "quality.yaml"
        path.write_bytes(raw)
        trusted = validate_policy(path, schema)
    candidate = validate_policy(repo / POLICY, schema)
    if candidate != trusted:
        raise ValueError("candidate policy differs from trusted base; separately reviewed governance change required (including exceptions/baseline)")
    names = git(repo, "ls-tree", "-r", "--name-only", "-z", trusted_base, "--", *PROTECTED).decode().split("\0")
    expected = {name for name in names if name}
    required = {"scripts/check_quality_gate.py", ".github/workflows/quality.yml", ".agents/quality-tooling/requirements.txt"}
    if not required <= expected:
        raise ValueError("trusted base lacks quality enforcement tooling; separately reviewed governance adoption required")
    current = {p.relative_to(repo).as_posix() for p in (repo / ".agents/quality-tooling").rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    current.update(required - {".agents/quality-tooling/requirements.txt"})
    if current != expected:
        raise ValueError("quality tooling inventory changed; separately reviewed governance change required")
    for name in sorted(expected):
        path = repo / name
        if path.is_symlink() or path.read_bytes() != git(repo, "show", f"{trusted_base}:{name}"):
            raise ValueError(f"protected quality tooling changed: {name}; separately reviewed governance change required")
    immutable_commit(repo, trusted["baseline"]["ref"])
    # The measurement baseline must be ancestral; the PR comparison branch may diverge.
    git(repo, "merge-base", "--is-ancestor", trusted["baseline"]["ref"], "HEAD")
    return trusted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=pathlib.Path, default=pathlib.Path("."))
    parser.add_argument("--trusted-base", required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    try:
        policy = check_governance(repo, args.trusted_base)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"QUALITY_GOVERNANCE_BLOCKED: {exc}", file=sys.stderr)
        return 3
    return subprocess.call([
        sys.executable, "-B", str(TOOLING / "vendor/scripts/quality_report.py"),
        "--repo", str(repo), "--base", policy["baseline"]["ref"], "--scope", "all", "--level", "top",
        "--config", str(repo / POLICY), "--format", "json",
    ])


if __name__ == "__main__":
    raise SystemExit(main())
