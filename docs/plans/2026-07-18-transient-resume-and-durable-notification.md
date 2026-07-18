# Profile Delegate Transient Resume and Durable Parent Notification Spec

> **For Hermes:** Implement with strict TDD. This document is the recovery source after context compaction. Do not modify unrelated dirty files or redesign the runner beyond this contract.

**Goal:** Recover a delegated profile from recognized transient provider/stream failures by resuming the same Hermes session up to two times, while guaranteeing one durable final completion event back to the parent agent for background runs.

**Architecture:** Treat one `profile_delegate` call as one bounded attempt chain under one total deadline and one concurrency slot. Attempt 1 uses the requested new/resumed session; only a terminal failure matching a strict transport allowlist may trigger a 10-second-delayed resume of the same child session. Persist every attempt separately, expose compact recovery history, and publish exactly one final event through a plugin-owned durable SQLite outbox reconciled by a plugin-owned gateway hook/daemon. Do not infer hangs from silence, inject into a live `chat -q` process, rerun the original task in a fresh session, or modify `/opt/hermes`.

**Tech stack:** Python 3.10+, Hermes plugin API/hooks, `hermes chat -q --resume`, bounded subprocess capture, plugin-owned JSON/SQLite artifacts, pytest, Ruff.

---

## 1. Product decisions

These decisions were made with Alberto on 2026-07-18:

1. **Recovery method:** resume the same delegated Hermes session automatically.
2. **Maximum recovery:** two automatic resumes after the initial attempt; three child process attempts maximum.
3. **Configuration:** default two resumes; one global plugin setting may reduce this to `0`, `1`, or `2`. No per-call override in V1.
4. **Eligibility:** strict allowlist of recognized transient connection/stream/provider-capacity failures only.
5. **Nudge style:** direct — continue exactly where the child stopped; do not restart the original task.
6. **Delay:** fixed 10 seconds before each resume.
7. **Timeout:** one total `timeout_seconds` budget for the complete delegation, including attempts and delays. A retry receives only the remaining time.
8. **Missing session identity:** if no trustworthy target `session_id` exists, do not rerun from scratch or guess a recent session; fail safely and notify the parent.
9. **Parent notification:** emit only one final notification, after success or terminal failure, containing compact attempt/recovery history.
10. **Delivery guarantee for notifying gateway background runs:** durable at-least-once delivery across gateway/process restart, implemented entirely by the plugin. CLI/TUI receive persisted artifacts/status but no autonomous durable reinjection guarantee in V1.
11. **Not V1:** no silence-based watchdog and no message injection into a still-running child.

## 2. Evidence and root cause

The current plugin performs one child subprocess and converts any non-zero exit into `nonzero_exit`. It already captures a child session footer and supports explicit resume, but it does not turn those primitives into an automatic recovery chain.

Observed failures:

- `pd_20260718_103647_9idrq1` ran for about six minutes, made substantial partial file changes, emitted a valid child session id, then ended with exit `1` and the terminal line `API call failed after 3 retries: Connection error.` Reexecuting from scratch would risk repeating edits or side effects; resuming that session is the safe recovery path.
- `pd_20260629_100004_ffitt6` ended with `HTTP 503: All Codex auth slots are temporarily unavailable after upstream server errors. Try again shortly.` This is provider-capacity/transient evidence, not a task failure.
- `pd_20260717_162324_3w4n73` ended with `-9`. That is compatible with SIGKILL/OOM and must not be disguised as a stream retry.
- `pd_20260718_123817_5pcidp` ended with `130` but no recognized terminal transport marker in the captured output. Exit `130` alone is ambiguous and must not auto-resume.

The current background notification path constructs an `async_delegation` event and places it only in the dispatching process' in-memory queue. A detached worker completing after a gateway restart cannot reach that dead queue. Hermes' core durability internals are read-only and outside this task, so the plugin needs its own durable outbox and a gateway-local reconciler registered through existing plugin extension points.

## 3. Scope

### In scope

- Automatic same-session resume after a recognized terminal transient failure.
- One total timeout/deadline across the attempt chain.
- Separate bounded artifacts for every attempt.
- Compact retry metadata in status/result/tool output.
- One final background completion event after all retry decisions finish.
- Plugin-owned durable outbox, gateway reconciliation, claiming, and acknowledgement without `/opt/hermes` changes.
- Stable error codes and operator-visible classification.
- Synchronous and background execution parity for retry behavior; durable autonomous delivery is gateway-only in V1.

### Out of scope

- Detecting a hang from quiet stdout/stderr.
- Killing a healthy but silent agent.
- Interactive nudges into a live `chat -q` process.
- Retrying arbitrary non-zero exits.
- Starting a fresh session when resume identity is missing or invalid.
- Retrying plugin timeout, user cancellation, policy/approval failures, validation failures, concurrency rejection, parse drift, SIGKILL/OOM, or model-declared `blocked`/`failed` results.
- Exactly-once notification. The contract is at-least-once; a crash after adapter acceptance but before acknowledgement may produce a duplicate.
- Any modification under `/opt/hermes`, use of Hermes' private durable SQLite schema, or direct Discord/Telegram send path.
- Durable autonomous reinjection for plain CLI or TUI/desktop in V1.

## 4. User-visible behavior

### 4.1 Successful recovery

If attempt 1 exits with a recognized transient failure and exposes a session id:

1. Persist attempt 1 metadata and logs.
2. Update `status.json` to `status="recovering"` with the classified reason.
3. Wait 10 seconds, charged to the original timeout budget.
4. Start attempt 2 with `--resume <same-session-id>` and a recovery nudge prompt.
5. If attempt 2 succeeds, finalize normally and send one completion notification saying recovery succeeded after one resume.
6. If attempt 2 has another recognized transient failure, repeat once for attempt 3.

No parent notification is emitted between attempts.

### 4.2 Exhausted recovery

After two resumed attempts fail transiently:

- final status: `failed`;
- final error code: `transient_resume_exhausted`;
- result summary: explicitly say the child session was resumed twice and still failed transiently;
- include the stable child session id and compact attempt history;
- send one durable final error event to the parent agent.

### 4.3 No resumable session

If a transient failure occurs but there is no trustworthy session id:

- do not search recent profile sessions;
- do not rerun the task from the original prompt;
- final error code: `transient_resume_no_session`;
- notify the parent once with the run id, failure class, and artifact paths.

For a caller-requested `session_mode="resume"`, the validated input `session_id` is already authoritative even if the failed process does not print a footer. For `session_mode="new"`, only the child footer parsed by the existing strict final-footer helper is authoritative.

### 4.4 Insufficient remaining budget

A resume requires the fixed 10-second delay plus at least 10 seconds of child runtime. If the total deadline cannot provide both:

- do not launch another process;
- final error code: `transient_resume_budget_exhausted`;
- notify the parent once;
- report the elapsed and remaining budget in metadata.

### 4.5 Synchronous calls

A synchronous call already returns its final result directly to the parent agent. It uses the same recovery chain and attempt artifacts, but it does not enqueue a second completion event. Duplicate “you already have the tool result” notifications are noise wearing a reliability hat.

## 5. Attempt-chain state machine

Task execution and notification delivery are separate state machines:

- `status` / `error_code` describe the delegated task attempt chain.
- `notification_status` / `notification_error_code` describe durable parent delivery.

Valid task lifecycle values become `running | recovering | completed | failed | timed_out | corrupt`. `recovering` is active and nonterminal; `timed_out` is terminal/finished. Update `VALID_RUN_STATUSES`, list-tool schema/filtering, `derive_activity`, status projections, docs, and tests together. A completed task remains `completed` even if parent notification persistence/wakeup fails; only notification fields and detached worker exit metadata reflect that secondary failure.

```text
running attempt
  ├─ exit 0 + usable result ------------------------------> completed
  ├─ plugin timeout --------------------------------------> timed_out (no resume)
  ├─ policy/approval/validation/concurrency failure ------> failed (no resume)
  ├─ non-transient nonzero exit --------------------------> failed (no resume)
  └─ recognized transient terminal failure
       ├─ no session id ----------------------------------> failed:no_session
       ├─ resumes used == configured max -----------------> failed:exhausted
       ├─ total budget insufficient ----------------------> failed:budget_exhausted
       └─ session id + budget + retry available
            -> persist attempt -> recovering -> wait 10s -> resume same session
```

One call acquires the plugin concurrency slot once and holds it across all attempts and 10-second recovery waits. This prevents another delegation from entering the same global slot between partial work and recovery.

## 6. Strict transient classifier

Add one pure helper:

```python
def classify_transient_failure(
    *,
    exit_code: int | None,
    timed_out: bool,
    stdout: str,
    stderr: str,
    parsed_result: dict | None,
) -> str | None:
    ...
```

### 6.1 Preconditions

Return `None` unless all are true:

- the child process ended;
- `exit_code` is non-zero;
- `timed_out` is false;
- no valid terminal success result envelope was produced;
- no higher-priority excluded failure marker is present.

**Classification order is mandatory:** parse the strict final session footer; evaluate timeout, approval/policy, signal/OOM, HTTP/auth/quota/model/context exclusions; parse any valid terminal result; only then evaluate the positive transient allowlist. A positive-looking stream line cannot override a higher-priority exclusion elsewhere in the same diagnostic tail.

Inspect only a bounded terminal diagnostic window: the final 20 nonblank lines / final 4,000 characters of stdout after stripping the final `session_id:` footer, plus the equivalent stderr tail. Do not classify from arbitrary task prose or a large diff containing error-like strings. If either stream was truncated, classification is allowed only when both the complete recognized positive terminal marker and all data required to reject higher-priority exclusions are inside the retained tail; otherwise fail closed as non-transient.

### 6.2 Initial positive allowlist

Implement a versioned immutable tuple/map of specific, case-insensitive **anchored regexes** with stable reason codes. These are the complete V1 patterns; no semantic fallback, fuzzy matching, or “equivalent” wording is permitted:

Evaluate positives in this exact first-match order so overlapping patterns have deterministic reason codes:

1. `incomplete_chunked_read`
2. `connection_reset`
3. `stream_closed_prematurely`
4. `provider_503`
5. `codex_slots_temporarily_unavailable`
6. `server_disconnected`
7. `remote_protocol_error`
8. `connection_error`

Specific signatures intentionally precede generic exception classes. Add overlap fixtures, e.g. `RemoteProtocolError: incomplete chunked read` must classify as `incomplete_chunked_read`, never `remote_protocol_error`.

| Reason code | Accepted terminal evidence |
|---|---|
| `connection_error` | `^API call failed after \d+ retries:\s*Connection error\.?$` |
| `provider_503` | `^API call failed after \d+ retries:\s*HTTP 503(?::|\s).*(?:Service Unavailable|upstream|temporarily unavailable|try again|retry later).*$` |
| `codex_slots_temporarily_unavailable` | `^(?:HTTP 503:\s*)?All Codex auth slots are temporarily unavailable.*(?:upstream|try again|retry later).*$` |
| `remote_protocol_error` | a traceback exception line matching `^(?:[\w.]+\.)?RemoteProtocolError:\s*\S.*$` |
| `server_disconnected` | a traceback exception line matching `^(?:[\w.]+\.)?ServerDisconnectedError:\s*\S.*$` |
| `connection_reset` | a traceback/terminal exception line ending in `Connection reset by peer`, e.g. `^(?:[\w.]+(?:Error|Exception):\s*)?.*Connection reset by peer\.?$` |
| `incomplete_chunked_read` | a traceback exception line matching `^(?:[\w.]+\.)?RemoteProtocolError:\s*(?:peer closed connection without sending complete message body|incomplete chunked read).*$` |
| `stream_closed_prematurely` | known Hermes/provider terminal prefix plus exact phrase: `^(?:API call failed after \d+ retries:|(?:[\w.]+\.)?(?:ReadError|WriteError|NetworkError):)\s*.*(?:stream closed prematurely|stream ended unexpectedly)\.?$` |

Generic substrings such as `error`, `connection`, `stream`, `503`, or `temporarily unavailable` are not sufficient by themselves.

The classifier consumes dedicated rolling diagnostic tails maintained while reading the pipes. Current `append_capped` preserves only the beginning of stdout/stderr, so normal compatibility logs can lose the final provider error after truncation. Add independent in-memory-or-private-file ring tails capped at 4,000 characters / 20 nonblank lines per stream and return them in `run_meta` for classification; do not increase the existing full-log caps. Never classify by calling `tail_text` on a prefix-capped file.

### 6.3 Explicit exclusions

Never auto-resume:

- `timed_out=true` or plugin error code `timeout`;
- approval timeout/denial or policy/bootstrap failure;
- validation, allowlist, workdir, reasoning-scope, background-start, or concurrency errors;
- HTTP `400`, `401`, `403`, `404`, invalid model/provider, context-length, malformed request, billing/quota exhaustion, or credential revocation;
- exit `-9`, `137`, OOM/SIGKILL evidence;
- exit `130` without a recognized positive transport marker;
- a clean exit with invalid/unstructured output;
- a valid child result whose status is `blocked` or `failed`;
- result parsing fallback or session rename failure.

A signal number is supporting metadata, never the sole positive classifier.

## 7. Recovery prompt and command

### 7.1 Recovery prompt

Create a separate private prompt artifact per resume. Do not overwrite the original `prompt.txt`.

Attempt 2 prompt:

```text
The previous delegated run ended because of a transient connection or stream failure.
Continue exactly where you left off in this same session. Do not restart the original task or repeat work/actions already completed.
Finish the original task and return the requested final JSON result.
```

Attempt 3 adds:

```text
This is the final automatic recovery attempt.
```

Do not paste the original task, full prior stdout, diff, or caller context into the nudge. The resumed Hermes session is the continuity source.

### 7.2 Command invariants

Every resume must preserve:

- target profile;
- workdir;
- child approval mode;
- capability preset and blocked tool schemas;
- model/provider/reasoning/max-turns/toolsets/skills overrides;
- quiet mode, source, and session-id footer behavior;
- target profile `HERMES_HOME` and temporary managed reasoning scope.

The only intentional changes are:

- prompt path points to the recovery prompt;
- `--resume` points to the stable target child session id;
- per-attempt timeout receives the remaining total budget.

Refactor command construction to accept explicit `prompt_path` and `resume_session_id` rather than mutating the persisted request object in place.

## 8. Timeout and delay contract

At the start of `_execute_delegate_run`:

```python
deadline = time.monotonic() + request["timeout_seconds"]
```

For every attempt:

```python
remaining = deadline - time.monotonic()
```

Rules:

- Attempt 1 may consume up to the current remaining budget.
- The deadline covers every blocking operation inside `_execute_delegate_run`: child attempts, 10-second waits, process termination/reaping, and best-effort session rename.
- A 10-second resume delay is interruptible only by process shutdown and counts against the same deadline.
- If shutdown/cancellation interrupts the delay, finalize as `status="failed"`, `error_code="transient_resume_interrupted"`, without launching another attempt; never fall through into a fresh run.
- After the delay, recompute remaining time; never reuse a stale value.
- Require at least 10 seconds after the delay before launching a resume.
- Pass only the remaining whole seconds to `run_capped_subprocess`, rounded down and clamped to at least `1` after the 10-second minimum-runtime gate.
- Timeout cleanup must use the same deadline. Send the existing kill immediately, reap only within remaining budget, and record `termination_overrun_seconds` if OS/process cleanup unavoidably completes after the deadline; do not start any later blocking operation.
- If `run_capped_subprocess` itself reaches its timeout, stop; do not classify that timeout as transient.
- Session rename uses `min(30, floor(remaining))`; if less than one second remains, skip rename with `session_renamed=false` and `rename_skipped="deadline_exhausted"` without changing task success.
- Record total elapsed time and per-attempt duration with monotonic timing; persist wall-clock ISO timestamps separately.

## 9. Artifact contract

Keep existing top-level paths for compatibility and add per-attempt artifacts:

```text
<run_dir>/
  request.json
  prompt.txt                       # immutable original prompt
  status.json
  result.json
  stdout.txt                       # final attempt stdout compatibility copy
  stderr.txt                       # final attempt stderr compatibility copy
  approval_events.jsonl
  attempts/
    01/
      prompt.txt                   # byte-for-byte private copy of original prompt
      stdout.txt
      stderr.txt
      meta.json
    02/
      prompt.txt                   # recovery nudge
      stdout.txt
      stderr.txt
      meta.json
    03/
      prompt.txt
      stdout.txt
      stderr.txt
      meta.json
  notification_event.json          # final bounded event for audit/requeue
```

Use private permissions (`0700` directories, `0600` files) with existing best-effort chmod behavior.

### 9.1 Attempt metadata

Each `meta.json` contains only bounded operational data:

```json
{
  "attempt": 1,
  "kind": "initial",
  "session_mode": "new",
  "session_id_in": "",
  "session_id_out": "20260718_...",
  "started_at": "...",
  "ended_at": "...",
  "duration_seconds": 382.1,
  "timeout_budget_seconds": 1200,
  "remaining_budget_seconds": 817.9,
  "exit_code": 1,
  "timed_out": false,
  "stdout_truncated": false,
  "stderr_truncated": false,
  "classification": "transient",
  "reason": "connection_error",
  "decision": "resume"
}
```

Do not copy raw stdout/stderr into JSON metadata.

### 9.2 Status/result recovery summary

Add a compact object to `status.json`, final tool output, and `result.json`:

```json
{
  "recovery": {
    "configured_max_resumes": 2,
    "resume_delay_seconds": 10,
    "attempt_count": 2,
    "resume_attempts_used": 1,
    "recovered": true,
    "exhausted": false,
    "transient_failures": [
      {"attempt": 1, "reason": "connection_error", "exit_code": 1}
    ]
  }
}
```

Cap `transient_failures` at three entries by construction. `profile_delegate_status` may return this compact history and attempt artifact paths, but not all attempt log bodies unless explicitly requested through existing bounded tails.

## 10. Final result rules

- Parse and normalize only the final accepted attempt as the task result.
- Copy the final attempt's stdout/stderr to top-level compatibility files atomically.
- Preserve all earlier attempt files.
- A recovered success remains `success=true`, `status="completed"`, with `recovery.recovered=true`.
- If the final attempt is non-transient, keep its most specific existing error code and attach recovery history; do not relabel every post-retry failure as exhaustion.
- Use `transient_resume_exhausted` only when every allowed resume was consumed by recognized transient failures.
- Rename a newly created child session only after final success, preserving current behavior.
- Never treat rename failure as task failure.

## 11. Durable final notification

### 11.1 Chosen plugin-only design

All writable implementation stays under `/opt/data/plugins/profile-delegate`. `/opt/hermes` is read-only reference material.

Use a plugin-owned SQLite outbox, for example `<runs_root>/notifications.sqlite3`, with one row per `task_id` and these bounded fields:

- producer identity and run path;
- normalized gateway routing (`session_key`, platform, chat/thread identifiers when available);
- state `running | pending | claimed | delivered | unknown`;
- bounded final event JSON;
- owner PID/process-start identity;
- claim token/time, attempt count, timestamps, and last bounded error.

SQLite uses WAL, `busy_timeout`, transactions, and a schema version owned by this plugin. The detached worker registers before child execution and transactionally moves the same row to `pending` after final artifacts are durable. Never touch Hermes' private `async_delegations` table.

### 11.2 Gateway ownership and reconciler

Register `pre_gateway_dispatch` in `register(ctx)`. On the first real gateway event, the hook receives the live `gateway` object and starts exactly one daemon reconciler for that gateway process/plugin instance. The hook itself returns `None` immediately; it never delays or rewrites user traffic.

The reconciler polls the plugin outbox every two seconds and handles only rows whose normalized route belongs to this caller-profile gateway. For each pending row it:

1. atomically claims with a random token and lease timestamp;
2. reconstructs a bounded synthetic event with `type="profile_delegate_completion"`, explicit `session_key`, `platform`, `chat_type`, `chat_id`, optional `thread_id`, `parent_session_id`, and final result metadata;
3. formats the private `[IMPORTANT: ...]` payload inside the plugin and calls the live gateway's existing `_inject_watch_notification(synth_text, evt)` coroutine from the gateway asyncio loop via `asyncio.run_coroutine_threadsafe` (or an equivalent thread-safe schedule on that loop captured from the hook);
4. marks `delivered` only when the future returns `True`;
5. releases/lets the lease expire on `False`, exception, cancellation, or timeout.

Do not label plugin-owned events `async_delegation`, call `_deliver_completion_notification`, or insert them into Hermes' core completion queue: that route invokes Hermes' private async-delegation claim ledger, which has no matching row and will reject delivery. The plugin owns producer identity, deduplication, claim, and acknowledgement; it reuses only `_inject_watch_notification`, whose source resolution prefers the persisted session-store origin and then validates explicit route metadata before adapter injection. This is local gateway integration, not a direct Discord/Telegram send path.

If the gateway restarts while the worker remains alive, the first subsequent real inbound event starts the new reconciler; when the worker later persists `pending`, polling delivers it without another restart. To cover a gateway that restarts and receives no inbound event at all, `register(ctx)` may also start a bounded bootstrap watcher that discovers a live `GatewayRunner` only through documented/importable process-local objects; if no such object is available, the guarantee begins once `pre_gateway_dispatch` provides the gateway. Document this boundary honestly rather than inventing a core hook that does not exist.

V1 supports durable autonomous delivery only for calls whose captured origin proves a gateway messaging route: nonempty `session_key`, explicit platform/chat type/chat ID, and optional thread ID captured from the live event/session origin. Do not trust session-key parsing alone for DM or ambiguous group suffixes. If `background=true`, `notify_on_complete=true`, and origin is CLI/TUI/stateless/empty/unparseable, fail before child work with `durable_notification_unroutable`; callers may choose `notify_on_complete=false` and poll status.

### 11.3 Race-free dispatch registration handshake

Use a single-writer/barrier protocol; atomic JSON replacement alone does not prevent lost updates.

1. Parent validates the gateway route, creates private artifacts, opens an inherited one-shot readiness pipe/socketpair, and starts the detached worker behind a closed execution gate.
2. Parent writes PID/background fields before releasing the worker; afterward it does not stale-read/overwrite worker-owned lifecycle fields.
3. Worker transactionally inserts/read-backs its outbox row as `running`, matching `task_id`, route, run path, and owner identity.
4. Worker writes immutable `notification_registered.json` and signals readiness through the pipe.
5. Parent waits at most five seconds while checking worker death. Timeout/EOF/mismatch terminates the worker before child launch and returns `durable_notification_registration_failed`, never a false async handle.
6. Only successful registration opens the child execution gate.

For thread mode, register/read back synchronously before starting the worker thread. Tests pause each side around writes/signals and prove no lost update or pre-registration child launch.

### 11.4 Completion and abandoned-worker recovery

After the attempt chain terminates:

1. Atomically write final task `result.json` and `status.json`.
2. Write one bounded `notification_event.json` containing route, final result/recovery history, and artifact paths—never prompt/log bodies or credentials.
3. In one SQLite transaction update the registered row to `pending` with that exact event; require affected-row/readback verification.
4. Only then set `notification_status="durable_pending"` and exit.

The gateway reconciler periodically checks `running` owners. A missing PID or changed process-start identity becomes one `unknown` pending event pointing to `run_dir`; it never fabricates task success/failure. Stale delivery claims become retryable after a fixed lease. Crash after gateway acceptance but before plugin acknowledgement may duplicate, which is the selected at-least-once contract.

### 11.5 Delivery semantics and lifecycle

- **One producer:** `task_id`; retry attempts never emit events.
- **Delivered boundary:** the reused gateway delivery method returns `True`; this means adapter acceptance, not completion of the parent LLM turn or outward platform send.
- **Separate states:** task `status/error_code` and notification `notification_status/notification_error_code` never overwrite each other.
- **No silent downgrade:** a notifying background gateway run cannot start without durable registration/readback.
- **Status projection:** status/list read the plugin outbox and expose delivery attempts/state without mutation.
- **Prune protection:** protect `running`, `pending`, and active claims; destructive prune fails closed if outbox state cannot be read.
- **Bounded retention:** delivered rows may age out under documented retention. Pending rows are never silently capacity-evicted; if a hard safety cap is reached, reject new notifying background dispatches with observability instead of deleting undelivered events.

If task execution succeeds but outbox completion persistence fails, preserve the completed task/result; record only `notification_error_code="durable_notification_persistence_failed"` and exit the worker nonzero. Never enqueue or deliver an event not proven durable by readback.

### 11.6 `notify_on_complete=false`

Do not register a durable row, persist a completion event, or queue a notification. Status remains `notification_status="disabled"`. Recovery still occurs and remains visible through run artifacts/status polling.

## 12. Configuration and schema

Add one strict global setting:

```text
PROFILE_DELEGATE_MAX_TRANSIENT_RESUMES=2
```

Contract:

- missing: default `2`;
- accepted: integer `0`, `1`, or `2`;
- malformed/out of range: fail dispatch with `configuration_error`; do not silently substitute a different retry count;
- read and persist the effective value at dispatch so detached workers remain deterministic after environment changes;
- no per-call tool field in V1.

The delay is a fixed product decision in V1:

```text
TRANSIENT_RESUME_DELAY_SECONDS = 10
```

Do not add a second setting until a measured need exists.

No existing input becomes required. Update tool description to disclose automatic same-session recovery and one total timeout budget. Bump plugin minor version from `1.4.0` to `1.5.0` after implementation.

## 13. Stable error codes

Add:

- `transient_resume_no_session`
- `transient_resume_budget_exhausted`
- `transient_resume_exhausted`
- `transient_resume_interrupted`
- `resume_session_mismatch`
- `durable_notification_unavailable`
- `durable_notification_unroutable`
- `durable_notification_registration_failed`
- `durable_notification_persistence_failed`
- `configuration_error` for invalid retry configuration

Retain existing specific errors for non-transient outcomes (`timeout`, `approval_timeout`, `nonzero_exit`, policy/validation errors, etc.). Task execution errors live in top-level `error_code`; notification-only failures live in `notification_error_code` and must not overwrite a completed task's status/result.

## 14. Safety and side effects

- Same-session resume is mandatory because the child session contains its reasoning and tool history. A fresh rerun would lose idempotency context.
- The nudge explicitly says not to repeat completed work/actions, but profiles are not transaction boundaries. External, paid, destructive, or binding operations still require their existing approval/policy controls.
- Do not infer a session from “most recent profile session”; concurrent delegates make that unsafe.
- Do not retry exit `130` alone; it may be user cancellation.
- Do not retry `-9`/`137`; inspect memory/process death separately.
- Hold one concurrency slot through recovery to prevent overlapping writers.
- Keep output caps per attempt. With at most three attempts, disk growth remains bounded by three times the configured per-stream caps; document this explicitly.
- Notification payloads must use bounded summaries and paths, never raw logs or task context.

## 15. Implementation plan (TDD)

### Task 1 — Lock classifier behavior

**Files**
- Modify: `test_profile_delegate.py`
- Later modify: `core.py`

**Steps**
1. Add parameterized positive fixtures for every exact reason-code regex in section 6.2, assert the V1 pattern map is finite/versioned, and lock the exact first-match precedence with overlapping fixtures.
2. Add negative fixtures for timeout, 400/401/403, quota/billing, approval, validation, concurrency, `-9`, `137`, bare `130`, generic prose mentioning streams, and valid JSON output.
3. Prove only the bounded rolling terminal tail is inspected, including a terminal provider error emitted after the normal compatibility log cap and a near-match just outside the final 20 lines.
4. Prove a final session footer is stripped before matching.
5. Prove combined positive+excluded evidence fails closed to the exclusion.
6. Run classifier tests RED.
7. Implement the smallest pure classifier and rolling-tail capture, then run GREEN.

### Task 2 — Add attempt artifact helpers

**Files**
- Modify: `test_profile_delegate.py`
- Modify: `core.py`

**Steps**
1. Add failing tests for `attempts/01..03`, private permissions, bounded logs, and `meta.json` shape.
2. Refactor subprocess paths so each invocation writes to its own attempt directory.
3. Keep original `prompt.txt` immutable.
4. Copy only the final attempt logs to top-level compatibility paths atomically.
5. Verify earlier attempt logs remain unchanged.

### Task 3 — Implement one-deadline same-session recovery

**Files**
- Modify: `test_profile_delegate.py`
- Modify: `core.py`

**Steps**
1. Use a sequenced fake subprocess: transient failure with footer, then success.
2. Assert commands are initial `new`, then `--resume` with exactly the captured id.
3. Assert the recovery prompt does not repeat the original task/context.
4. Assert same overrides/policy/workdir on every command.
5. Assert one concurrency acquisition spans all attempts.
6. Mock monotonic time and sleep; prove the fixed delay and decreasing budget.
7. Add success-after-first-resume, success-after-second-resume, exhausted, no-session, already-resumed-input, insufficient-budget, and non-transient-second-attempt tests.
8. Add a footer-mismatch test: after the stable session id is established, a later footer may confirm it but must never replace it; mismatch is a non-recoverable `resume_session_mismatch` integrity failure.
9. Add shutdown/cancellation-during-delay tests asserting `failed/transient_resume_interrupted`, plus deadline-boundary tests proving no subsequent child launch.
10. Implement loop around one extracted `execute_attempt(...)` helper.
11. Keep session rename after final success only and under the same remaining deadline.

### Task 4 — Surface compact recovery state

**Files**
- Modify: `test_profile_delegate.py`
- Modify: `core.py`
- Modify: `__init__.py`

**Steps**
1. Add failing assertions for recovery metadata in request/status/final result/status tool.
2. Persist the effective global retry count at dispatch.
3. Add strict config validation.
4. Ensure background detached workers rely only on persisted request data.
5. Update tool description; add no per-call field.

### Task 5 — Build plugin-owned durable outbox

**Files**
- Create: `notification_outbox.py`
- Modify: `test_profile_delegate.py`
- Modify: `core.py`

**Steps**
1. Add failing tests for the plugin SQLite schema, WAL/busy timeout, register/readback, pending transition, atomic claim, lease expiry, acknowledgement, and abandoned-owner recovery.
2. Add strict route fixtures: Discord/Telegram gateway accepted; CLI/TUI/stateless/empty/foreign rejected when notifying.
3. Assert one row per `task_id`, bounded event/error fields, and no prompt/log/task-body persistence.
4. Assert delivered retention is bounded, pending rows are never evicted, and a full safety cap rejects new notifying dispatches.
5. Implement the minimal standalone outbox; do not import or mutate Hermes private persistence helpers/schema.
6. Prove `notify_on_complete=false` bypasses outbox registration and remains pollable.

### Task 6 — Add detached-worker registration handshake

**Files**
- Modify: `test_profile_delegate.py`
- Modify: `core.py`

**Steps**
1. Add a fake detached worker gated by an inherited pipe/socketpair.
2. Deterministically pause parent and worker around PID/status write, durable registration, marker write, and readiness signal.
3. Assert parent returns async success only after readback+signal and child Hermes cannot launch first.
4. Assert the immutable marker is created only after durable readback succeeds; `status.json` is not the handshake primitive.
5. Simulate timeout, EOF, worker death, and mismatched registration; assert worker termination, no child launch, and no false async handle.
6. Preserve PID/liveness inspection without concurrent stale-object writes.

### Task 7 — Persist exactly one final event

**Files**
- Modify: `test_profile_delegate.py`
- Modify: `core.py`
- Modify: `notification_outbox.py`

**Steps**
1. Simulate two transient failures followed by success; assert zero interim events and one persisted final event.
2. Simulate final failure; assert one durable error event with attempt history.
3. Assert event is persisted after result/status files and before worker exit.
4. Assert only a completion with successful plugin-outbox readback may become deliverable.
5. Assert bounded payload, routing identity, and one producer row.
6. Project task and notification lifecycles separately in status/list, including `recovering` active and `timed_out` finished.
7. Preserve successful task result when notification persistence fails; record only `notification_error_code` and nonzero worker metadata.
8. Protect running/finalizing/pending runs in prune and fail closed on durable-state read errors.

### Task 8 — Register and prove the plugin gateway reconciler

**Files**
- Modify: `__init__.py`
- Create: `gateway_reconciler.py`
- Modify: `notification_outbox.py`
- Modify: `test_profile_delegate.py`
- Modify: `plugin.yaml`

**Steps**
1. Register `pre_gateway_dispatch` and advertise it in `plugin.yaml`; hook captures the live gateway/loop and starts one daemon reconciler without delaying inbound traffic.
2. Claim pending plugin rows and schedule the existing gateway completion-delivery coroutine thread-safely; never write `/opt/hermes` or core's completion queue/DB.
3. Prove completion after gateway restart plus a subsequent inbound hook reaches the original lane without another restart.
4. Prove worker death after restart becomes one `unknown` event containing `run_dir`.
5. Prove failed/timeout delivery releases or expires the claim, stale claims retry, successful `True` acknowledgement marks delivered, and acceptance/ack crash may replay.
6. Prove multiple hook calls start only one reconciler and polling stays bounded/idle.
7. Verify CLI/TUI notifying dispatch fails before child work; `notify_on_complete=false` remains supported.
8. Assert no files under `/opt/hermes` change.

### Task 9 — Documentation and release metadata

**Files**
- Modify: `README.md`
- Modify: `plugin.yaml`
- Modify: this spec only if implementation discoveries require a correction

**Steps**
1. Document classifier allowlist/exclusions, same-session requirement, total budget, fixed delay, max-resume config, artifact growth, and notification semantics.
2. State clearly that silence is not a hang signal and no live nudge exists in V1.
3. State at-least-once, not exactly-once.
4. Document gateway-only durable delivery, first-inbound-after-restart activation boundary, plugin-owned retention, and read-only `/opt/hermes` constraint.
5. Bump both README and manifest to `1.5.0`.

## 16. Verification matrix

Run from `/opt/data/plugins/profile-delegate`:

```bash
.venv/bin/python -m pytest test_profile_delegate.py -q
.venv/bin/ruff check __init__.py core.py notification_outbox.py gateway_reconciler.py child_bootstrap.py test_profile_delegate.py
.venv/bin/python -m py_compile __init__.py core.py notification_outbox.py gateway_reconciler.py child_bootstrap.py
.venv/bin/python cli_smoke.py --help
# Verify `git diff -- /opt/hermes` is empty; /opt/hermes is read-only scope.
```

Add an integration-shaped fake-Hermes executable that:

1. attempt 1 writes a session footer and a recognized connection error, then exits `1`;
2. attempt 2 verifies `--resume <same-id>`, writes valid JSON, and exits `0`;
3. records argv and elapsed budget without network access.

Then verify:

- one task id and one child session id;
- two attempts, one 10-second delay (mocked in unit tests; shortened only in the integration fixture through dependency injection, not production config);
- final success and `recovery.recovered=true`;
- exactly one final durable plugin-outbox completion;
- detached completion reaches a live idle gateway once the plugin reconciler has captured that gateway;
- gateway restart followed by the documented hook activation restores delivery and acknowledgement behavior;
- durable state exists only in the plugin-owned outbox under the captured caller profile's runs root;
- no changes to target profile persistent config or any file under `/opt/hermes`;
- no prompt/log contents in the notification payload;
- no unrelated repository files changed.

Finally run one harmless real delegated profile smoke with a successful call to confirm normal behavior is unchanged. Do not manufacture a live provider outage as a release test.

## 17. Acceptance criteria

The feature is accepted only when all are true:

1. A recognized connection/stream failure with a child session id resumes that exact session and can recover successfully.
2. No execution path creates a fresh session as retry fallback.
3. At most two resumes occur, defaulting to two and globally configurable to `0..2`.
4. Only the strict allowlist triggers recovery; all exclusions are regression-tested.
5. Delay is exactly 10 seconds and charged to one total deadline.
6. Timeout, approval/policy, bare `130`, `-9`/`137`, validation, concurrency, parse drift, and model-declared failures never auto-resume.
7. Every attempt has separate bounded artifacts; top-level compatibility paths show the final attempt.
8. Recovery metadata is visible in status/result without dumping logs.
9. Background attempt chains emit no intermediate retry notification and exactly one final producer event.
10. The plugin outbox survives gateway/plugin-process restart and delivers a notifying gateway run at least once after the reconciler has captured the restarted gateway.
11. A reconciler already attached to a live idle gateway polls and delivers detached completions without another user turn.
12. Durable rows, claims, and acknowledgements exist only in the caller profile's plugin-owned outbox; target profile storage and Hermes core DB are untouched.
13. Unroutable gateway origins or failed durable registration handshakes fail before child work; no best-effort downgrade or false async handle.
14. CLI/TUI notifying background dispatch is rejected in V1; `notify_on_complete=false` remains available with status polling.
15. Synchronous calls return the final result inline and do not create a duplicate completion.
16. Running, pending, and actively claimed notifications protect run artifacts; destructive prune fails closed if outbox state cannot be checked.
17. Gateway restart while the worker remains alive, followed by documented hook activation, delivers a later completion without a second restart; worker death becomes one `unknown` event.
18. Durable registration/publication require affected-row and readback verification; missing or mismatched rows cannot look successful.
19. Delivered retention is bounded; pending capacity pressure rejects new notifying dispatches instead of evicting undelivered events.
20. Focused plugin tests, Ruff, compile, CLI smoke, one harmless real gateway-profile smoke, and a proof that `/opt/hermes` is unchanged all pass.

## 18. Plugin-only boundary and residual risks

`/opt/hermes` is strictly read-only. The implementation may import and call existing public/process-local plugin and gateway surfaces, but every new module, schema, test, hook, thread, and write stays in `/opt/data/plugins/profile-delegate` or its caller-profile runtime data root.

Residual limits are explicit:

- after gateway restart, the reconciler can only attach when an existing plugin hook exposes the new live gateway object; with current extension points that is normally the first real inbound gateway event;
- V1 does not promise autonomous durable delivery for CLI/TUI;
- at-least-once may duplicate after gateway acceptance and before plugin acknowledgement;
- “delivered” ends at gateway adapter acceptance, not parent LLM completion or outward platform confirmation;
- delivered retention is finite, while pending rows are preserved and backpressure new notifying work.

If the first-inbound-after-restart activation boundary is unacceptable, the honest answer is that the stronger zero-inbound restart guarantee is impossible within plugin-only/read-only-core scope. Do not smuggle a Hermes-core patch back into the plan wearing a fake moustache.
