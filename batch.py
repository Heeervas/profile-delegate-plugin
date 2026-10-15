"""Stateless multi-dispatch composition over the single-run engine."""
from __future__ import annotations

if __package__:
    from . import core
else:
    import core


FORCED = dict(background=True, notify_on_complete=True, transport_mode="interactive", session_mode="new")


def validate_fields(payload, schema):
    """Validate model types before the singular engine's normalizers."""
    if not isinstance(payload, dict):
        raise core.ProfileDelegateError("expected object", "validation_error")
    properties = schema["properties"]
    if set(payload) - set(properties) or set(schema.get("required", [])) - set(payload):
        raise core.ProfileDelegateError("unknown or missing fields", "validation_error")
    kinds = {"string": str, "boolean": bool, "integer": int, "array": list}
    for key, value in payload.items():
        spec = properties[key]
        if type(value) is not kinds[spec["type"]]:
            raise core.ProfileDelegateError(f"{key}: invalid type", "validation_error")
        if "enum" in spec and value not in spec["enum"]:
            raise core.ProfileDelegateError(f"{key}: invalid value", "validation_error")
        if isinstance(value, list):
            if len(value) > spec.get("maxItems", 100) or any(type(v) is not str for v in value):
                raise core.ProfileDelegateError(f"{key}: invalid array", "validation_error")
        if type(value) is int and not spec.get("minimum", value) <= value <= spec.get("maximum", value):
            raise core.ProfileDelegateError(f"{key}: outside limits", "validation_error")


def error_item(exc):
    return {"dispatch_status": "failed", "error_code": getattr(exc, "code", "internal_error"),
            "error": str(exc), **getattr(exc, "details", {})}


def _validate_tasks(tasks, item_schema, origin):
    items = []
    for index, task in enumerate(tasks):
        item = {"index": index, "profile": task.get("profile", "") if isinstance(task, dict) else "",
                "run_created": False, "deduplicated": False}
        try:
            validate_fields(task, item_schema)
            result = core.delegate_profile(**task, **FORCED, origin=origin, preflight=True)
            item.update(profile=result["normalized_request"]["profile"], validation_status="validated")
        except Exception as exc:
            item.update(error_item(exc))
        items.append(item)
    return items


def _dispatch(tasks, items, origin):
    stopped = False
    for task, item in zip(tasks, items):
        item.pop("validation_status", None)
        if stopped:
            item.update(dispatch_status="not_started", error_code="dispatch_stopped", error="Prior dispatch failed")
            continue
        try:
            result = core.delegate_profile(**task, **FORCED, origin=origin)
            for key in ("task_id", "profile", "run_created", "deduplicated", "paths", "watch_command"):
                if key in result:
                    item[key] = result[key]
            item["dispatch_status"] = "reused" if result.get("deduplicated") else "started"
        except Exception as exc:
            item.update(error_item(exc))
            stopped = True
    accepted = sum(item["dispatch_status"] in {"started", "reused"} for item in items)
    return {"status": "accepted" if accepted == len(items) else "partial" if accepted else "rejected", "items": items}


def multidelegate(payload, item_schema, origin):
    """Validate all items before dispatch; no batch state or capacity reservation."""
    if not isinstance(payload, dict) or set(payload) - {"tasks", "preflight"}:
        raise core.ProfileDelegateError("expected tasks/preflight object", "validation_error")
    tasks, preflight = payload.get("tasks"), payload.get("preflight", False)
    if type(preflight) is not bool or not isinstance(tasks, list):
        raise core.ProfileDelegateError("tasks must be array and preflight boolean", "validation_error")
    policy = core.load_effective_policy()
    if not 1 <= len(tasks) <= min(policy.values["max_concurrent"], policy.values["max_async"]):
        raise core.ProfileDelegateError("tasks outside configured batch limit", "validation_error")
    origin = core.normalize_origin(origin)
    if not origin["session_key"] or not core.origin_match(origin, origin)[0]:
        raise core.ProfileDelegateError("trusted routable origin required", "origin_required")
    core.require_native_async_ledger_compatibility()
    items = _validate_tasks(tasks, item_schema, origin)
    if any(item.get("dispatch_status") == "failed" for item in items):
        for item in items:
            item.pop("validation_status", None)
            if item.get("dispatch_status") != "failed":
                item.update(dispatch_status="not_started", error_code="batch_validation_failed", error="Batch validation failed")
        return {"status": "rejected", "items": items}
    if preflight:
        return {"status": "validated", "items": items, "run_created": False, "capacity_reserved": False}
    return _dispatch(tasks, items, origin)
