# Operator activation and rollback — prepared only

## Candidate configuration

No production change has been applied. After Alberto explicitly approves activation, merge ONLY these keys into the caller plugin entry, preserving all existing target/workdir/capability allowlists:

```yaml
plugins:
  entries:
    profile-delegate:
      child_approval_mode: profile  # omission default, NOT an authority ceiling
      allow_child_approval_override: true  # explicit caller grant for task selection
      child_approval_modes_by_profile:
        builder: profile
        reviewer: deny
```

The named targets must already exist and be permitted by target admission. `approve_yolo` remains an alias for `yolo`. Operator map choices are omission defaults; admitted explicit task selectors take precedence. `allow_child_approval_override` is real caller-side authority, false by default, and does not override frozen ancestry. New omitted configuration defaults profile; existing explicit production deny remains deny until approved. The previous operator-only acceptance is superseded for per-task selection by `PER_TASK_REPAIR.md`; runtime repair acceptance remains pending.

Optional separately approved native Builder posture:

```yaml
approvals:
  mode: manual
  single_query_mode: approve
  unattended_mode: approve
```

Preserve existing `approvals.deny`, security knobs and permanent `command_allowlist`; do not overwrite the entire approvals mapping. This allows ordinary unattended consent while direct interactive manual prompts remain available. It does not promise smart LLM screening. Native off/yolo are broader bypass alternatives and are NOT the recommended default or applied here. Approval bypass does not automatically consent to shell hooks.

## Activation procedure (controller/operator, after approval)

1. Record private exact pre-change caller and target config/code selections. Never copy credential-bearing whole configurations into this repository.
2. Apply only the explicitly approved keys. Keep other profiles' selectors/postures unchanged. Validate target map and inspect `profile_delegate_policy` / a harmless preflight.
3. Start a fresh gateway/process through its existing supported operator mechanism. A loaded process does not hot-load code/schema reliably. Builder has NOT restarted it.
4. In a NEW admitted delegation, inspect native envelope source, permanent grants, denies, unattended posture, bypass and fingerprint. Run harmless project read/test before allowing valuable changes. Frozen resumed runs retain their original authority and must not be widened by config edits.
5. Inspect actual completion, tool/guard events and file state; an ACK/worker assertion alone is insufficient.

## Rollback

1. Restore only the pre-activation plugin selector/map and separately approved native posture keys; production's previous explicit deny is the safe known selector.
2. Restore the feature-owned code revision through the operator's approved deployment mechanism while preserving incoming unrelated continuity edits. Do not `git reset --hard`, `git clean`, delete private run artifacts or replay old snapshots over live work.
3. Restart/fresh-load through the same approved operator mechanism; verify policy with a harmless NEW preflight/delegation.
4. Keep existing run evidence and frozen envelopes. Historical missing snapshots remain deny; explicit historical approve_yolo retains alias semantics. Malformed/conflicting present snapshots refuse. Cancelled requested-only attempts do not establish a new authority grant; observed identity evidence is required.

## Recovery and limits

For fresh consent refusal, inspect `approval_events.jsonl` (`approval_required` versus `policy_denied`), status and partial artifacts. With no broker, obtain operator approval for a NEW admitted authority context when needed; never retry a prohibited action via another interpreter/profile/tool. Continue existing implementation sessions whenever their frozen authority remains valid.

`profile` and `inherit` choose policy sources, not ordered privilege levels. Inherit takes caller permanent grants/posture, excludes transient grants/credentials, and retains target/ancestor prohibitions. Nested transitions support frozen inherit or deny; unsupported widening/source switching refuses before spawn. Native execute_code follows local/isolated/host-access policy but is not a command-level sandbox.

Review, quality and real acceptance receipts: `ACCEPTANCE.md`. No activation, restart, publication or production migration is included in Builder's completion.
