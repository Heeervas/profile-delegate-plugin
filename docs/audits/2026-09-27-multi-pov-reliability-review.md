# Profile Delegate multi-POV reliability review

Date: 2026-09-27
Status: review complete; implementation not authorized by this review
Scope: runtime reliability, model-facing tool/schema UX, architecture/security, historical run evidence, and current agent-project state

## Verdict

Profile Delegate is useful and materially improved, but it is not yet dependable enough to treat as transparent profile-to-profile execution.

- **Trusted single-user local use:** usable with operational caveats.
- **Shared or untrusted use:** not acceptable because inspection/maintenance authorization and per-call privilege elevation are too broad.
- **Reliability:** recent execution is better than the historical reputation, but important failures still cluster around TUI startup/turn handling, inherited environment, provider/session compatibility, and ambiguous result contracts.

This is not one bug. The dominant contributors are:

1. execution environment is inherited too broadly and reported imprecisely;
2. detached work is forced through the more fragile interactive TUI path;
3. the schema exposes too many coupled controls without request-specific preflight;
4. same-profile/nested execution has no explicit resource/lock contract;
5. successful transport can still yield an operationally useless `unknown/drifted` result;
6. model-callable read/maintenance and `approve_yolo` authority exceed the stated origin-authorized product contract.

## Evidence

### Historical run ledger

Snapshot of `/opt/data/profile_delegate/runs`:

- 706 total runs
- 580 completed
- 75 failed
- 24 cancelled
- 15 still marked running
- 12 timed out
- Among completed/failed/timed-out executions: **87.0% completed**, **13.0% failed or timed out**
- Since 2026-09-01: 78 completed, 7 failed, 3 cancelled, 1 timed out

Historical failure/error codes:

- `tui_turn_error`: 24
- `nonzero_exit`: 19
- `worker_died`: 14
- `timeout`: 12
- `tui_transport_error`: 7
- `tui_nonzero_exit`: 6
- concurrency limits: 4
- `resume_session_mismatch`: 1

These counts are execution lifecycle counts, not task-quality counts. `completed` does not imply the delegated task returned an accepted result; recent Markdown runs completed execution but produced `status=unknown` and `contract_status=drifted`.

### Concrete recent failures

- `pd_20260925_084241_vjedjz`: TUI gateway-ready timeout after 30 seconds, before useful execution.
- `pd_20260925_085434_rlatzo`: provider-realm HTTP 409 after a model/provider/session combination; not a transport retry case.
- Recent successful Markdown fiscal runs completed execution but returned an unknown/drifted task result because the required verdict protocol was not constructible from the tool schema.

### Validation

Canonical project gate reported by all three independent reviews:

```text
PYTHONPATH=/opt/hermes .venv/bin/python -m pytest -q -o 'addopts=' -W error
389 passed
```

Running outside the prescribed module path produced dozens of import/configuration-driven failures. The canonical gate is green, but installation/runtime-path sensitivity remains a product weakness and needs its own loader smoke.

## Ranked findings

### P0 — Correctness and authority

#### 1. Child environment inheritance is nondeterministic

`core.py:2089-2124` starts from `os.environ.copy()` and strips only a narrow set of session/approval variables. Execution-scoping variables such as TUI toolsets/skills/turn limits and other Hermes overlays can leak from the parent. `tui_runner.py` only overwrites some values when explicit overrides are non-empty.

**Impact:** omitted fields do not reliably mean “inherit target profile defaults”; tools, skills, model behavior, or limits can vary with caller process history.

**Change:** construct a deterministic child environment. Clear all Hermes execution-scope variables before applying persisted request values, or use an explicit allowlist plus documented credential/proxy pass-through. Persist non-secret variable provenance, never values.

#### 2. Effective capabilities are not actually effective

Build-mode `effective_execution`/`effective_capabilities` are derived from per-call overrides. Empty arrays currently mean both “inherit target profile” and “nothing resolved,” while `terminal_access=false` can coexist with a child that successfully used terminal tools.

**Impact:** models and operators cannot tell inheritance from denial or inspect the real authority granted.

**Change:** represent capability resolution explicitly:

```json
{
  "mode": "inherit|override|preset",
  "requested": [],
  "resolved": ["file", "terminal"]
}
```

Do not label unresolved values as effective.

#### 3. Run authorization is inconsistent

Steer/cancel enforce exact origin; status, global list, reconcile, and prune do not consistently apply the same ownership boundary. A model-enabled caller can inspect another session's run or invoke maintenance over shared artifacts.

**Impact:** contradicts the brief's origin-authorized contract and is unsafe outside trusted single-user operation.

**Change:** centralize `authorize_run(action, caller_origin, status)`. Default model-facing reads and controls to exact origin. Keep global inspection, reconcile, and destructive prune operator/CLI-only or behind explicit policy.

#### 4. `approve_yolo` is a model-callable privilege elevation

Per-call approval override is enabled and can set `HERMES_YOLO_MODE=1` without a parent approval broker.

**Impact:** prompt-influenced execution can widen authority beyond the target profile's default posture.

**Change:** default approval override off. If elevation is needed, require an immutable operator-issued, run-bound grant with source, scope, expiry, and requested capability persisted in artifacts.

### P1 — Reliability

#### 5. Interactive transport is valuable, but its reliability contract is incomplete

`core.py:2845-2850` selects `tui_stdio` for detached background runs unless an environment variable forces CLI. That increases startup/control-plane failure surface, but TUI is also what gives Profile Delegate its most important differentiator: live steering across profile/process boundaries. Replacing it with simple CLI by default would cure the fever by shooting the patient.

Hermes' native subagent harness confirms the right semantics to preserve:

- `AIAgent.steer()` queues text without cutting the current tool call (`/opt/hermes/agent/interrupt_control.py:217-226`);
- delivery happens at the next role-safe iteration boundary (`agent_runtime_helpers.py:3188-3224`);
- ownership is bound to the exact parent session, transport, and live session generation (`tools/delegate_tool_registry.py:124-157`);
- acceptance and completion are linearized under one registry lock, with `accepting_steer` closed before completion;
- `queued` is explicitly not `delivered`; a late accepted steer is surfaced as `missed_steer` instead of disappearing (`delegate_tool_registry.py:128-134,302-308`);
- gateway RPC reuses the same control primitive rather than inventing a second steering runtime (`tui_gateway/methods_session.py:2084-2099`).

**Change:** keep steering first-class and implement `transport_mode=auto|interactive|simple` as follows:

- `interactive`: normal/default background path; TUI RPC with native steer/interrupt/events.
- `auto`: select interactive whenever the run is backgrounded or otherwise live-steerable; degrade to simple only when interactive bootstrap fails **before prompt acceptance**, with the fallback recorded and returned.
- `simple`: explicit fire-and-forget/compatibility mode; process-owner cancellation and no steer. Its schema must state the capability loss bluntly.

Persist and fingerprint requested/selected transport. Never switch transport after prompt acceptance or ambiguous acceptance. Harden TUI startup rather than treating steer as optional polish.

#### 6. Same-profile and nested delegation semantics are accidental

There is no explicit same-profile check. Depth is an environment counter and concurrency locks are rooted in the active Hermes home. With `max_concurrent=1`, an ancestor and descendant sharing a profile home can contend for the same slot; raising concurrency only makes the behavior accidentally work.

**Change:** initially reject same-home recursive delegation with `same_profile_delegation_not_supported`. Persist `root_task_id`, `parent_task_id`, caller/target profile, depth, and resolved home identity. Add lineage-aware permits only after a real use case justifies recursion.

#### 7. Basic validation depends on config/runtime imports

Policy/config loading happens before simple request validation. Runtime import failures can therefore mask malformed request errors and make behavior interpreter/module-path sensitive.

**Change:** validate schema-local fields first, then discover target/runtime policy through an injected adapter. Add a real plugin-loader installation smoke with actionable module-path diagnostics.

#### 8. Session and provider compatibility lacks explicit preflight

`session_mode=new` does not forbid a non-empty `session_id`, and model/provider overrides can produce non-retryable provider-realm incompatibility.

**Change:** model session input as a discriminated union: new forbids ID; resume requires ID. Classify realm mismatch as `provider_session_incompatible` with a corrective action; do not retry it as transport failure.

### P2 — Model/tool UX

#### 9. The main tool schema is too flat and internally contradictory

Model/provider/reasoning/toolsets/skills/preset/approval/session controls are independent top-level fields even though their validity is coupled. JSON Schema defaults on inherited fields can become accidental overrides when clients materialize defaults.

**Change:**

- remove schema defaults from conditionally inherited fields;
- group execution, capabilities, session, transport, and authority into discriminated objects in a versioned v2 contract;
- keep a minimal backwards-compatible v1 adapter;
- make the primary example minimal rather than advertising policy-gated overrides.

#### 10. There is no request-specific preflight

`profile_delegate_policy` only returns global policy. It cannot answer whether a proposed call against a specific profile/session will work.

**Change:** add `profile_delegate_preflight` or allow `profile_delegate_policy(proposed_call=...)`. Return normalized request, resolved inherited values, all conflicts, `run_created=false`, and a complete retry payload.

#### 11. Markdown/text results are operationally brittle

The schema says Markdown/text are valid but does not expose the terminal verdict protocol. Successful transport can therefore become `unknown/drifted` with a useless one-heading summary.

**Change:** use a structured terminal envelope for every mode:

```json
{
  "status": "ok|blocked|failed",
  "content_format": "json|markdown|text",
  "content": "...",
  "artifacts": [],
  "errors": [],
  "next_steps": []
}
```

JSON should remain the machine default. Markdown/text should affect `content`, not remove machine-readable outcome fields.

#### 12. Status naming is easy to misread

Top-level `success=true` can mean only that lookup succeeded while execution completed with an unknown task result.

**Change:** expose `lookup_success`, `execution_status`, `task_status`, `contract_status`, `notification_status`, `transport_status`, and `task_success`. Keep old aliases only for compatibility.

## Recommended implementation sequence

### Version 1.11 — Deterministic execution and honest introspection

Promise: omitted execution fields reliably inherit the target profile, and artifacts accurately show what was requested, resolved, and observed.

- deterministic child environment and provenance
- explicit capability resolution
- strict new/resume session union
- local validation before runtime imports
- provider/session error classification
- status field disambiguation
- hostile-parent-env and real-loader regressions

### Version 1.12 — Steer-first interactive transport

Promise: background delegation remains steerable by default, with truthful steering lifecycle and a bounded explicit simple fallback.

- `transport_mode=auto|simple|interactive`
- `auto` prefers interactive for background/live-steerable work; simple is explicit or pre-acceptance fallback only
- native-subagent-compatible semantics: exact owner authority, `accepting_steer`, queued vs delivered, and `missed_steer`
- persist steer request/accept/delivery/miss timestamps and bounded text hashes; never claim delivery from queue acceptance
- CLI fire-and-forget execution and cancellation semantics, with steer capability reported unavailable before launch
- persisted/fingerprinted transport selection
- comparative CLI/TUI benchmark: startup latency, RSS, completion rate, cancellation, notification
- no cross-transport retry after ambiguous acceptance

### Version 1.13 — Schema v2 and request preflight

Promise: a caller can determine whether a proposed delegation will work before creating a run.

- request-specific preflight
- discriminated execution/session/capability/authority objects
- inherited/default fields represented by omission or explicit mode, not JSON Schema defaults
- structured terminal envelope for every output format
- minimal primary example and actionable retry payloads

### Version 1.14 — Authorization and graph semantics

Promise: run visibility, maintenance, elevation, nesting, and same-profile behavior are explicit and enforceable.

- centralized action authorization
- operator-only global inspection/maintenance
- run-bound approval grants; no default model-callable yolo elevation
- explicit same-home recursion rejection
- root/parent/profile/home lineage metadata
- evaluate lineage-aware permits only if a measured consumer requires recursion

### Later, only if justified

- `continue_from_task_id` with exact-origin authorization and session serialization
- retention policy after reviewing unresolved legacy runs
- remote/HTTP execution only when a real cross-host consumer exists

## What not to do

- Do not patch Hermes core to hide plugin contract problems.
- Do not raise concurrency merely to make same-profile recursion appear functional.
- Do not treat more retries as a fix for provider-realm or ambiguous-acceptance errors.
- Do not expose more tools/skills by default; fix resolution, description, and preflight first.
- Do not conflate `completed` execution with successful task outcome.

## Decision

The next implementation should be **Version 1.11: deterministic execution and honest introspection**. It addresses the user's most credible complaint—wrong profile environment/capabilities—without first expanding transport, recursion, or authority. Version 1.12 should then harden the interactive path around Hermes' proven subagent steering semantics. Steering is a core capability, not an optional transport luxury; simple CLI remains a bounded fallback for callers that knowingly give it up.
