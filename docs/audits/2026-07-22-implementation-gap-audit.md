# Profile Delegate implementation gap audit — 2026-07-22

> **HISTORICAL / SUPERSEDED — DO NOT IMPLEMENT.** This audit predates the accepted plugin-only reliability reset in `../plans/2026-07-22-plugin-only-reliability-reset-p0-p4.md`. Its outbox, reconciler, durable-delivery, and Hermes-core recommendations were explicitly rejected and remain out of scope. Retained only as decision history.

## Historical verdict

**SUPERSEDED — the former durable-delivery direction was rejected.**

Current evidence:

- cgroup limit is now 3 GiB; current run showed no OOM events.
- Canonical suite: `235 passed, 4 failed` in 14.86 s.
- Dirty implementation: strict parser/recovery work plus a standalone SQLite outbox prototype.
- No production code imports or uses `NotificationOutbox`; no reconciler or manifest exists.

## What is implemented

### Output foundation

- Literal V1 result delimiters and prompt protocol in `core.py`.
- Whole-output or single-delimited-block JSON parsing.
- Exact base-field type validation.
- Conservative Markdown recovery for status-first reports such as `BLOCKED_NEEDS_FIXES`.
- Arbitrary prose now fails instead of defaulting to `ok`.

### Outbox foundation

- Standalone SQLite row lifecycle: register, publish, claim, release, acknowledge.
- WAL and busy timeout.
- Basic payload cap and owner check.
- Focused unit-test skeleton.

## Blocking gaps, in dependency order

### 1. Correct the partial foundations before integration

#### Parser/recovery

- `blocked` still yields wrapper `success=true` in `core.py` and `tui_runner.py`; success must require `result.status == "ok"` while run lifecycle remains `completed`.
- Parser failures collapse multiple/reversed/nested/invalid V1 blocks into generic `None`; add a typed parse outcome with explicit `ambiguous_json_candidates`/invalid-delimiter errors, candidate count, selected span, method and repair flag.
- Delimiters are matched as substrings, not literal standalone lines.
- Recovery provenance required by the plan is incomplete: raw byte/character count, SHA-256, selected span, candidate count and truncation/partial flags are absent.
- Markdown section selection loops by category rather than preserving source order.
- Additional output-contract keys are accepted indiscriminately; define and enforce the contract-specific allowed-key set or explicitly relax the plan.
- Remove obsolete heuristic candidate-scoring helpers once no caller uses them.

#### Outbox

- Root symlink rejection is broken because `_private_root()` resolves before checking; the focused security test fails.
- Validate DB/WAL/SHM paths with no-follow/ownership checks and private modes; do not chmod a potentially pre-existing symlink target.
- Add `PRAGMA user_version`, schema migration/rejection, state constraints and an explicit durability setting.
- Validate/bound task ID, route fields, owner token and run path confinement.
- Persist process-start identity, not PID alone.
- `publish()` must accept manifest-verified exact event bytes, validate matching task ID and refuse overwriting delivered/invalid states.
- Add pending-cap backpressure, delivered retention and stale-claim/abandoned-owner recovery.

### 2. Capture a trusted return address

Current `_current_origin()` lacks chat ID, chat type, thread ID, parent session ID and async-delivery capability.

Implement:

- capture `platform`, `chat_id`, `thread_id`, `session_key`, current durable session ID, caller profile/UI ID and `async_delivery_supported()` at tool call time;
- add chat type to Hermes session context or obtain it from a supported gateway context surface—do not parse the session key;
- reject `background && notify_on_complete` before child work when route/lineage/capability is incomplete;
- keep `notify_on_complete=false` pollable.

The `pre_gateway_dispatch` hook runs before auth and before session lookup. It is suitable to activate a profile-scoped reconciler, **not** to authorize rows or capture the task's parent session.

### 3. Add the race-free detached registration handshake

No handshake exists. Current code starts the detached process, then writes PID/status, then returns an async handle.

Required:

- parent/worker readiness pipe or socketpair plus a closed execution gate;
- durable outbox registration/readback before child Hermes launches;
- process-start identity and owner token readback;
- parent publishes PID metadata without stale worker-field overwrite;
- timeout/EOF/mismatch/status-write failure terminates and reaps the exact process group and returns no async handle;
- capacity and duplicate reuse consult durable owner identity/lease.

### 4. Implement transactional terminal publication

No `notification_event.json`, `completion_manifest.json`, manifest verification or startup repair exists. Result and status remain separate writes.

Implement the approved order:

1. `result.json`
2. terminal `status.json`
3. `notification_event.json`
4. `completion_manifest.json` as authoritative commit point
5. outbox `pending` transaction using exact verified event bytes

Add deterministic repair under the run lock for every partial-write boundary. Status/list/spectator remain read-only.

Remove the launcher-owned daemon notification watcher and `_push_profile_delegate_completion` in-memory queue path after durable publication is proven. The detached worker must be the sole terminal producer.

### 5. Add a minimal safe Hermes gateway surface

Supported today:

- `pre_gateway_dispatch` hook exposes `gateway` and `session_store`.
- `SessionDB.get_compression_tip()` follows compression-only lineage.
- `SessionStore.lookup_by_session_id()` exists.

Unsafe/private today:

- `_inject_watch_notification()` is private.
- Existing pinned-event flow may call `switch_session()`, which can mutate a `/new` lane back to an older live session.
- There is no public non-mutating lookup by physical session key and no public guarded completion-injection method.

Smallest safe core change:

- public/non-mutating `SessionStore.lookup_by_session_key(session_key)`;
- public gateway method such as `deliver_internal_completion(text, route, origin_session_id)` that:
  1. validates route and adapter;
  2. reads the lane's current session without creating/switching it;
  3. resolves origin through compression-only tip;
  4. accepts only when current lane equals that tip;
  5. performs no `switch_session`, latest-session fallback or lane mutation;
  6. returns `True` only after adapter acceptance.

Tests must prove A→A, A→A2 compression, A→B `/new` refusal, branch refusal, missing lineage refusal and no adapter call/lane mutation on refusal.

### 6. Implement the profile-scoped reconciler

Missing entirely: `gateway_reconciler.py`, hook registration and manifest declaration.

Required:

- one reconciler per caller-profile gateway/outbox, activated by the supported hook;
- hook event activates only; it never authorizes or rewrites persisted routes;
- claim pending rows, validate manifest, invoke the public guarded delivery method thread-safely;
- ACK only on `True`; release/retry on temporary failure/adapter absence;
- stale claim lease recovery;
- activation from one lane must process valid rows for other lanes served by the same profile gateway;
- document first-inbound-after-gateway-restart activation boundary.

### 7. Make lifecycle/status/prune truthful

- Add heartbeat/lease reconciliation; dead workers become `run.status=failed`, `error_code=worker_outcome_unknown` under lock.
- Use PID + process-start identity/token to defeat PID reuse.
- Project run, result, recovery and notification states separately in status/list.
- Default prune currently deletes any old terminal run. It must fail closed unless outbox proves `delivered`, or notification is explicitly `disabled`.
- Protect every undelivered/error/unknown/registering/running/pending/claimed state and outbox read/corruption/lock failures.

### 8. Finish documentation, metadata and evidence

- Update `plugin.yaml` hook declaration/version and README; current docs still promise best-effort queue delivery and permissive nested JSON extraction.
- Fix four current tests by aligning obsolete fixtures with the approved strict contract; do not loosen the parser to preserve warning-prefixed embedded JSON.
- Fix Ruff unused import.
- Add boundary fault tests, restart/replay, compression/`/new` matrix, adapter retry, SIGKILL, disk-write fault, prune protection and exact-event integrity tests.
- Run full suite, Ruff, compile, CLI smoke, one harmless real background delegation from a fresh parent session and independent review.

## Current failing tests

1. `test_symlink_root_rejected` — real outbox security defect.
2. `test_delegate_parses_warning_prefixed_stdout_outer_envelope` — obsolete permissive fixture; convert to literal V1 block.
3. `test_session_id_footer_helpers` — footer test incorrectly assumes embedded warning-prefixed JSON remains accepted; separate footer behavior from parser contract.
4. `test_detached_background_worker_finalizes_completed_run` — `/bin/echo` prose now correctly fails; replace with a fake executable emitting a valid V1 result, or assert failure if the test is about prose.

## Recommended execution waves

1. Parser/outbox foundation corrections and green focused/full suite.
2. Trusted route capture + handshake.
3. Manifest publication + startup recovery.
4. Minimal Hermes public guarded-delivery surface + lineage matrix.
5. Reconciler.
6. Lifecycle/prune/status.
7. Fault tests, real smoke, docs/version and independent review.
