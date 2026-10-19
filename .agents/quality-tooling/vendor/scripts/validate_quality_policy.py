# Validate strict builder-assurance quality.yaml policies. Usage: python validate_quality_policy.py POLICY [--schema SCHEMA]
# Example: python validate_quality_policy.py ../templates/quality.yaml
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

MAX_POLICY_BYTES = 2_000_000


class StrictLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: StrictLoader, node: yaml.MappingNode, deep: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise yaml.constructor.ConstructorError("mapping", node.start_mark, "mapping keys must be strings", key_node.start_mark)
        if key in result:
            raise yaml.constructor.ConstructorError("mapping", node.start_mark, f"duplicate key: {key}", key_node.start_mark)
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)
# Keep JSON-like primitives, but do not silently coerce dates or YAML 1.1 yes/no/on/off forms.
StrictLoader.yaml_implicit_resolvers = {}
for first, tag, regex in [
    (list("tTfF"), "tag:yaml.org,2002:bool", re.compile(r"^(?:true|false|True|False)$")),
    (list("-+0123456789"), "tag:yaml.org,2002:int", re.compile(r"^[-+]?(?:0|[1-9][0-9]*)$")),
    (list("-+0123456789."), "tag:yaml.org,2002:float", re.compile(r"^[-+]?(?:[0-9]+\.[0-9]+|[0-9]+[eE][-+]?[0-9]+|[0-9]+\.[0-9]+[eE][-+]?[0-9]+)$")),
]:
    for char in first:
        StrictLoader.add_implicit_resolver(tag, regex, [char])


def load_strict_yaml(path: pathlib.Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > MAX_POLICY_BYTES:
        raise ValueError("policy exceeds 2 MB")
    text = raw.decode("utf-8")
    tokens = list(yaml.scan(text))
    if any(isinstance(token, (yaml.tokens.AnchorToken, yaml.tokens.AliasToken, yaml.tokens.TagToken)) for token in tokens):
        raise ValueError("YAML anchors, aliases, and custom tags are forbidden")
    docs = list(yaml.load_all(text, Loader=StrictLoader))
    if len(docs) != 1 or not isinstance(docs[0], dict):
        raise ValueError("policy must contain exactly one mapping document")
    return docs[0]


def validate_semantics(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    adapter_ids = [item["id"] for item in policy.get("adapters", []) if isinstance(item, dict) and "id" in item]
    if len(adapter_ids) != len(set(adapter_ids)):
        errors.append("adapter ids must be unique")
    exception_ids = [item["id"] for item in policy.get("exceptions", []) if isinstance(item, dict) and "id" in item]
    if len(exception_ids) != len(set(exception_ids)):
        errors.append("exception ids must be unique")
    for metric, limits in policy.get("thresholds", {}).items():
        if isinstance(limits, dict) and limits.get("strong", 0) <= limits.get("warning", 0):
            errors.append(f"{metric}: strong threshold must exceed warning")
    errors.extend(validate_exception_semantics(policy))
    return errors


def validate_policy(path: pathlib.Path, schema_path: pathlib.Path) -> dict[str, Any]:
    policy = load_strict_yaml(path)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(policy), key=lambda e: list(e.absolute_path))
    messages = [f"{'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}" for error in errors]
    messages.extend(validate_semantics(policy))
    if messages:
        raise ValueError("\n".join(messages))
    return policy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("policy", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1] / "schemas" / "quality-policy-v1.schema.json")
    args = parser.parse_args(argv)
    try:
        policy = validate_policy(args.policy.resolve(), args.schema.resolve())
    except (OSError, UnicodeError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 3
    print(f"VALID {policy['policy_id']} schema={policy['schema_version']}")
    return 0


def validate_exception_semantics(policy):
    """Validate bounded lifetime and exact paths without changing error order."""
    errors = []
    for exception in policy.get("exceptions", []):
        try:
            created = dt.date.fromisoformat(exception["created_at"])
            expires = dt.date.fromisoformat(exception["expires_at"])
            if expires <= created:
                errors.append(f"{exception['id']}: expires_at must be after created_at")
            if (expires - created).days > 366:
                errors.append(f"{exception['id']}: exception lifetime exceeds 366 days")
            path = exception["selector"]["path"]
            if any(char in path for char in "*?["):
                errors.append(f"{exception['id']}: exception path must be exact, not a glob")
        except (KeyError, TypeError, ValueError):
            pass
    return errors


if __name__ == "__main__":
    raise SystemExit(main())
