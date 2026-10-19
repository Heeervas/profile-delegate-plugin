"""Exercise the trusted gate against disposable real Git repositories.
Run: python -m unittest discover -s .agents/quality-tooling/tests -v
Example: QUALITY_GATE_PYTHON=/path/to/locked/python python -m unittest discover -s .agents/quality-tooling/tests
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[3]
PYTHON = os.environ.get("QUALITY_GATE_PYTHON", sys.executable)


class QualityGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "candidate"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "quality-test@example.invalid")
        self.git("config", "user.name", "Quality gate test")
        self.put("sample.py", "def answer():\n    return 42\n")
        shutil.copytree(ROOT / ".agents/quality-tooling", self.repo / ".agents/quality-tooling", ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        for name in ("scripts/check_quality_gate.py", ".github/workflows/quality.yml"):
            self.put(name, (ROOT / name).read_text())
        self.commit()
        self.baseline = self.git("rev-parse", "HEAD").strip()
        policy = self.template_policy()
        self.put(".agents/quality.yaml", yaml.safe_dump(policy))
        self.commit()
        self.base = self.git("rev-parse", "HEAD").strip()
        self.trusted = Path(self.temp.name) / "trusted"
        self.git("clone", "-q", str(self.repo), str(self.trusted))

    def template_policy(self):
        # The trusted checkout need not carry candidate's installation-specific policy.
        return {"schema_version": "1.0", "policy_id": "gate-test", "minimum_quality_expected": "top",
                "change_scope": {"default": "all", "include_untracked": True, "detect_file_renames": True},
                "scope": {"include": [], "exclude": [], "languages": ["python"]},
                "baseline": {"strategy": "merge_base", "ref": self.baseline, "unavailable": "error"},
                "adapters": [{"id": "source", "type": "builtin", "implementation": "core_source_v1", "languages": [], "required_at": "soft"},
                             {"id": "python", "type": "builtin", "implementation": "python_ast_v1", "languages": ["python"], "required_at": "standard"}],
                "thresholds": {"python_ast_v1.cyclomatic_v1": {"warning": 10, "strong": 15}}, "policy": {"changed_code_only": True, "untouched_existing_debt": "report", "soft_new_strong": "report", "standard_new_strong": "exception_or_fail", "top_new_strong": "exception_or_fail", "required_adapter_failure": "incomplete"},
                "exceptions": [], "extensions": {}}

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True, stderr=subprocess.PIPE)

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")

    def put(self, name, content):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def run_gate(self, base=None):
        return subprocess.run([PYTHON, "-I", "-B", str(self.trusted / "scripts/check_quality_gate.py"),
                               "--repo", str(self.repo), "--trusted-base", base or self.base],
                              text=True, capture_output=True)

    def blocked(self, expected, base=None):
        result = self.run_gate(base)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn(expected, result.stderr)

    def test_ordinary_change_and_prose_pass_with_fresh_report(self):
        self.put("sample.py", "def answer():\n    return 43\n")
        self.put("README.md", "Harmless prose.\n")
        self.put(".agents/quality-report.json", '{"status": "QUALITY_FAIL"}')
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["quality_status"], "QUALITY_PASS")
        self.assertIn(self.baseline, result.stdout)

    def test_strong_new_complexity_fails_despite_stale_green(self):
        self.put("sample.py", "def answer(value):\n" + "".join(f"    if value == {i}:\n        return {i}\n" for i in range(20)) + "    return -1\n")
        self.put(".agents/quality-report.json", '{"status": "QUALITY_PASS"}')
        result = self.run_gate()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["quality_status"], "QUALITY_FAIL")

    def test_malformed_source_is_incomplete_not_pass(self):
        self.put("sample.py", "def broken(:\n")
        result = self.run_gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["quality_status"], "QUALITY_INCOMPLETE")

    def test_candidate_policy_cannot_self_approve(self):
        for field, value in (("thresholds", {"python_ast_v1.cyclomatic_v1": {"warning": 100, "strong": 200}}),
                             ("scope", {"include": [], "exclude": ["sample.py"], "languages": ["python"]}),
                             ("exceptions", [{"unapproved": True}]),
                             ("baseline", {"strategy": "merge_base", "ref": self.base, "unavailable": "error"})):
            with self.subTest(field=field):
                original = (self.repo / ".agents/quality.yaml").read_text()
                policy = yaml.safe_load(original)
                policy[field] = value
                self.put(".agents/quality.yaml", yaml.safe_dump(policy))
                self.blocked("QUALITY_GOVERNANCE_BLOCKED")
                self.put(".agents/quality.yaml", original)

    def test_policy_prose_does_not_false_block(self):
        path = self.repo / ".agents/quality.yaml"
        path.write_text(path.read_text() + "\n# harmless policy comment\n")
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_diverged_trusted_branch_does_not_block_candidate(self):
        self.git("checkout", "-qb", "trusted-advance")
        self.put("README.md", "Base branch advanced independently.\n")
        self.commit()
        advanced_base = self.git("rev-parse", "HEAD").strip()
        self.git("checkout", "-qb", "candidate", self.base)
        self.put("sample.py", "def answer():\n    return 43\n")
        self.commit()
        result = self.run_gate(advanced_base)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["quality_status"], "QUALITY_PASS")

    def test_missing_policy_blocks(self):
        (self.repo / ".agents/quality.yaml").unlink()
        self.blocked("QUALITY_GOVERNANCE_BLOCKED")

    def test_unapproved_bootstrap_blocks(self):
        self.blocked("trusted base lacks quality policy", self.baseline)

    def test_mutable_and_zero_base_block(self):
        for base in ("HEAD", "0" * 40):
            with self.subTest(base=base):
                self.blocked("QUALITY_GOVERNANCE_BLOCKED", base)

    def test_protected_changes_and_inventory_block(self):
        for name in ("scripts/check_quality_gate.py", ".github/workflows/quality.yml", ".agents/quality-tooling/tests/test_quality_gate.py", ".agents/quality-tooling/requirements.txt"):
            with self.subTest(name=name):
                original = (self.repo / name).read_text()
                self.put(name, original + "\n# weakening attempt\n")
                self.blocked("protected quality tooling changed")
                self.put(name, original)
        self.put(".agents/quality-tooling/extra.py", "pass\n")
        self.blocked("inventory changed")

    def test_protected_removal_blocks(self):
        (self.repo / ".agents/quality-tooling/tests/test_quality_gate.py").unlink()
        self.blocked("inventory changed")

    def test_vendor_matches_recorded_hashes(self):
        tooling = ROOT / ".agents/quality-tooling"
        provenance = json.loads((tooling / "provenance.json").read_text())
        for name, digest in provenance["files"].items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((tooling / name).read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
