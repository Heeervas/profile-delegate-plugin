"""Native approval source and historical resume resolution, plugin-local."""
from pathlib import Path
import os
from typing import Any, Dict
import core
from core import EffectivePolicy, ValidatedProfile, ProfileDelegateError

def _resume_record_matches(request, status, target, session_id):
    if request.get("profile_home") != target.home:
        return False
    recorded_ids = {status.get("child_session_id"), status.get("session_id")}
    if session_id in recorded_ids:
        seeded = session_id == request.get("requested_session_id")
        if seeded and status.get("status") in {"cancelled", "failed", "timed_out"}:
            evidence = status.get("session_identity_evidence")
            history = status.get("recovery_history", [])
            if not isinstance(history, list) or not isinstance(evidence, (str, type(None))):
                return False
            observed = evidence in ("post_interrupt_observed", "native_observed") or any(
                item.get("session_id") == session_id and type(item.get("exit_code")) is int
                and item["exit_code"] == 0
                for item in history if isinstance(item, dict))
            if not observed:
                return False
        return True
    return any(sid and core.compression_continuation(Path(target.home), sid, session_id,
                                               profile=target.canonical, cli_footer=True)
               for sid in recorded_ids)


def resume_native_approval(policy: EffectivePolicy, target: ValidatedProfile, session_id: str) -> Dict[str, Any]:
    """Read-only resume lookup: reuse one unambiguous frozen source snapshot."""
    import native_approval
    matches = []
    root = core.get_runs_root()
    if root.is_dir():
        for directory in root.iterdir():
            if not directory.is_dir() or directory.is_symlink():
                continue
            try:
                request = core.read_json_file(directory / "request.json")
                status = core.read_json_file(directory / "status.json")
                if core._resume_record_matches(request, status, target, session_id):
                    if "native_approval" in request:
                        matches.append(native_approval.validate(request["native_approval"]))
                    else:
                        legacy = EffectivePolicy(dict(policy.values), dict(policy.sources))
                        legacy.values["child_approval_mode"] = native_approval.selector(request.get("child_approval_mode") or "deny")
                        legacy.values["child_approval_modes_by_profile"] = {}
                        matches.append(core.resolve_native_approval(legacy, target))
            except ProfileDelegateError:
                continue
    if matches:
        if any(value != matches[0] for value in matches):
            raise ProfileDelegateError("resume approval snapshots conflict; create a new session", "approval_policy_error")
        if matches[0] is not None:
            frozen = matches[0]
            ancestor_path = os.getenv("PROFILE_DELEGATE_APPROVAL_REQUEST")
            if ancestor_path:
                try:
                    native_approval.admit_resume(frozen, native_approval.read_request(Path(ancestor_path)))
                except ValueError as exc:
                    raise ProfileDelegateError(str(exc), "approval_policy_error") from exc
            return frozen
    # Unknown or historical persisted session never acquires the new default.
    legacy_policy = EffectivePolicy(dict(policy.values), dict(policy.sources))
    legacy_policy.values["child_approval_mode"] = "deny"
    legacy_policy.values["child_approval_modes_by_profile"] = {}
    return core.resolve_native_approval(legacy_policy, target)


def resolve_native_approval(policy: EffectivePolicy, target: ValidatedProfile) -> Dict[str, Any]:
    import native_approval
    try:
        from hermes_cli.config import load_config_readonly
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        caller_config = load_config_readonly()
        token = set_hermes_home_override(target.home)
        try:
            target_config = load_config_readonly()
        finally:
            reset_hermes_home_override(token)
        target_modes = policy.values["child_approval_modes_by_profile"]
        target_selected = target.canonical in target_modes and policy.sources["child_approval_mode"] != "env"
        mode = target_modes[target.canonical] if target_selected else policy.values["child_approval_mode"]
        source = "operator_target" if target_selected else policy.sources["child_approval_mode"]
        ancestor_path = os.getenv("PROFILE_DELEGATE_APPROVAL_REQUEST")
        ancestor = native_approval.read_request(Path(ancestor_path)) if ancestor_path else None
        from tools import approval
        return native_approval.snapshot(
            mode, source, str(core.get_hermes_home_path()), target.home,
            caller_config, target_config, approval.is_approval_bypass_active(), ancestor,
        )
    except Exception as exc:
        raise ProfileDelegateError(f"native approval snapshot refused: {exc}", "approval_policy_error") from exc
