# Deterministic changed-code scope, metrics, policy evaluation, and rendering. Usage: import quality_core from quality_report.py
# Example: from quality_core import collect_changes, analyze_python, evaluate_report
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import io
import json
import math
import os
import pathlib
import subprocess
import tokenize
from dataclasses import dataclass
from typing import Any

LEVELS = {"soft": 0, "standard": 1, "top": 2}
DEFAULT_THRESHOLDS = {
    "python_ast_v1.function_logical_lines": {"warning": 40, "strong": 80},
    "python_ast_v1.cyclomatic_v1": {"warning": 10, "strong": 15},
    "python_ast_v1.max_nesting": {"warning": 4, "strong": 6},
    "python_ast_v1.parameter_count": {"warning": 5, "strong": 8},
    "python_ast_v1.file_logical_lines": {"warning": 500, "strong": 900},
}
SUPPORTED_IMPLEMENTATIONS = {"core_source_v1", "python_ast_v1", "external_findings_v1", "external_metrics_v2"}


class QualityError(Exception):
    """Expected invocation/config/source error."""


@dataclass(frozen=True)
class Change:
    path: str
    status: str
    old_path: str | None = None
    unsupported: str | None = None


def run_git(repo: pathlib.Path, args: list[str], *, input_data: bytes | None = None, check: bool = True) -> bytes:
    proc = subprocess.run(["git", "-C", str(repo), *args], input=input_data, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=False)
    if check and proc.returncode:
        raise QualityError(proc.stderr.decode("utf-8", "replace").strip() or "git command failed")
    return proc.stdout


def repo_root(repo: str | pathlib.Path) -> pathlib.Path:
    candidate = pathlib.Path(repo).resolve()
    out = run_git(candidate, ["rev-parse", "--show-toplevel"])
    root = pathlib.Path(out.decode().strip()).resolve()
    if not root.is_dir():
        raise QualityError("repository root is unavailable")
    return root


def baseline_commit(repo: pathlib.Path, base: str) -> str:
    if base == "default_branch":
        symbolic = run_git(repo, ["symbolic-ref", "refs/remotes/origin/HEAD"], check=False).decode().strip()
        if not symbolic:
            raise QualityError("default_branch is unresolved; pass --base or configure origin/HEAD")
        base = symbolic.removeprefix("refs/remotes/")
    head = run_git(repo, ["rev-parse", "--verify", "HEAD"], check=False).decode().strip()
    if not head:
        raise QualityError("unborn repository has no baseline commit")
    base_commit = run_git(repo, ["rev-parse", "--verify", f"{base}^{{commit}}"], check=False).decode().strip()
    if not base_commit:
        raise QualityError(f"baseline ref is unavailable: {base!r}")
    ancestor = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", base_commit, "HEAD"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if ancestor.returncode != 0:
        raise QualityError(f"no merge-base for {base!r} and HEAD")
    return base_commit


def parse_name_status(raw: bytes) -> list[Change]:
    parts = raw.split(b"\0")
    changes: list[Change] = []
    i = 0
    while i < len(parts) and parts[i]:
        status = parts[i].decode("ascii", "replace")
        i += 1
        if status.startswith(("R", "C")):
            if i + 1 >= len(parts):
                raise QualityError("truncated Git rename record")
            old = os.fsdecode(parts[i])
            path = os.fsdecode(parts[i + 1])
            i += 2
            changes.append(Change(path=path, old_path=old, status=status[0]))
        else:
            if i >= len(parts):
                raise QualityError("truncated Git status record")
            changes.append(Change(path=os.fsdecode(parts[i]), status=status[0]))
            i += 1
    return changes


def classify_path(repo: pathlib.Path, change: Change) -> Change:
    path = repo / change.path
    try:
        if path.is_symlink():
            return Change(change.path, change.status, change.old_path, "symlink")
        if path.exists() and not path.is_file():
            return Change(change.path, change.status, change.old_path, "submodule_or_non_file")
        if path.exists() and b"\0" in path.read_bytes()[:8192]:
            return Change(change.path, change.status, change.old_path, "binary")
    except OSError as exc:
        return Change(change.path, change.status, change.old_path, f"read_error:{exc.__class__.__name__}")
    return change


def collect_changes(repo: pathlib.Path, baseline: str, scope: str, include_untracked: bool = True,
                    detect_renames: bool = True) -> list[Change]:
    if scope not in {"committed", "index", "worktree", "all"}:
        raise QualityError(f"invalid scope: {scope}")
    unmerged = run_git(repo, ["diff", "--name-only", "--diff-filter=U", "-z"])
    if unmerged:
        paths = ", ".join(os.fsdecode(item) for item in unmerged.split(b"\0") if item)
        raise QualityError(f"unresolved merge conflicts: {paths}")
    rename = ["--find-renames=100%"] if detect_renames else ["--no-renames"]
    groups: list[list[Change]] = []
    if scope == "committed":
        groups.append(parse_name_status(run_git(repo, ["diff", "--name-status", "-z", *rename, baseline, "HEAD", "--"])))
    elif scope == "index":
        groups.append(parse_name_status(run_git(repo, ["diff", "--cached", "--name-status", "-z", *rename, "HEAD", "--"])))
    elif scope == "worktree":
        groups.append(parse_name_status(run_git(repo, ["diff", "--name-status", "-z", *rename, "--"])))
    else:
        # Compare the immutable baseline directly to the final index+worktree view.
        # This collapses rename chains and avoids reporting obsolete intermediate paths.
        groups.append(parse_name_status(run_git(repo, ["diff", "--name-status", "-z", *rename, baseline, "--"])))
    if scope in {"worktree", "all"} and include_untracked:
        raw = run_git(repo, ["ls-files", "--others", "--exclude-standard", "-z"])
        groups.append([Change(os.fsdecode(p), "A") for p in raw.split(b"\0") if p])
    merged = {change.path: change for group in groups for change in group}
    return [classify_path(repo, merged[key]) for key in sorted(merged, key=lambda x: x.encode("utf-8", "surrogateescape"))]


def content_current(repo: pathlib.Path, change: Change) -> bytes | None:
    if change.status == "D" or change.unsupported:
        return None
    try:
        return (repo / change.path).read_bytes()
    except OSError:
        return None


def content_baseline(repo: pathlib.Path, baseline: str, change: Change) -> bytes | None:
    source_path = change.old_path or change.path
    proc = subprocess.run(["git", "-C", str(repo), "show", f"{baseline}:{source_path}"], stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, check=False)
    return proc.stdout if proc.returncode == 0 else None


def _logical_lines(source: str, start: int = 1, end: int | None = None) -> int:
    lines: set[int] = set()
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type in {tokenize.ENCODING, tokenize.ENDMARKER, tokenize.INDENT, tokenize.DEDENT,
                              tokenize.NEWLINE, tokenize.NL, tokenize.COMMENT}:
                continue
            if token.type == tokenize.STRING and token.start[0] == start:
                # A leading standalone string is a docstring; AST span semantics exclude it.
                continue
            if token.start[0] >= start and (end is None or token.start[0] <= end):
                lines.add(token.start[0])
    except (tokenize.TokenError, IndentationError):
        return 0
    return len(lines)


class MetricVisitor(ast.NodeVisitor):
    def __init__(self, source: str, path: str):
        self.source = source
        self.path = path
        self.scope: list[tuple[str, str]] = []
        self.functions: list[dict[str, Any]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        self.scope.append((node.name, "class"))
        self.generic_visit(node)
        self.scope.pop()

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualified = ".".join([*[name for name, _ in self.scope], node.name])
        kind = "method" if self.scope and self.scope[-1][1] == "class" else "function"
        start = min([node.lineno, *[d.lineno for d in node.decorator_list]])
        end = node.end_lineno or node.lineno
        positional = len(node.args.posonlyargs) + len(node.args.args)
        if kind == "method" and node.args.args and node.args.args[0].arg in {"self", "cls"}:
            positional -= 1
        params = positional + len(node.args.kwonlyargs) + (1 if node.args.vararg else 0) + (1 if node.args.kwarg else 0)
        complexity = 1
        max_nesting = 0

        def walk(current: ast.AST, nesting: int = 0) -> None:
            nonlocal complexity, max_nesting
            if current is not node and isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                return
            branch = isinstance(current, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp,
                                           ast.ExceptHandler, ast.comprehension, ast.Match))
            if branch:
                complexity += 1
                nesting += 1
                max_nesting = max(max_nesting, nesting)
            if isinstance(current, ast.BoolOp):
                complexity += max(0, len(current.values) - 1)
            if isinstance(current, ast.match_case) and current.guard is not None:
                complexity += 1
            for child in ast.iter_child_nodes(current):
                walk(child, nesting)
        walk(node)
        self.functions.append({
            "path": self.path, "language": "python", "symbol": qualified, "symbol_kind": kind,
            "metrics": {
                "python_ast_v1.function_physical_lines": end - start + 1,
                "python_ast_v1.function_logical_lines": _logical_lines(self.source, node.lineno, end),
                "python_ast_v1.parameter_count": params,
                "python_ast_v1.max_nesting": max_nesting,
                "python_ast_v1.cyclomatic_v1": complexity,
            },
        })
        self.scope.append((node.name, "function"))
        self.generic_visit(node)
        self.scope.pop()

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function


def analyze_python(data: bytes, path: str) -> dict[str, Any]:
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return {"path": path, "status": "PARSE_ERROR", "message": f"UTF-8 decode error: {exc}", "symbols": []}
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return {"path": path, "status": "PARSE_ERROR", "message": f"{exc.msg} at line {exc.lineno}", "symbols": []}
    visitor = MetricVisitor(source, path)
    visitor.visit(tree)
    physical = len(source.splitlines())
    file_symbol = {"path": path, "language": "python", "symbol": "<module>", "symbol_kind": "file",
                   "metrics": {"python_ast_v1.file_physical_lines": physical,
                               "python_ast_v1.file_logical_lines": _logical_lines(source)}}
    return {"path": path, "status": "OK", "message": "", "symbols": [file_symbol, *visitor.functions]}


def severity(value: float, limits: dict[str, float]) -> str | None:
    if value > limits["strong"]:
        return "strong"
    if value > limits["warning"]:
        return "warning"
    return None


def metric_findings(current: dict[str, Any], baseline: dict[str, Any] | None, old_path: str | None,
                    thresholds: dict[str, Any]) -> list[dict[str, Any]]:
    base_symbols = {}
    if baseline and baseline["status"] == "OK":
        base_symbols = {(s["symbol"], s["symbol_kind"]): s for s in baseline["symbols"]}
    findings = []
    for symbol in current.get("symbols", []):
        key = (symbol["symbol"], symbol["symbol_kind"])
        previous = base_symbols.get(key)
        mapping = "FILE_RENAME" if previous and old_path else "EXACT" if previous else "SYMBOL_MAPPING_UNKNOWN" if old_path else "NEW"
        for metric, value in symbol["metrics"].items():
            if metric not in thresholds:
                continue
            level = severity(value, thresholds[metric])
            if not level:
                continue
            findings.append({"adapter_id": "python-ast", "adapter_version": "1.0", "metric_spec": metric,
                "metric": metric, "path": symbol["path"], "language": "python", "symbol": symbol["symbol"],
                "symbol_kind": symbol["symbol_kind"], "current": value,
                "baseline": previous["metrics"].get(metric) if previous else None, "mapping_status": mapping,
                "strong_threshold": thresholds[metric]["strong"],
                "severity": level, "message": f"{metric}={value} exceeds {level} threshold",
                "tool_name": "python-ast", "tool_version": f"python-{os.sys.version_info.major}.{os.sys.version_info.minor}"})
    return findings


def deleted_metric_findings(baseline: dict[str, Any], path: str,
                            thresholds: dict[str, Any]) -> list[dict[str, Any]]:
    """Record threshold-relevant baseline metrics for a deleted Python file without blocking."""
    findings = []
    for symbol in baseline.get("symbols", []):
        for metric, value in symbol["metrics"].items():
            if metric not in thresholds:
                continue
            level = severity(value, thresholds[metric])
            if not level:
                continue
            findings.append({
                "adapter_id": "python-ast", "adapter_version": "1.0", "metric_spec": metric,
                "metric": metric, "path": path, "language": "python", "symbol": symbol["symbol"],
                "symbol_kind": symbol["symbol_kind"], "current": 0, "baseline": value,
                "mapping_status": "DELETED", "strong_threshold": thresholds[metric]["strong"],
                "severity": level, "message": f"deleted symbol had {metric}={value} at baseline",
                "tool_name": "python-ast",
                "tool_version": f"python-{os.sys.version_info.major}.{os.sys.version_info.minor}",
            })
    return findings


def strict_json_load(path: pathlib.Path, max_bytes: int = 20_000_000) -> Any:
    data = path.read_bytes()
    if len(data) > max_bytes:
        raise QualityError(f"external findings file too large: {path}")
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite number {value}")
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=reject_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise QualityError(f"invalid external JSON {path}: {exc}") from exc


def load_external_payload(path: pathlib.Path, schema: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from jsonschema import Draft202012Validator, FormatChecker
    payload = strict_json_load(path)
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload), key=lambda e: list(e.path))
    if errors:
        raise QualityError(f"invalid external findings {path}: {errors[0].message}")
    result = []
    for finding in payload["findings"]:
        item = dict(finding)
        item.update({key: payload[key] for key in ("adapter_id", "adapter_version", "metric_spec", "tool_name", "tool_version", "source_snapshot")})
        result.append(item)
    metadata = {key: payload[key] for key in ("adapter_id", "adapter_version", "metric_spec", "tool_name", "tool_version", "source_snapshot", "coverage")}
    return metadata, result


def load_external(path: pathlib.Path, schema: dict[str, Any]) -> list[dict[str, Any]]:
    return load_external_payload(path, schema)[1]


def load_external_metrics_payload(path: pathlib.Path, schema: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from jsonschema import Draft202012Validator, FormatChecker
    payload = strict_json_load(path)
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
                    key=lambda error: list(error.path))
    if errors:
        raise QualityError(f"invalid external metrics {path}: {errors[0].message}")
    metadata_keys = ("adapter_id", "adapter_version", "metric_spec", "tool_name", "tool_version",
                     "source_snapshot", "baseline_commit", "coverage")
    return {key: payload[key] for key in metadata_keys}, list(payload["measurements"])


def external_metric_findings(measurements: list[dict[str, Any]], thresholds: dict[str, Any],
                             metadata: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    provenance = {key: metadata[key] for key in
                  ("adapter_id", "adapter_version", "metric_spec", "tool_name", "tool_version", "source_snapshot")}
    for measurement in measurements:
        metric = measurement["metric"]
        if metric not in thresholds:
            continue
        level = severity(measurement["current"], thresholds[metric])
        if not level:
            continue
        finding = dict(measurement)
        finding.update(provenance)
        finding.update({"severity": level, "strong_threshold": thresholds[metric]["strong"]})
        if not finding.get("message"):
            finding["message"] = f"{metric}={finding['current']} exceeds {level} threshold"
        findings.append(finding)
    return findings


def effective_level(requested: str, minimum: str) -> str:
    if requested not in LEVELS or minimum not in LEVELS:
        raise QualityError("quality level must be soft, standard, or top")
    return requested if LEVELS[requested] >= LEVELS[minimum] else minimum


def required_adapter(required_at: str, level: str) -> bool:
    return required_at != "never" and LEVELS[level] >= LEVELS[required_at]


def matching_exception(finding: dict[str, Any], exceptions: list[dict[str, Any]], today: dt.date) -> dict[str, Any] | None:
    for exception in exceptions:
        selector = exception["selector"]
        created = dt.date.fromisoformat(exception["created_at"])
        expires = dt.date.fromisoformat(exception["expires_at"])
        if (selector["path"] == finding["path"] and selector["language"] == finding["language"] and
                selector["symbol"] == finding["symbol"] and selector["kind"] == finding["symbol_kind"] and
                exception["metric"] == finding["metric"] and created <= today <= expires and
                finding["current"] <= exception["allowance"]["maximum"]):
            return exception
    return None


def evaluate_findings(findings: list[dict[str, Any]], exceptions: list[dict[str, Any]], level: str,
                      adapter_errors: list[str], policy_controls: dict[str, Any] | None = None,
                      evaluation_date: dt.date | None = None) -> tuple[str, list[dict[str, Any]]]:
    if adapter_errors:
        return "QUALITY_INCOMPLETE", []
    applied = []
    failures = []
    today = evaluation_date or dt.date.today()
    for finding in findings:
        if finding.get("severity") != "strong":
            continue
        blocks = finding_blocks(finding, level, policy_controls)
        exception = matching_exception(finding, exceptions, today)
        if exception:
            applied.append({"id": exception["id"], "path": finding["path"], "symbol": finding["symbol"], "metric": finding["metric"]})
        elif blocks:
            failures.append(finding)
    if failures:
        return "QUALITY_FAIL", applied
    if applied:
        return "QUALITY_PASS_WITH_EXCEPTION", applied
    return "QUALITY_PASS", applied


def canonical_json(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Builder Assurance quality report", "", f"**{report['quality_status']}**",
             f"- Requested level: `{report['requested_level']}`", f"- Effective level: `{report['effective_level']}`",
             f"- Scope: `{report['scope']['mode']}` ({report['scope']['files_analyzed']}/{report['scope']['files_total']} analyzed; {report['scope']['files_unsupported']} unsupported)",
             f"- Baseline: `{report['repository']['baseline']}`", f"- Current: `{report['repository']['current']}`", ""]
    if report["findings"]:
        lines += ["## Findings", "", "| Severity | Path | Symbol | Metric | Current | Baseline | Mapping |", "|---|---|---|---|---:|---:|---|"]
        for item in report["findings"]:
            baseline = "—" if item.get("baseline") is None else str(item["baseline"])
            lines.append(f"| {item['severity']} | `{item['path']}` | `{item['symbol']}` | `{item['metric']}` | {item['current']} | {baseline} | {item['mapping_status']} |")
        lines.append("")
    if report["evidence_gaps"]:
        lines += ["## Evidence gaps", "", *[f"- {gap}" for gap in report["evidence_gaps"]], ""]
    lines += ["_This deterministic outcome is scoped code-quality evidence. It is not a claim of behavioral correctness, security, or release readiness._", ""]
    return "\n".join(lines)


def config_hash(policy: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(policy).encode()).hexdigest()


def finding_blocks(finding, level, policy_controls):
    """Decide blocking severity separately from exception application."""
    previous = finding.get("baseline")
    strong_threshold = finding.get("strong_threshold")
    newly_strong = previous is None or not math.isfinite(previous) or (strong_threshold is not None and previous <= strong_threshold)
    worsened = previous is not None and finding["current"] > previous
    default_action = "report" if level == "soft" else "exception_or_fail"
    action = (policy_controls or {}).get(f"{level}_new_strong", default_action)
    blocks = action == "exception_or_fail" and (newly_strong or worsened)
    return blocks
