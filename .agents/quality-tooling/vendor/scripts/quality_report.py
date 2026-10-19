# Produce deterministic changed-code quality reports. Usage: python quality_report.py --repo . --base HEAD~1 --config .agents/quality.yaml --format json
# Example: python quality_report.py --repo . --base main --scope all --level standard --config .agents/quality.yaml --format markdown
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import os
import pathlib
import secrets
import stat
import subprocess
import sys
from typing import Any

from quality_core import (QualityError, analyze_python, baseline_commit, canonical_json, collect_changes, config_hash,
                          content_baseline, deleted_metric_findings, effective_level, evaluate_findings,
                          external_metric_findings, load_external_metrics_payload, load_external_payload,
                          metric_findings, render_markdown, repo_root, required_adapter, run_git)
from validate_quality_policy import validate_policy

EXIT = {"QUALITY_PASS": 0, "QUALITY_PASS_WITH_EXCEPTION": 0, "QUALITY_FAIL": 2, "QUALITY_INCOMPLETE": 4}


def current_content(root: pathlib.Path, path: str, status: str, scope: str) -> bytes | None:
    if status == "D":
        return None
    if scope == "committed":
        proc = subprocess.run(["git", "-C", str(root), "show", f"HEAD:{path}"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        return proc.stdout if proc.returncode == 0 else None
    if scope == "index":
        proc = subprocess.run(["git", "-C", str(root), "show", f":{path}"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        return proc.stdout if proc.returncode == 0 else None
    try:
        return (root / path).read_bytes()
    except OSError:
        return None


def classify_snapshot_entry(root: pathlib.Path, path: str, data: bytes | None, status: str, scope: str) -> str | None:
    if status == "D":
        return None
    if scope in {"worktree", "all"}:
        candidate = root / path
        if candidate.is_symlink():
            return "symlink"
        if candidate.exists() and not candidate.is_file():
            return "submodule_or_non_file"
    if data is None:
        return "read_error"
    if b"\0" in data[:8192]:
        return "binary"
    return None


def selected_git_mode(root: pathlib.Path, path: str, scope: str) -> str | None:
    if scope == "committed":
        raw = run_git(root, ["ls-tree", "-z", "HEAD", "--", path])
        return raw.split(b" ", 1)[0].decode("ascii") if raw else None
    if scope == "index":
        raw = run_git(root, ["ls-files", "-s", "-z", "--", path])
        return raw.split(b" ", 1)[0].decode("ascii") if raw else None
    return None


def snapshot_changes(root: pathlib.Path, changes: list[Any], scope: str) -> tuple[list[Any], dict[str, bytes | None]]:
    captured: dict[str, bytes | None] = {}
    classified = []
    for change in changes:
        data = current_content(root, change.path, change.status, scope)
        captured[change.path] = data
        if scope in {"committed", "index"} and change.status != "D":
            mode = selected_git_mode(root, change.path, scope)
            if mode == "120000":
                unsupported = "symlink"
            elif mode == "160000":
                unsupported = "submodule_or_non_file"
            elif mode is None:
                unsupported = "read_error"
            else:
                unsupported = classify_snapshot_entry(root, change.path, data, change.status, scope)
        else:
            unsupported = change.unsupported or classify_snapshot_entry(root, change.path, data, change.status, scope)
        classified.append(type(change)(change.path, change.status, change.old_path, unsupported))
    return classified, captured


def snapshot_identity(root: pathlib.Path, changes: list[Any], captured: dict[str, bytes | None],
                      scope: str, excluded_paths: set[str] | None = None) -> str:
    head = run_git(root, ["rev-parse", "HEAD"]).decode().strip()
    digest = hashlib.sha256()
    excluded_paths = excluded_paths or set()
    for change in changes:
        if change.path in excluded_paths:
            continue
        digest.update(f"{change.status}\0{change.old_path or ''}\0{change.path}\0{change.unsupported or ''}\0".encode("utf-8", "surrogateescape"))
        data = captured[change.path]
        if data is not None:
            digest.update(hashlib.sha256(data).digest())
    return f"{head}+{scope}:{digest.hexdigest()[:16]}"


def verify_output_leaf(directory_fd: int, name: str) -> None:
    try:
        existing = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(existing.st_mode):
        raise QualityError("refusing to overwrite symlink output")


def secure_write_output(root: pathlib.Path, destination_input: pathlib.Path, output: str) -> None:
    destination = destination_input if destination_input.is_absolute() else pathlib.Path.cwd() / destination_input
    destination = destination.absolute()
    try:
        relative = destination.relative_to(root)
    except ValueError as exc:
        raise QualityError("output path must stay under repository root") from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise QualityError("invalid output path")
    directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = f".quality-report-{secrets.token_hex(8)}.tmp"
    try:
        for part in relative.parts[:-1]:
            try:
                os.mkdir(part, 0o755, dir_fd=directory_fd)
            except FileExistsError:
                pass
            child_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = child_fd
        verify_output_leaf(directory_fd, relative.name)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(output)
                handle.flush()
                os.fsync(handle.fileno())
            # Re-check immediately before replacement so a concurrent leaf swap
            # cannot turn an earlier safe observation into a symlink overwrite.
            verify_output_leaf(directory_fd, relative.name)
            os.replace(temporary, relative.name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        except Exception:
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            raise
    finally:
        os.close(directory_fd)


def allowed(path: str, policy: dict[str, Any]) -> bool:
    include = policy["scope"]["include"]
    exclude = policy["scope"]["exclude"]
    pure = pathlib.PurePosixPath(path)
    def matches(pattern: str) -> bool:
        return pure.match(pattern) or fnmatch.fnmatchcase(path, pattern)
    included = not include or any(matches(pattern) for pattern in include)
    excluded = any(matches(pattern) for pattern in exclude)
    return included and not excluded


LANGUAGE_SUFFIXES = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".yaml": "yaml", ".yml": "yaml", ".json": "json", ".toml": "toml",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".rs": "rust", ".go": "go", ".java": "java", ".kt": "kotlin", ".kts": "kotlin",
    ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".cs": "csharp", ".rb": "ruby", ".php": "php", ".swift": "swift", ".sql": "sql",
    ".html": "html", ".htm": "html", ".css": "css", ".scss": "scss",
}


def language_for_path(path: str) -> str | None:
    return LANGUAGE_SUFFIXES.get(pathlib.PurePosixPath(path).suffix.lower())


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    script_root = pathlib.Path(__file__).resolve().parents[1]
    schema_path = script_root / "schemas" / "quality-policy-v1.schema.json"
    external_schema = json.loads((script_root / "schemas" / "normalized-findings-v1.schema.json").read_text())
    metrics_schema = json.loads((script_root / "schemas" / "normalized-metrics-v2.schema.json").read_text())
    policy = validate_policy(args.config.resolve(), schema_path)
    root = repo_root(args.repo)
    base = baseline_commit(root, args.base or policy["baseline"]["ref"])
    scope = args.scope or policy["change_scope"]["default"]
    level = effective_level(args.level.lower(), policy["minimum_quality_expected"])
    evaluation_date = dt.date.fromisoformat(args.evaluation_date) if args.evaluation_date else dt.datetime.now(dt.timezone.utc).date()
    changes = collect_changes(root, base, scope, policy["change_scope"]["include_untracked"], policy["change_scope"]["detect_file_renames"])
    changes, captured = snapshot_changes(root, changes, scope)
    external_paths = {relative for adapter in policy["adapters"]
                      if adapter["implementation"] in {"external_findings_v1", "external_metrics_v2"}
                      for relative in adapter.get("paths", [])}
    current_snapshot = snapshot_identity(root, changes, captured, scope, external_paths)
    findings: list[dict[str, Any]] = []
    gaps: list[str] = []
    adapters: list[dict[str, Any]] = []
    analyzed_paths: set[str] = set()

    context = {"inputs": (root, base, policy, changes, captured, current_snapshot, external_schema, metrics_schema),
               "outputs": (findings, gaps, adapters, analyzed_paths)}
    run_adapters(context, level)

    required_errors = required_evidence_errors(changes, policy, adapters, gaps)
    status, applied = evaluate_findings(findings, policy["exceptions"], level, required_errors, policy["policy"], evaluation_date)
    report = {
        "schema_version": "1.0", "quality_status": status, "requested_level": args.level.lower(), "effective_level": level,
        "repository": {"root_id": hashlib.sha256(str(root).encode()).hexdigest()[:16], "baseline": base, "current": current_snapshot},
        "scope": {"mode": scope, "files_total": len(changes), "files_analyzed": len(analyzed_paths),
                  "files_unsupported": sum(1 for c in changes if c.unsupported),
                  "changes": [{"path": c.path, "old_path": c.old_path, "status": c.status, "unsupported": c.unsupported} for c in changes]},
        "policy": {"id": policy["policy_id"], "config_sha256": config_hash(policy),
                   "evaluation_date": evaluation_date.isoformat()},
        "adapters": adapters,
        "findings": sorted(findings, key=lambda f: (f["path"], f["symbol"], f["metric"], f["severity"])),
        "exceptions": sorted(applied, key=lambda e: (e["id"], e["path"], e["symbol"], e["metric"])),
        "evidence_gaps": sorted(set(gaps)),
    }
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=pathlib.Path, default=pathlib.Path("."))
    parser.add_argument("--base")
    parser.add_argument("--scope", choices=["committed", "index", "worktree", "all"])
    parser.add_argument("--level", choices=["soft", "standard", "top", "SOFT", "STANDARD", "TOP"], default="standard")
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--evaluation-date", help="UTC policy evaluation date (YYYY-MM-DD); recorded in canonical output")
    parser.add_argument("--output", type=pathlib.Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        report = build_report(args)
        output = canonical_json(report) if args.format == "json" else render_markdown(report)
        if args.output:
            root = repo_root(args.repo)
            secure_write_output(root, args.output, output)
        else:
            sys.stdout.write(output)
        return EXIT[report["quality_status"]]
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, QualityError) as exc:
        print(f"QUALITY CONFIG/SCOPE ERROR: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"QUALITY INTERNAL ERROR: {exc}", file=sys.stderr)
        return 1



def analyze_python_changes(context, adapter, state):
    root, base, policy, changes, captured, current_snapshot, external_schema, metrics_schema = context["inputs"]
    findings, gaps, adapters, analyzed_paths = context["outputs"]
    applicable = python_applicability(context, adapter, state)
    for change in [c for c in applicable if not c.unsupported and c.status == "D"]:
        analyze_deleted_python(context, change)
    for change in [c for c in applicable if not c.unsupported and c.status != "D"]:
        analyze_current_python(context, change)
    if state["required"] and any(c.unsupported for c in applicable):
        state["status"] = "INCOMPLETE"


def analyze_external_findings(context, adapter, state):
    root, base, policy, changes, captured, current_snapshot, external_schema, metrics_schema = context["inputs"]
    findings, gaps, adapters, analyzed_paths = context["outputs"]
    covered_files: set[tuple[str, str]] = set()
    enabled_languages = set(policy["scope"]["languages"])
    adapter_languages = set(adapter["languages"])
    effective_languages = adapter_languages & enabled_languages if enabled_languages else adapter_languages
    expected_coverage = {(c.path, language) for c in changes if c.status != "D" and allowed(c.path, policy)
                         for language in effective_languages if language_for_path(c.path) == language}
    for relative in adapter.get("paths", []):
        artifact_coverage, scoped = consume_external_findings(context, state, relative, expected_coverage, enabled_languages)
        covered_files.update((path, language) for path, language in artifact_coverage
                             if not enabled_languages or language in enabled_languages)
        findings.extend(scoped)
    finish_external_findings(context, adapter, state, covered_files, expected_coverage)


def analyze_external_metrics(context, adapter, state):
    root, base, policy, changes, captured, current_snapshot, external_schema, metrics_schema = context["inputs"]
    findings, gaps, adapters, analyzed_paths = context["outputs"]
    covered_files: set[tuple[str, str]] = set()
    enabled_languages = set(policy["scope"]["languages"])
    adapter_languages = set(adapter["languages"])
    effective_languages = adapter_languages & enabled_languages if enabled_languages else adapter_languages
    expected_coverage = {(c.path, language) for c in changes if c.status != "D" and allowed(c.path, policy)
                         for language in effective_languages if language_for_path(c.path) == language}
    if not expected_coverage:
        state["status"] = "NOT_APPLICABLE"
        state["reason"] = "no changed files match adapter and repository language scope"
        state["applicable_files"] = 0
        state["provenance"] = []
        return
    for relative in adapter.get("paths", []):
        artifact_coverage, measurements, metadata = consume_external_metrics(context, state, relative, expected_coverage)
        covered_files.update(artifact_coverage)
        findings.extend(external_metric_findings(measurements, policy["thresholds"], metadata))
    finish_external_metrics(context, adapter, state, covered_files, expected_coverage)


def run_adapters(context, level):
    root, base, policy, changes, captured, current_snapshot, external_schema, metrics_schema = context["inputs"]
    findings, gaps, adapters, analyzed_paths = context["outputs"]
    for adapter in policy["adapters"]:
        implementation = adapter["implementation"]
        state = {"id": adapter["id"], "implementation": implementation,
                 "status": "OK", "required": required_adapter(adapter["required_at"], level)}
        if implementation == "python_ast_v1":
            state.update({"adapter_version": "1.0", "tool_name": "python-ast",
                          "tool_version": f"python-{sys.version_info.major}.{sys.version_info.minor}",
                          "metric_specs": sorted(policy["thresholds"])})
        elif implementation == "core_source_v1":
            state.update({"adapter_version": "1.0", "tool_name": "builder-assurance",
                          "tool_version": "1.0", "metric_specs": []})
        else:
            state["provenance"] = []
        try:
            if adapter["implementation"] == "core_source_v1":
                state["applicable_files"] = sum(1 for c in changes if allowed(c.path, policy))
            elif adapter["implementation"] == "python_ast_v1":
                analyze_python_changes(context, adapter, state)
            elif adapter["implementation"] == "external_findings_v1":
                analyze_external_findings(context, adapter, state)
            elif adapter["implementation"] == "external_metrics_v2":
                analyze_external_metrics(context, adapter, state)
            else:
                raise QualityError(f"unsupported adapter {adapter['implementation']}")
        except (OSError, QualityError, ValueError) as exc:
            state["status"] = "ERROR"
            state["error"] = str(exc)
            if state["required"]:
                gaps.append(f"required adapter {adapter['id']} failed: {exc}")
        adapters.append(state)


def required_evidence_errors(changes, policy, adapters, gaps):
    for change in changes:
        if change.unsupported and allowed(change.path, policy):
            gaps.append(f"unsupported changed file ({change.unsupported}): {change.path}")
            for state in adapters:
                if state["required"] and state["implementation"] == "core_source_v1":
                    state["status"] = "INCOMPLETE"
    required_errors = [a["id"] for a in adapters if a["required"] and a["status"] not in {"OK", "NOT_APPLICABLE"}]
    # Parse/read failures in a required adapter are evidence gaps, not passes.
    if any(g.startswith("python_ast_v1") for g in gaps) and any(a["implementation"] == "python_ast_v1" and a["required"] for a in adapters):
        required_errors.append("python-ast-evidence-gap")
    return required_errors


def analyze_deleted_python(context, change):
    root, base, policy, changes, captured, current_snapshot, external_schema, metrics_schema = context["inputs"]
    findings, gaps, adapters, analyzed_paths = context["outputs"]
    baseline_data = content_baseline(root, base, change)
    if baseline_data is None:
        gaps.append(f"python_ast_v1 could not read deleted baseline source: {change.path}")
        return
    previous = analyze_python(baseline_data, change.path)
    if previous["status"] != "OK":
        gaps.append(f"python_ast_v1 baseline {previous['status']}: {change.path}: {previous['message']}")
        return
    analyzed_paths.add(change.path)
    findings.extend(deleted_metric_findings(previous, change.path, policy["thresholds"]))


def analyze_current_python(context, change):
    root, base, policy, changes, captured, current_snapshot, external_schema, metrics_schema = context["inputs"]
    findings, gaps, adapters, analyzed_paths = context["outputs"]
    current_data = captured[change.path]
    if current_data is None:
        gaps.append(f"python_ast_v1 could not read current source: {change.path}")
        return
    current = analyze_python(current_data, change.path)
    baseline_data = content_baseline(root, base, change)
    previous = analyze_python(baseline_data, change.old_path or change.path) if baseline_data is not None else None
    if current["status"] != "OK":
        gaps.append(f"python_ast_v1 {current['status']}: {change.path}: {current['message']}")
    elif previous is not None and previous["status"] != "OK":
        gaps.append(f"python_ast_v1 baseline {previous['status']}: {change.old_path or change.path}: {previous['message']}")
    else:
        analyzed_paths.add(change.path)
        findings.extend(metric_findings(current, previous, change.old_path, policy["thresholds"]))


def consume_external_findings(context, state, relative, expected_coverage, enabled_languages):
    root, base, policy, changes, captured, current_snapshot, external_schema, metrics_schema = context["inputs"]
    findings, gaps, adapters, analyzed_paths = context["outputs"]
    artifact = (root / relative).resolve()
    if root != artifact and root not in artifact.parents:
        raise QualityError(f"external artifact escapes repository: {relative}")
    metadata, external = load_external_payload(artifact, external_schema)
    provenance = {key: metadata[key] for key in
                  ("adapter_id", "adapter_version", "metric_spec", "tool_name", "tool_version")}
    if provenance not in state["provenance"]:
        state["provenance"].append(provenance)
    if metadata["source_snapshot"] != current_snapshot:
        raise QualityError(f"external findings snapshot does not match selected source: {relative}")
    return validate_findings_coverage(context, external, metadata, relative, expected_coverage, enabled_languages)


def consume_external_metrics(context, state, relative, expected_coverage):
    root, base, policy, changes, captured, current_snapshot, external_schema, metrics_schema = context["inputs"]
    findings, gaps, adapters, analyzed_paths = context["outputs"]
    changed_paths = {c.path for c in changes}
    artifact = (root / relative).resolve()
    if root != artifact and root not in artifact.parents:
        raise QualityError(f"external metrics artifact escapes repository: {relative}")
    metadata, measurements = load_external_metrics_payload(artifact, metrics_schema)
    provenance = {key: metadata[key] for key in
                  ("adapter_id", "adapter_version", "metric_spec", "tool_name", "tool_version")}
    if provenance not in state["provenance"]:
        state["provenance"].append(provenance)
    if metadata["source_snapshot"] != current_snapshot:
        raise QualityError(f"external metrics snapshot does not match selected source: {relative}")
    if metadata["baseline_commit"] != base:
        raise QualityError(f"external metrics baseline does not match selected baseline: {relative}")
    artifact_coverage = {(item["path"], item["language"]) for item in metadata["coverage"]["files"]}
    if artifact_coverage - expected_coverage:
        raise QualityError(f"external metrics coverage exceeds adapter/repository applicability: {relative}")
    measurement_pairs = {(item["path"], item["language"]) for item in measurements}
    if not measurement_pairs <= artifact_coverage:
        raise QualityError(f"external metrics measurements lack coverage: {relative}")
    if any(item["path"] not in changed_paths or not allowed(item["path"], policy) for item in measurements):
        raise QualityError(f"external metrics include paths outside selected change scope: {relative}")
    return artifact_coverage, measurements, metadata


def finish_external_findings(context, adapter, state, covered_files, expected_coverage):
    root, base, policy, changes, captured, current_snapshot, external_schema, metrics_schema = context["inputs"]
    findings, gaps, adapters, analyzed_paths = context["outputs"]
    state["applicable_files"] = len({path for path, _ in covered_files})
    if state["required"] and not adapter.get("paths"):
        state["status"] = "INCOMPLETE"
        gaps.append(f"required external adapter {adapter['id']} has no artifacts")
    elif state["required"] and expected_coverage - covered_files:
        state["status"] = "INCOMPLETE"
        missing = ", ".join(f"{path} ({language})" for path, language in sorted(expected_coverage - covered_files))
        gaps.append(f"required external adapter {adapter['id']} missing coverage: {missing}")
    elif not expected_coverage:
        state["status"] = "NOT_APPLICABLE"
        state["reason"] = "no changed files match adapter and repository language scope"
    if state["status"] == "OK":
        analyzed_paths.update(path for path, _ in covered_files)
    state["provenance"] = sorted(state["provenance"], key=lambda item: tuple(item[key] for key in
                                  ("adapter_id", "adapter_version", "metric_spec", "tool_name", "tool_version")))


def finish_external_metrics(context, adapter, state, covered_files, expected_coverage):
    root, base, policy, changes, captured, current_snapshot, external_schema, metrics_schema = context["inputs"]
    findings, gaps, adapters, analyzed_paths = context["outputs"]
    state["applicable_files"] = len({path for path, _ in covered_files})
    if state["required"] and not adapter.get("paths"):
        state["status"] = "INCOMPLETE"
        gaps.append(f"required external metrics adapter {adapter['id']} has no artifacts")
    elif state["required"] and expected_coverage - covered_files:
        state["status"] = "INCOMPLETE"
        missing = ", ".join(f"{path} ({language})" for path, language in sorted(expected_coverage - covered_files))
        gaps.append(f"required external metrics adapter {adapter['id']} missing coverage: {missing}")
    elif not expected_coverage:
        state["status"] = "NOT_APPLICABLE"
        state["reason"] = "no changed files match adapter and repository language scope"
    if state["status"] == "OK":
        analyzed_paths.update(path for path, _ in covered_files)
    state["provenance"] = sorted(state["provenance"], key=lambda item: tuple(item[key] for key in
                                  ("adapter_id", "adapter_version", "metric_spec", "tool_name", "tool_version")))


def python_applicability(context, adapter, state):
    root, base, policy, changes, captured, current_snapshot, external_schema, metrics_schema = context["inputs"]
    findings, gaps, adapters, analyzed_paths = context["outputs"]
    enabled = not policy["scope"]["languages"] or "python" in policy["scope"]["languages"]
    enabled = enabled and (not adapter["languages"] or "python" in adapter["languages"])
    applicable = [c for c in changes if enabled and c.path.endswith(".py") and allowed(c.path, policy)]
    state["applicable_files"] = len(applicable)
    if not enabled:
        state["status"] = "NOT_APPLICABLE"
        state["reason"] = "python is outside repository or adapter language scope"
    elif not applicable:
        state["status"] = "NOT_APPLICABLE"
        state["reason"] = "no changed Python files are in selected scope"
    return applicable


def validate_findings_coverage(context, external, metadata, relative, expected_coverage, enabled_languages):
    root, base, policy, changes, captured, current_snapshot, external_schema, metrics_schema = context["inputs"]
    findings, gaps, adapters, analyzed_paths = context["outputs"]
    changed_paths = {c.path for c in changes}
    path_scoped = [item for item in external if item["path"] in changed_paths and allowed(item["path"], policy)]
    if len(path_scoped) != len(external):
        raise QualityError(f"external findings include paths outside selected change scope: {relative}")
    scoped = [item for item in path_scoped if not enabled_languages or item["language"] in enabled_languages]
    artifact_coverage = {(item["path"], item["language"]) for item in metadata["coverage"]["files"]}
    if any(path not in changed_paths or not allowed(path, policy) for path, _ in artifact_coverage):
        raise QualityError(f"external coverage includes paths outside selected change scope: {relative}")
    if artifact_coverage - expected_coverage:
        raise QualityError(f"external coverage includes paths or languages outside adapter/repository applicability: {relative}")
    finding_pairs = {(item["path"], item["language"]) for item in external}
    if not finding_pairs <= artifact_coverage:
        raise QualityError(f"external findings are not covered by the artifact manifest: {relative}")
    return artifact_coverage, scoped

if __name__ == "__main__":
    raise SystemExit(main())
