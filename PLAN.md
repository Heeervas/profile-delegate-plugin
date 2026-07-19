# Duplicate Call Prevention Implementation Plan

**Goal:** Prevent repeated parent calls caused by deterministic override failures and concurrent identical submissions, without broadening delegated capabilities.

**Architecture:** Keep the fix plugin-native and concentrated in `core.py` plus the thin registration wrapper. Add one typed/effective policy loader, one aggregate preflight validator, one read-only policy tool, and one fingerprint lock around active-run lookup plus run creation. Preserve existing artifacts and subprocess execution paths.

**Execution graph:** `T1 review -> T2 regression tests -> T3 core/config implementation -> T4 schema/docs/version -> T5 full checks -> T6 live smokes -> T7 reviewer acceptance`

## Options compared

1. **Recommended — compact policy loader + preflight + dedicated policy tool + locked active dedupe.**
   - Smallest complete fix. Existing execution flow stays intact; policy becomes discoverable; deterministic failures become one-shot repairable; dedupe is limited to active identical requests.
   - Cost: adds a policy type/normalizer and a small lock/index scan.

2. **Schema-only generated descriptions + richer exceptions, no policy tool.**
   - Fewer registered tools, but callers cannot reliably inspect policy after startup/config drift and descriptions become bloated/stale. Does not give a stable machine-readable inspection surface.
   - Reject: insufficient for acceptance criterion 1.

3. **Persistent SQLite idempotency/config subsystem.**
   - Strong indexing and lifecycle history, but introduces migration/schema/locking complexity for a local plugin already using atomic JSON artifacts and flock.
   - Reject: overbuilt; higher corruption and migration risk.

4. **Prompt/env-only mitigation.**
   - Cheap, but leaves invisible policy, sequential failures, reasoning ambiguity, and the real duplicate launch intact.
   - Reject: not a fix.

## Config contract and precedence

Effective value precedence, lowest to highest:

1. hardcoded safe defaults and absolute bounds;
2. `plugins.entries.profile-delegate` YAML;
3. matching `PROFILE_DELEGATE_*` environment variable when explicitly present;
4. per-call value only for request fields and only when the effective policy allows it.

Migration/failure behavior:

- Missing YAML preserves current behavior: target allowlist required; explicit workdir rejected without roots; toolset/skill overrides rejected; approval `deny`; current conservative limits.
- Empty YAML allowlists mean deny-all for that override, never “unrestricted.”
- Malformed types, invalid enums, unsafe bounds, or contradictory timeout bounds return `configuration_error` before a run directory is created. They do not fall back to a broader default.
- Legacy `child_approval_mode: strip_only` remains the sole explicit compatibility coercion and maps to `deny`.
- Environment variables remain backward-compatible operator overrides. Invalid explicitly-set env values fail closed rather than being ignored.
- Secrets/paths to private artifacts are not exposed by policy inspection. Allowed workdir roots and named capability/profile allowlists are considered non-secret operational policy.

Proposed YAML shape (only implemented knobs, no speculative nesting):

```yaml
plugins:
  entries:
    profile-delegate:
      child_approval_mode: deny
      allowed_profiles: [builder, reviewer]
      allow_all_profiles: false
      allowed_workdirs: [/opt/data]
      allowed_toolsets: []
      allowed_skills: []
      max_depth: 1
      max_concurrent: 1
      max_async: 2
      default_timeout_seconds: 1200
      max_timeout_seconds: 1800
      max_transient_resumes: 2
      duplicate_guard:
        enabled: true
        active_window_seconds: 120
```

## API behavior

- Add `profile_delegate_policy` returning bounded effective non-secret policy plus `config_sources` and managed-scope reasoning state (`inherit_only` or `override_available`).
- Add `reasoning_mode: inherit|override` (default `inherit`). `reasoning_effort` is valid only with `override`; `none` remains a real explicit effort. For backward compatibility, supplying `reasoning_effort` without `reasoning_mode` is treated as explicit override, while omission means inherit.
- Add `duplicate_policy: reuse|new` (default `reuse`). `new` is the explicit intentional-duplicate escape hatch.
- Aggregate capability/reasoning preflight errors. Deterministic errors include `unsupported_fields`, `retry_patch`, `retryable`, `run_created:false`, and bounded effective policy.
- Before any run artifact mutation, compute SHA-256 over normalized origin, target/session inputs, task/context/contract hashes, workdir, execution/capability/approval settings. Under an exclusive fingerprint lock, scan only active runs inside the configured short window. Return the active task with `deduplicated:true`; completed runs are never silently reused. `duplicate_policy:new` bypasses reuse.

## Tasks and verification

### T1 — Reviewer design gate
- Reviewer reads `STATE.md`, this plan, and relevant implementation ranges.
- Mandatory feedback is incorporated before production edits.

### T2 — Regression tests (RED)
Modify `test_profile_delegate.py` to cover:
- YAML/env precedence and malformed fail-closed config;
- policy tool output;
- combined unsupported `toolsets` + `skills` response;
- nested managed-scope inheritance, and explicit `none` override conflict with one corrective patch;
- no run artifact on preflight failure;
- locked identical active reuse and `duplicate_policy:new` bypass;
- exact one run creation under concurrent identical calls.

### T3 — Minimal core implementation (GREEN)
Modify `core.py` only: policy loading/validation, structured errors, preflight, reasoning state, fingerprint lock/reuse.

### T4 — Thin API/docs/version
Modify `__init__.py`, `README.md`, and `plugin.yaml`: register policy tool, schema fields/descriptions, YAML example, migration notes, version alignment.

### T5 — Checks
Run:
- `/opt/hermes/.venv/bin/python -m pytest . -q`
- `/opt/hermes/.venv/bin/python -m py_compile __init__.py core.py child_bootstrap.py cli_smoke.py`
- Ruff if available; otherwise report unavailable, not fabricated.
- inspect `git diff --check` and `git diff --stat`.

### T6 — Live smokes without gateway/config mutation
- default → reviewer, valid call with no disallowed overrides;
- default → builder, where builder invokes reviewer with inherited reasoning (no explicit override);
- inspect parent result, child session IDs, and run/session artifacts; prove each valid parent submission created one child run.

### T7 — Independent acceptance review
Reviewer checks diff, test output, smoke artifacts, capability posture, and migration guidance. Mandatory findings are fixed and rechecked.
