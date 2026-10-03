"""Bounded approval snapshots and child-only native reader binding.

Selectors choose policy sources, not privilege levels. No command parser lives here.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

MODES = {"deny", "profile", "inherit", "yolo"}
# v2 identifies deny's native permanent-grant semantics. v1 deny refused
# dangerous commands even when permanently granted: posture alone cannot
# distinguish it from a normalized candidate envelope. Never migrate on resume.
VERSION = 2


def selector(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("approval selector must be deny, profile, inherit, or yolo")
    if value == "approve_yolo":
        return "yolo"
    if value not in MODES:
        raise ValueError("approval selector must be deny, profile, inherit, or yolo")
    return value


def subset(config: dict) -> dict:
    raw = config.get("approvals") or {}
    if not isinstance(raw, dict):
        raise ValueError("native approvals must be a mapping")
    mode = raw.get("mode", "manual")
    if mode is False:
        mode = "off"
    if mode not in {"manual", "smart", "off"}:
        raise ValueError("invalid native approvals.mode")
    result = {"mode": mode}
    for key in ("single_query_mode", "unattended_mode"):
        value = str(raw.get(key, "deny")).lower()
        result[key] = "approve" if value in {"approve", "off", "allow", "yes"} else "deny"
    for key in ("deny",):
        value = raw.get(key, [])
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError(f"native approvals.{key} must be an array of strings")
        result[key] = list(value)
    grants = config.get("command_allowlist") or []
    if not isinstance(grants, list) or any(not isinstance(item, str) for item in grants):
        raise ValueError("native command_allowlist must be an array of strings")
    return {"approvals": result, "command_allowlist": list(grants)}


def fingerprint(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def snapshot(mode: str, provenance: str, caller: str, target: str,
             caller_config: dict, target_config: dict, caller_yolo: bool = False,
             ancestor: dict | None = None) -> dict:
    mode = selector(mode)
    native = subset(caller_config if mode == "inherit" else target_config)
    target_native = subset(target_config)
    denies = list(dict.fromkeys(native["approvals"]["deny"] + target_native["approvals"]["deny"]))
    bypass = mode != "deny" and (mode == "yolo" or (mode == "inherit" and caller_yolo) or native["approvals"]["mode"] == "off")
    if mode == "deny":
        native["approvals"].update(mode="manual", single_query_mode="deny", unattended_mode="deny")
    if ancestor:
        validate(ancestor)
        # No inference of incomparable policies or glob containment. Nested
        # execution reuses its ancestor's exact ordinary policy or stays deny.
        if ancestor["effective"] == "deny":
            if mode != "deny":
                raise ValueError("deny ancestry requires deny")
            native = copy.deepcopy(ancestor["native"])
            bypass = False
            native["approvals"].update(mode="manual", single_query_mode="deny", unattended_mode="deny")
        elif mode not in {"inherit", "deny"}:
            raise ValueError("nested delegation must inherit the frozen ancestor policy")
        else:
            native = copy.deepcopy(ancestor["native"])
            bypass = ancestor["bypass"] if mode == "inherit" else False
            if mode == "deny":
                native["approvals"].update(mode="manual", single_query_mode="deny", unattended_mode="deny")
        denies = list(dict.fromkeys(denies + ancestor["native"]["approvals"]["deny"]))
    native["approvals"]["deny"] = denies
    payload = {"schema_version": VERSION, "effective": mode, "source": provenance,
               "caller": caller, "target": target, "native": native,
               "bypass": bypass, "unattended_context": "single_query",
               "lineage_admission": "frozen_inherit_only" if ancestor else "operator_target"}
    payload["fingerprint"] = fingerprint(payload)
    return payload


def validate(envelope: dict) -> dict:
    if not isinstance(envelope, dict) or envelope.get("schema_version") not in {1, VERSION}:
        raise ValueError("unsupported native approval envelope")
    expected = {"schema_version", "effective", "source", "caller", "target", "native", "bypass",
                "unattended_context", "lineage_admission", "fingerprint"}
    if set(envelope) != expected or type(envelope["bypass"]) is not bool:
        raise ValueError("malformed native approval envelope")
    selector(envelope["effective"])
    if subset(envelope["native"]) != envelope["native"]:
        raise ValueError("noncanonical native approval envelope")
    if envelope["unattended_context"] != "single_query":
        raise ValueError("unsupported unattended context")
    unsigned = {key: value for key, value in envelope.items() if key != "fingerprint"}
    if fingerprint(unsigned) != envelope["fingerprint"]:
        raise ValueError("native approval fingerprint mismatch")
    if envelope["effective"] == "deny":
        if envelope["schema_version"] == 1:
            raise ValueError("historical schema-v1 deny authority cannot be resumed safely; create a new session (frozen authority is not migrated)")
        posture = envelope["native"]["approvals"]
        if envelope["bypass"] or any(posture[key] != value for key, value in (
                ("mode", "manual"), ("single_query_mode", "deny"), ("unattended_mode", "deny"))):
            raise ValueError("unsafe deny authority; create a new session")
    return copy.deepcopy(envelope)


def validate_request(request: dict) -> None:
    if "native_approval" in request:
        validate(request["native_approval"])


def configure_selector(entry, values, sources, coerce) -> None:
    if "child_approval_mode" in entry:
        values["child_approval_mode"] = coerce(entry["child_approval_mode"], allow_legacy_config=True)
        sources["child_approval_mode"] = "yaml"


def configured_target_modes(entry: dict) -> dict:
    if __package__:
        from .contracts import ProfileDelegateError
    else:
        from contracts import ProfileDelegateError
    try:
        return target_modes(entry)
    except Exception as exc:
        raise ProfileDelegateError(str(exc), "configuration_error") from exc


def target_modes(entry: dict) -> dict:
    from hermes_cli.profiles import profile_exists, validate_profile_name
    values = entry.get("child_approval_modes_by_profile", {})
    if not isinstance(values, dict):
        raise ValueError("child_approval_modes_by_profile must be a mapping")
    for target, mode in values.items():
        validate_profile_name(target)
        if not profile_exists(target):
            raise ValueError(f"invalid approval target {target!r}: profile does not exist")
        try:
            selector(mode)
        except ValueError as exc:
            raise ValueError(f"invalid approval target {target!r}: {exc}") from exc
    return dict(values)


def admit_resume(frozen: dict, ancestor: dict | None) -> dict:
    """Reject incompatible current lineage without refreshing frozen authority."""
    frozen = validate(frozen)
    if ancestor is None:
        raise ValueError("legacy ancestry cannot admit a frozen resume")
    ancestor = validate(ancestor)
    ordinary = copy.deepcopy(frozen["native"])
    inherited = copy.deepcopy(ancestor["native"])
    denies = set(ordinary["approvals"].pop("deny"))
    required = set(inherited["approvals"].pop("deny"))
    if not required <= denies:
        raise ValueError("frozen resume conflicts with current ancestry")
    if frozen["effective"] == "deny":
        narrowed = copy.deepcopy(inherited)
        narrowed["approvals"].update(mode="manual", single_query_mode="deny", unattended_mode="deny")
        admitted = not frozen["bypass"] and ordinary == narrowed
    elif ancestor["effective"] == "deny":
        admitted = False
    else:
        admitted = (frozen["effective"] == "inherit" and
                    frozen["bypass"] == ancestor["bypass"] and ordinary == inherited)
    if not admitted:
        raise ValueError("frozen resume conflicts with current ancestry")
    return frozen


def bind(envelope: dict) -> None:
    """Bind exact native config before importing guards/agent in a child process."""
    import os
    from hermes_cli import config

    envelope = validate(envelope)
    native = envelope["native"]
    original_read = config.load_config_readonly
    original_load = config.load_config

    def overlay(value):
        from hermes_constants import get_hermes_home
        if str(get_hermes_home().resolve()) != str(Path(envelope["target"]).resolve()):
            return value
        value = copy.deepcopy(value)
        approvals = value.get("approvals") or {}
        # Preserve unrelated target scanner/security knobs. Replace ordinary
        # posture and grants exactly, never deep-merge allowlists.
        approvals.update(copy.deepcopy(native["approvals"]))
        value["approvals"] = approvals
        value["command_allowlist"] = list(native["command_allowlist"])
        return value

    config.load_config_readonly = lambda: overlay(original_read())
    config.load_config = lambda: overlay(original_load())
    os.environ["HERMES_SINGLE_QUERY_SESSION"] = "1"
    os.environ.pop("HERMES_YOLO_MODE", None)
    if envelope["bypass"]:
        os.environ["HERMES_YOLO_MODE"] = "1"
    from tools import approval
    approval._YOLO_MODE_FROZEN = envelope["bypass"]
    with approval._lock:
        approval._permanent_approved.clear()
        approval._permanent_approved.update(native["command_allowlist"])
        approval._permanent_approved_by_home.clear()
        approval._session_approved.clear()
        approval._session_yolo.clear()


def read_request(path: Path) -> dict | None:
    request = json.loads(path.read_text(encoding="utf-8"))
    if "native_approval" not in request:
        return None
    return validate(request["native_approval"])
