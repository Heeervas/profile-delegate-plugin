# Profile Delegate Durable Delivery, Session Lineage, and Output Recovery Plan

> **REJECTED / SUPERSEDED (2026-07-22).** Do not implement this plan's durable-delivery, outbox, lineage-routing, Hermes-core, or cross-repository work. The accepted direction is the plugin-only reliability reset in `2026-07-22-plugin-only-reliability-reset-p0-p4.md`, limited to `/opt/data/plugins/profile-delegate`. This document is retained only as historical design context.

**Status:** Rejected and superseded; implementation must not start

**Scope:** The three approved remediation tracks only: durable detached completion delivery, compression-aware routing/session lineage, and deterministic recovery from JSON contract drift.

**Explicitly out of scope:** provider-native structured output, unrelated transient-resume work, general plugin redesign, and speculative fourth action.

## Goal

Make a background Profile Delegate run survive launcher/gateway loss, route its one terminal result to the correct logical continuation after LCM compression without leaking into a later `/new` session, and never misreport Markdown/prose contract drift as successful JSON.

## Evidence and baseline

The incident run `/opt/data/profile_delegate/runs/pd_20260722_084434_mjfe2a` completed and retained artifacts, but `notification_status=detached_worker_completed_no_live_queue`; there is no matching durable `async_delegations` row. Its child returned a useful Markdown `BLOCKED_NEEDS_FIXES` report, while normalization produced `status=ok`, `structured=false`, and `error_code=unstructured_output`.

Relevant code:

- `core.py:1720-1759`: completion is inserted only into the current process' in-memory queue.
- `core.py:1999-2019`: notification watcher is a daemon thread owned by the launching process.
- `core.py:2029-2047`: detached worker records the no-live-queue state but no replayable event.
- `core.py:1283-1312,1315-1490`: prompt, heuristic JSON candidate selection, and permissive normalization.
- `tui_runner.py:305-350`: final text is parsed immediately; task lifecycle hides contract degradation.
- `/opt/hermes/tools/async_delegation.py:127-208,266-290`: native durable dispatch/completion/replay machinery.
- `/opt/hermes/gateway/run.py:15611-15623`: `parent_session_id` pins a synthetic event, but Profile Delegate omits it.
- Hermes compression lineage can resolve an ended parent to a compression continuation; `/new` and branches must remain separate.

Baseline verification on the current tree:

- Plugin-local `.venv`: `202 passed, 31 failed`; all observed failures are caused by missing `hermes_cli` when `/opt/hermes` is absent from the import path, so that invocation is not a valid release gate.
- `/opt/hermes/.venv` does not contain `pytest` and cannot run the plugin suite directly.
- Canonical release invocation is the plugin test environment with Hermes source available: `PYTHONPATH=/opt/hermes .venv/bin/python -m pytest -q -o 'addopts='`. Capture its exact result before implementation.

## Design decision

Use a **plugin-owned durable SQLite outbox** under the caller profile's Profile Delegate runtime root, plus a plugin-owned gateway reconciler. Do not write Hermes' private `async_delegations` schema and do not depend on a detached process importing `process_registry` under the correct `HERMES_HOME`; the child TUI deliberately switches `HERMES_HOME` to the target profile.

Delivery is **at least once**. A crash after adapter acceptance but before acknowledgement may duplicate. Stronger exactly-once behavior would require a durable, idempotent parent-turn insertion contract that does not currently exist.

## State contracts

Task execution and notification delivery remain separate:

- Task lifecycle: existing run state plus result status `ok|blocked|failed`.
- Notification lifecycle: `disabled|registering|running|pending|claimed|delivered|unknown|failed`.

`queued` is removed or retained only as a compatibility alias; it must not imply durability or delivery. Status/list project outbox state and bounded error/attempt metadata.

Normative transitions:

- A normally finished child turn keeps `run.status=completed`. `result.status=ok` makes wrapper `success=true`; `result.status=blocked|failed` makes wrapper `success=false` without rewriting the run lifecycle.
- Dead-worker reconciliation uses `run.status=failed` plus `error_code=worker_outcome_unknown`; no new run-status enum is introduced.
- Notification state never changes task/run/result state. Notification persistence or delivery failures populate only notification fields.
- Status/list/spectator reads remain read-only. They may project a derived inconsistency warning but never repair artifacts.

The durable notification identity is `task_id`. Persist:

- caller profile/runtime root;
- stable physical route: platform, chat type/id, optional thread id, session key;
- logical origin: parent session ID and UI session ID;
- bounded final event and artifact paths;
- owner PID plus process start time/token;
- claim token/time, attempts, timestamps, last bounded error.

Never persist task/context/prompt/log bodies in the outbox event.

## Execution graph

`T0 baseline -> T0A gateway-surface spike -> (T1 outbox || T6 strict contract) -> T2 registration -> T3 publication -> T4 lineage contract -> T5 reconciler -> T7 recovery -> T8 lifecycle/prune -> T9 verification -> T10 review`

T1 and T6 may be implemented independently after T0A. No gateway adapter invocation is implemented before T4's compression, `/new`, and branch matrix is green. T5 depends on T1-T4; T7 depends on T6.

## Tasks

### T0 — Lock the baseline and fixtures

**Files:** tests and incident fixture only.

1. Run `PYTHONPATH=/opt/hermes .venv/bin/python -m pytest -q -o 'addopts='`; record the exact pass/fail baseline before fixtures or implementation.
2. Add a sanitized fixture derived from the incident's `stdout.txt`, `request.json`, `result.json`, and routing fields.
3. Add focused characterization tests proving current defects: launcher death loses notification; same-lane `/new` risks wrong logical session; Markdown blocked output becomes `ok`.
4. Keep the plugin-local missing-`hermes_cli` failure documented but do not bless it as a product regression.

### T0A — Prove the supported gateway surface

**Files:** spike tests only; production changes follow only after the decision.

1. Prove `pre_gateway_dispatch` registration, access to the live gateway/session store, and capture of `asyncio.get_running_loop()`.
2. Prove bounded internal delivery and acknowledgement through the candidate interface.
3. Treat `_inject_watch_notification`, `_session_db`, and equivalent underscore-prefixed state as private. Decide explicitly whether version-pinned private coupling is accepted.
4. Preferred decision: add the smallest generic public Hermes methods for bounded internal injection and compression-tip/lane inspection if the public plugin surface is insufficient. Include `/opt/hermes` tests and review scope for that minimal change.
5. Stop before T1 if neither path can prove delivery, ACK semantics, and no lane mutation.

### T1 — Build the caller-owned durable outbox

**Files:** create `notification_outbox.py`; modify tests and `core.py`.

1. Create versioned SQLite schema with WAL, busy timeout, transactions, one row per `task_id`, and bounded fields.
2. Implement register/readback, transition to pending, claim with lease, release, acknowledge, and state projection.
3. Keep delivered retention bounded. Never silently evict pending rows; reject new notifying dispatches at a documented hard cap.
4. Recover dead `running` producers as `unknown`, using `(pid, process-start identity, token)`, not PID alone.
5. Canonicalize the caller-owned runtime root once at trusted dispatch; never derive it from child-controlled values or target-profile `HERMES_HOME`.
6. Require ownership by the current UID; reject symlinks/root escape; create directories as `0700` and DB/WAL/SHM/event files privately; cap every persisted field before the transaction.

**Tests:** transaction/readback failures, concurrent claim, stale lease, PID reuse, pending retention, bounded payload, wrong profile/UID, malicious path, symlink, root escape, and oversized event.

### T2 — Make dispatch registration race-free

**Files:** `__init__.py`, `core.py`, tests.

1. For `background=true && notify_on_complete=true`, capture trusted gateway context before child work: caller profile, canonical caller home/runtime root, platform, chat type/id, optional thread id, session key, parent session ID, origin UI session ID, and async-delivery capability.
2. Capture chat/thread fields from gateway session context, never model arguments or session-key parsing. Reject the notifying dispatch if any required route/lineage/capability field is unavailable.
3. Spawn the detached worker behind an execution gate and require it to register/read back the outbox row before releasing the child TUI.
4. Parent publishes worker identity before returning; worker and parent must not stale-overwrite each other's lifecycle fields.
5. On registration timeout, EOF, mismatch, or status-publication failure, terminate and reap the exact process group; return no async success handle.
6. `notify_on_complete=false` bypasses registration and remains pollable.

**Tests:** pause each side of the handshake; prove no pre-registration child launch and no orphan worker after post-`Popen` persistence failure.

### T3 — Persist one terminal event from the worker

**Files:** `core.py`, `tui_runner.py`, `notification_outbox.py`, tests.

1. Commit in this strict atomic-replace order: `result.json` → terminal `status.json` → `notification_event.json` → `completion_manifest.json` → outbox `pending` transaction. The manifest rename is the authoritative file-set commit point; no notification is claimable before it exists and validates.
2. `completion_manifest.json` schema V1 is exactly: `schema_version=1`, `task_id`, `committed_at`, `run_status`, `result_status`, `result_schema_version`, and `files`, where `files` contains exactly `result.json`, `status.json`, and `notification_event.json`, each with relative `path`, UTF-8 byte `size`, and lowercase SHA-256. It contains no prompt/log/task body.
3. `notification_event.json` contains the bounded route, logical lineage, normalized result/recovery metadata, and artifact paths. Its bytes are final before the manifest hash is computed.
4. After manifest write/readback and hash verification, transactionally move the pre-registered outbox row to `pending` with those exact event bytes; require affected-row/readback verification.
5. Emit no interim event and no in-memory-only fallback. If outbox publication fails after a valid manifest, preserve task/result state and expose only `notification_error_code=durable_notification_persistence_failed`; startup retries the idempotent publication.
6. Startup repair runs under the run lock and follows this deterministic table:
   - no manifest, valid `result.json`: treat result as the outcome authority; regenerate terminal status and event deterministically from result plus trusted request route, replace any mismatching later partial artifact, write/verify the manifest, then publish pending;
   - no manifest, missing/invalid result: outcome is unknowable; preserve corrupt bytes under a bounded diagnostic filename, commit a synthesized `result.status=failed`, `run.status=failed`, `error_code=artifact_commit_incomplete`, then event/manifest/pending in normal order;
   - valid manifest, hashes valid, outbox not pending/delivered: idempotently publish its exact event bytes as pending;
   - manifest missing/invalid while an outbox row is already pending/claimed: revoke the claim, mark notification persistence/integrity failed, and never deliver until repair creates and verifies a valid manifest;
   - manifest present but any file hash/size/task ID mismatches: preserve evidence, set `notification_error_code=artifact_integrity_failed`, and never deliver or silently rewrite a committed set.
7. Status/list/spectator paths remain read-only and may only project the detected inconsistency.

**Tests:** kill/fail at each write/rename/readback boundary; assert one recoverable truthful state.

### T4 — Lock the physical-lane and logical-lineage contract

**Files:** route/lineage tests and the interface chosen by T0A.

1. Resolve `parent_session_id` through compression-only continuation semantics and obtain the current tip.
2. Read the physical lane's current durable session before injection. Permit delivery only when it equals the resolved tip or is proven to belong to the same compression-only lineage.
3. Otherwise keep the row pending with `logical_lane_moved`; perform no `switch_session`, adapter call, lane mutation, latest-session fallback, or delivery to `/new`/branch sessions.
4. Pass the resolved live tip—not the ended parent—as `gateway_session_id`.
5. Treat physical route validity and logical conversation validity as independent mandatory checks.
6. Complete the A-live, A→A2 compression, A→B `/new`, explicit branch, missing lineage, and temporary-adapter matrix before T5.

### T5 — Add the plugin gateway reconciler

**Files:** create `gateway_reconciler.py`; modify `__init__.py`, `plugin.yaml`, tests, plus only the minimal public Hermes surface selected by T0A.

1. Capture the live gateway and event loop through the supported hook; start one reconciler scoped to the active caller profile/outbox, not to the inbound lane that activated it.
2. Process all validated rows whose platform adapter is served by that caller-profile gateway. The activating hook event never authorizes or rewrites persisted routes.
3. Apply T4's lineage guard before claiming/injection, construct a bounded internal event, and schedule the chosen gateway interface thread-safely.
4. Mark delivered only when adapter injection returns `True`; release/retry on `False`, exception, temporary adapter absence, or stale lease with bounded backoff.
5. Do not send directly to Discord/Telegram and do not forge Hermes private `async_delegation` ledger rows.
6. Prove a reconciler activated by one lane later delivers valid pending rows for another lane on the same caller-profile gateway.
7. Document the restart boundary honestly: a restarted gateway may need its first inbound event before attachment; once attached, idle polling delivers later completions.

**Fault test:** launch, kill/recreate launcher/gateway before completion, finish detached worker, reactivate the hook, assert one accepted delivery and durable ACK.

### T6 — Enforce the result schema strictly

**Files:** `core.py`, `tui_runner.py`, tests.

1. Define versioned base-envelope schema: require `status`, `summary`, `artifacts`, `errors`, `next_steps`; exact base types; status in `ok|blocked|failed`. Allow additional output-contract-specific keys only when that contract names them; unknown keys otherwise fail validation.
2. Missing/invalid fields become `contract_invalid`; never default missing or unstructured status to `ok`.
3. Replace semantic scoring of arbitrary embedded objects with deterministic candidate rules:
   - whole-output JSON first;
   - exactly one V1 block second, using literal standalone lines `<<<PROFILE_DELEGATE_RESULT_V1>>>` and `<<<END_PROFILE_DELEGATE_RESULT_V1>>>`, with only the JSON object between them;
   - if multiple contract-valid candidates remain, return `ambiguous_json_candidates`.
4. The generated child prompt prints those two literal delimiter lines, delimits task/context as data, and restates the immutable serialization protocol after caller-controlled text. Generic Markdown JSON fences are not protocol delimiters.
5. Make `blocked` consistently non-successful for the execution wrapper while preserving it as a valid result status.

### T7 — Add deterministic one-pass local recovery

**Files:** `core.py`, `tui_runner.py`, tests.

Recovery order, with no second model call:

1. strict whole-output JSON parse;
2. exactly one literal `PROFILE_DELEGATE_RESULT_V1` block parse; zero, nested, reversed, or multiple blocks fail deterministically, and generic fenced/embedded JSON is not selected;
3. conservative lexical repair of the whole output or the one literal block, limited to UTF-8 BOM removal and one trailing comma before `}`/`]`, followed by full schema validation;
4. Markdown recovery only after normalizing the first nonblank ATX heading by removing its `#` prefix, trimming whitespace, and stripping one matching outer code-span delimiter. The normalized heading must then match the versioned grammar `^(OK|BLOCKED|FAILED)(?:_[A-Z0-9_]+)?$`; this explicitly admits the incident heading ``## `BLOCKED_NEEDS_FIXES` `` without accepting a token buried in prose.

Rules:

- Arbitrary prose without an unambiguous token fails `unstructured_output`.
- Recovered Markdown preserves the full report as raw output and maps status conservatively; never infer `ok` from generic prose.
- Record `structured`, `recovered`, `recovery_method`, candidate count, selected span, raw path, byte/character count, SHA-256, and truncation/partial flags.
- For the incident fixture, recover `blocked` and retain blocker/check/path content; never collapse it to a heading-only `ok` summary.
- Build the recovered summary deterministically from the normalized terminal heading plus, in source order, at most one section from each category: blocker/error, verification/check, and path/artifact. Include at most three sections total and cap the final summary at 2,000 UTF-8 bytes, truncating only at a valid code-point boundary and appending `…`; raw output remains the provenance artifact.
- Oversized or incomplete TUI output preserves bounded raw/partial evidence and yields `output_truncated` or `parse_failed`, not silent loss.

### T8 — Harden adjacent lifecycle and pruning required by the three tracks

**Files:** `core.py`, outbox, tests.

1. Add heartbeat/lease reconciliation for detached workers; stale runs become `run.status=failed`, `error_code=worker_outcome_unknown` under lock.
2. Make duplicate reuse and async capacity depend on valid worker identity/lease, never live dispatcher PID.
3. Default prune may remove a run only after an outbox read proves `notification_state=delivered`, or `notification_state=disabled` for `notify_on_complete=false`. Every other state—including registering, running, pending, claimed/stale claim, unknown, failed, and persistence-error—is undelivered and protected. Outbox read/corruption/lock errors fail closed.
4. Surface task status, result status/structure/recovery, notification state/attempts/error, and worker activity separately.

These are included only where necessary to prevent the approved delivery/recovery mechanisms from lying or deleting their only evidence.

### T9 — Verification and release gates

Run from `/opt/data/plugins/profile-delegate`:

```bash
PYTHONPATH=/opt/hermes .venv/bin/python -m pytest -q -o 'addopts='
.venv/bin/ruff check __init__.py core.py tui_runner.py notification_outbox.py gateway_reconciler.py test_profile_delegate.py
PYTHONPATH=/opt/hermes .venv/bin/python -m py_compile __init__.py core.py tui_runner.py notification_outbox.py gateway_reconciler.py
PYTHONPATH=/opt/hermes .venv/bin/python cli_smoke.py --help
git diff --check
git status --short
```

Run memory-heavy full-suite and real-background gates serially; before each, require enough cgroup headroom and no unrelated delegated workers. This 2 GiB runtime has already OOM-killed a concurrent full-suite + Reviewer run.

Then run fault/integration smokes with fake Hermes/TUI and isolated DBs:

1. launcher/gateway death after detached spawn, restart, completion, one durable delivery;
2. completion during A -> A2 compression;
3. same-lane `/new` A -> B does not receive A's result;
4. adapter absent then available, one eventual delivery;
5. ACK failure/restart does not silently claim success; duplicate risk is observable;
6. incident Markdown fixture recovers as blocked;
7. arbitrary prose and ambiguous JSON fail closed;
8. worker SIGKILL and disk-write fault reconcile truthfully;
9. default prune preserves undelivered runs.

Finally run one harmless real Profile Delegate background smoke from a fresh parent session. Verify the result and outbox/state artifacts independently; a worker summary is not proof.

### T10 — Independent review

Reviewer receives:

- this plan and accepted scope;
- final diff, baseline and post-change test outputs;
- fault-test artifacts and real smoke task ID/path;
- explicit list of any `/opt/hermes` modifications;
- residual-risk statement.

Mandatory findings are fixed and all affected gates rerun before release.

## Acceptance criteria

1. Notifying detached work cannot start without durable registration/readback.
2. Launcher/gateway loss does not lose the final completion artifact/event.
3. One terminal producer event exists per `task_id`; delivery is durable at least once.
4. Physical lane plus logical parent lineage are both validated.
5. Compression continuation receives the result; `/new`, branches, and unrelated sessions do not.
6. Temporary route/adapter absence retries without restart once the reconciler is attached.
7. Missing/invalid JSON cannot become `status=ok`.
8. The incident Markdown report becomes a truthful blocked result with raw provenance.
9. Ambiguous/multiple JSON candidates and arbitrary prose fail closed.
10. Result-contract degradation is visible in status/list output.
11. Worker death, partial artifact commits, and PID reuse cannot leave a permanently credible `running` state.
12. Default prune can delete only proven delivered or explicitly notification-disabled runs; every undelivered/error state is protected and outbox errors fail closed.
13. Focused, full, fault, and real smoke gates pass; Reviewer returns no unresolved blocker.

## Residual risks

- At-least-once delivery can duplicate after adapter acceptance and before outbox ACK. The event/task ID must be visible for reconciliation.
- “Delivered” means gateway adapter acceptance, not proof that the parent LLM finished processing or the platform displayed the message.
- If plugin hooks cannot attach a reconciler until the first inbound event after gateway restart, zero-inbound autonomous restart delivery is not promised. Achieving that stronger contract requires an explicit Hermes startup extension point, not wishful threading.
- Local Markdown recovery is intentionally conservative; unusual but useful prose may remain a visible contract failure rather than being guessed into success. That is the correct failure mode.