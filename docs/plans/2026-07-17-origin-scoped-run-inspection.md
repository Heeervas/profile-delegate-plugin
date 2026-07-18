# Profile Delegate Origin-Scoped Run Inspection Plan

> **For Hermes:** Implement with strict TDD. This file is the recovery source after context compaction.

**Goal:** Make `profile_delegate_list` and `profile_delegate_status` distinguish runs created by concurrent caller sessions and expose whether a reported `running` run still has a live worker, without replacing the existing artifact store or adding a database.

**Architecture:** Keep each run directory and its `request.json` / `status.json` as the source of truth. At dispatch, persist a small normalized `origin` identity captured from Hermes' concurrency-safe session context; retain the existing flat `origin_session_key` for backward compatibility. Inspection tools project this metadata, default list calls to the current caller session, permit explicit lane-wide or global inspection, and derive advisory worker liveness without mutating canonical status. Old runs remain readable through a compatibility adapter; no migration is required.

**Tech Stack:** Python 3.10+, Hermes plugin API, `gateway.session_context.get_session_env`, JSON artifacts, `os.kill(pid, 0)` for advisory Unix liveness, pytest, Ruff.

---

## 1. Problem statement and verified current state

The global run store is:

```text
$HERMES_HOME/profile_delegate/runs/<task_id>/
```

Current behavior:

- `profile_delegate_list(limit)` reads every caller's recent run directories and returns a global slice.
- `profile_delegate_status(task_id)` resolves globally by `task_id`.
- Dispatch already captures `origin_session_key` and persists it in `request.json` and `status.json`.
- Hermes also exposes concurrency-safe origin values through `gateway.session_context.get_session_env(...)`, including durable session id, routing key, UI session id, platform, source, and profile.
- Detached background mode already persists `worker_pid`; list/status simply omit it.
- `session_title` already labels the delegated task but list/status omit it.

Therefore the fix is mostly projection and filtering, not a new process manager. Replacing the artifact store would be architectural cosplay with an invoice attached.

## 2. Design comparison

### Option A — Presentation-only: expose existing fields

Add `session_title`, `origin_session_key`, and `worker_pid` to list/status.

**Pros**
- Smallest patch.
- No artifact changes.
- Immediately makes manual inspection less blind.

**Cons**
- Default list remains globally mixed.
- `worker_pid` alone does not distinguish alive, dead, or unsupported.
- Existing `origin_session_key` identifies a routing lane, not always one durable Hermes session.
- Every caller/model must implement matching logic itself.

**Verdict:** useful compatibility layer, insufficient fix.

### Option B — Separate run roots per caller session

Store runs under `runs/<origin>/<task_id>`.

**Pros**
- Physical isolation makes current-session listing trivial.
- Directory scans naturally stay scoped.

**Cons**
- Breaks task-id resolution, pruning, existing paths, docs, and external references.
- Requires path-safe encoding/hashing and migration or dual-root discovery.
- Global inspection becomes more complex.
- Session identity rotation can strand related runs.

**Verdict:** reject. It solves a query problem by mutating storage topology.

### Option C — Add a SQLite registry/index

Create a runs table containing origin, state, PID, timestamps, and artifact paths.

**Pros**
- Strong filtering and pagination at high volume.
- Could support leases, indexes, and richer process lifecycle later.

**Cons**
- Creates dual-write consistency between SQLite and run artifacts.
- Requires schema migrations, locking, recovery, and corruption semantics.
- The plugin already prunes bounded local artifacts and does not need database-scale throughput.

**Verdict:** reject for now. Reconsider only with measured evidence such as tens of thousands of retained runs or query latency that artifact scans cannot meet.

### Option D — Add normalized origin metadata plus scoped projections

Persist a compact `origin` object, preserve legacy fields, default list to the current session, expose explicit `current_lane` and `all` scopes, and derive liveness from existing worker metadata.

**Pros**
- Fixes the user-visible ambiguity at the query boundary.
- Additive and backward-compatible.
- No migration, database, daemon, or new dependency.
- Supports Discord threads, CLI sessions, API/UI tabs, and future adapters through one identity model.
- Keeps `task_id` globally stable.

**Cons**
- Liveness remains advisory; PID existence cannot prove semantic ownership forever.
- Legacy runs may have only a routing key or no origin metadata.
- Artifact scans remain O(number of retained runs).

**Verdict:** implement. It is the smallest design that actually closes the bug.

## 3. Canonical contracts

### 3.1 Persisted origin object

At dispatch, capture only routing/ownership fields needed for inspection:

```json
{
  "origin": {
    "platform": "discord",
    "source": "discord",
    "profile": "default",
    "session_id": "20260717_...",
    "ui_session_id": "",
    "session_key": "discord:guild:channel:thread"
  }
}
```

Rules:

- Read values with `gateway.session_context.get_session_env`, not process-global `os.environ`, because gateway sessions run concurrently.
- Do not persist user id, username, message content, chat name, or task context in `origin`; they are unnecessary for ownership and increase privacy exposure.
- Keep top-level `origin_session_key` for old consumers and notification code.
- Add `artifact_schema_version: 2` to new request/status artifacts.
- Treat the object as immutable provenance. Lifecycle updates must not rewrite it.

### 3.2 Identity matching

For `scope="current_session"`, select the strongest caller identifier available in this order:

1. `ui_session_id` when present — distinguishes concurrent desktop/TUI windows.
2. durable `session_id` — distinguishes `/new`, resumed sessions, and separate conversations.
3. `session_key` — compatibility fallback for gateway lanes and older runs.

A run matches when its corresponding strongest available persisted value equals the caller value. Do not silently fall back from a present but nonmatching strong identifier to a weaker lane key; that would merge sessions again.

For `scope="current_lane"`, compare `session_key` only. This intentionally groups runs from the same Discord thread/channel lane across durable session rotations.

For `scope="all"`, do not filter by origin.

If `current_session` or `current_lane` has no usable caller identity, return an empty result with:

```json
{
  "scope_effective": "unresolved",
  "warning": "current caller origin is unavailable; pass scope='all' explicitly for global inspection"
}
```

Never silently widen to global scope.

### 3.3 List input

```json
{
  "limit": 20,
  "scope": "current_session",
  "status": ["running"],
  "profile": "builder"
}
```

Contract:

- `scope`: `current_session | current_lane | all`; default `current_session`.
- `status`: optional array of `running | completed | failed | corrupt`; omitted means all.
- `profile`: optional exact canonical target profile.
- `limit`: still 1–100 and applies **after** scope/status/profile filtering.

Do not add offset/cursor pagination in this patch. Existing retention plus a 100-result cap is adequate; pagination without measured need is debt in a fake moustache.

### 3.4 List output

Top level:

```json
{
  "success": true,
  "scope_requested": "current_session",
  "scope_effective": "current_session",
  "origin_match_by": "session_id",
  "count": 1,
  "runs": []
}
```

Each run summary:

```json
{
  "task_id": "pd_...",
  "profile": "builder",
  "session_title": "fix profile delegate listing",
  "status": "running",
  "activity": "active",
  "worker_alive": true,
  "error_code": null,
  "created_at": "...",
  "ended_at": null,
  "origin": {
    "platform": "discord",
    "source": "discord",
    "profile": "default",
    "session_id": "20260717_...",
    "ui_session_id": "",
    "session_key": "discord:guild:channel:thread"
  },
  "run_dir": "..."
}
```

### 3.5 Status input/output

Keep status lookup by globally unique `task_id`; do not turn provenance into authorization.

Add optional input:

```json
{
  "task_id": "pd_...",
  "tail_chars": 4000
}
```

No new required fields.

Add output fields:

- `session_title`
- `origin`
- `belongs_to_current_session`: `true | false | null`
- `origin_match_by`: `ui_session_id | session_id | session_key | null`
- `background_worker_mode`
- `worker_pid`
- `worker_alive`: `true | false | null`
- `activity`: `active | stale | finished | unknown`
- `notification_status`

`belongs_to_current_session=null` means either caller or run identity is unavailable. A mismatched run remains readable, but the output makes the mismatch impossible to miss.

### 3.6 Derived liveness

Use one pure helper and do not modify `status.json` during reads.

Rules:

- Terminal status (`completed` or `failed`) → `activity="finished"`, regardless of PID reuse.
- `running` + detached worker PID alive → `activity="active"`, `worker_alive=true`.
- `running` + detached worker PID dead → `activity="stale"`, `worker_alive=false`.
- `running` without a checkable PID (legacy or thread mode) → `activity="unknown"`, `worker_alive=null`.
- `os.kill(pid, 0)` success or `PermissionError` means alive; `ProcessLookupError` means dead; malformed/nonpositive PID means unknown.

Do not auto-rewrite a stale run to `failed` in list/status. Read-time reconciliation should not become an invisible state mutation. A later explicit repair command may do that if real operational demand appears.

## 4. Implementation tasks

### Task 1: Lock origin capture and compatibility with failing tests

**Files:**
- Modify: `test_profile_delegate.py`
- Later modify: `__init__.py`, `core.py`

**Steps:**
1. Add tests for a pure `_current_origin()` wrapper reading mocked `get_session_env` values.
2. Prove `_handler()` passes the normalized origin into `delegate_profile()`.
3. Prove explicit tool arguments still win over Hermes internal kwargs, especially target `session_id` versus caller session metadata.
4. Add a test that new `request.json` and `status.json` contain `artifact_schema_version: 2`, normalized `origin`, and legacy `origin_session_key`.
5. Add a legacy fixture containing only `origin_session_key`.
6. Run targeted tests and verify RED.

### Task 2: Implement minimal origin capture and persistence

**Files:**
- Modify: `__init__.py`
- Modify: `core.py`
- Test: `test_profile_delegate.py`

**Steps:**
1. Add `_current_origin()` in the thin wrapper; use `get_session_env` with safe env fallback only when gateway context APIs are unavailable.
2. Change `delegate_profile(..., origin_session_key="")` to accept additive `origin: Optional[dict] = None`; keep the legacy parameter temporarily so direct callers/tests do not break.
3. Normalize allowed string fields and cap each value to a small fixed length.
4. Persist one canonical `origin` object and derive top-level `origin_session_key` from it when available.
5. Keep notification delivery reading legacy `origin_session_key` in this patch; do not refactor unrelated completion routing.
6. Run targeted and full tests.

### Task 3: Build one compatibility projector

**Files:**
- Modify: `core.py`
- Test: `test_profile_delegate.py`

**Steps:**
1. Add `normalize_persisted_origin(status_or_request)`:
   - return schema-v2 `origin` when present;
   - otherwise synthesize `{"session_key": legacy_value}` from `origin_session_key`;
   - otherwise return an object with empty values or `None`, consistently.
2. Add `origin_match(run_origin, caller_origin, scope)` returning `(matches, matched_by)`.
3. Test UI-session, durable-session, lane fallback, explicit mismatch, and missing-origin cases.
4. Ensure a present nonmatching strong id does not fall through to a matching weak id.
5. Reuse these helpers from list and status; do not duplicate matching logic.

### Task 4: Add advisory activity projection

**Files:**
- Modify: `core.py`
- Test: `test_profile_delegate.py`

**Steps:**
1. Add failing tests for terminal, alive detached worker, dead detached worker, legacy running, malformed PID, and `PermissionError`.
2. Implement `probe_worker_alive(pid)` and `derive_activity(status)` as pure/read-only helpers.
3. Assert list/status calls leave `status.json` byte-identical.
4. Keep thread-mode and legacy results `unknown`; do not invent certainty.

### Task 5: Scope and enrich `profile_delegate_list`

**Files:**
- Modify: `__init__.py`
- Modify: `core.py`
- Test: `test_profile_delegate.py`

**Steps:**
1. Extend `_list_schema()` with `scope`, `status`, and `profile`.
2. Update `_list_handler()` to capture current origin and pass it separately from model arguments.
3. Extend `profile_delegate_list(...)` to filter while iterating and apply `limit` after matches.
4. Return scope metadata and warnings for unresolved current scope.
5. Add `session_title`, normalized origin, worker/activity fields, and existing fields to every run summary.
6. Test two simultaneous sessions plus one same-lane/different-session run:
   - default sees only exact current session;
   - `current_lane` sees both lane runs;
   - `all` sees every run;
   - status/profile filters compose correctly.
7. Preserve corrupt-run reporting without crashing the entire list.

### Task 6: Enrich `profile_delegate_status`

**Files:**
- Modify: `__init__.py`
- Modify: `core.py`
- Test: `test_profile_delegate.py`

**Steps:**
1. Pass caller origin from `_status_handler()` to the core status function without adding model-visible identity fields.
2. Add provenance, ownership comparison, worker/activity, and notification fields to output.
3. Test same-session, different-session, legacy-run, and unavailable-caller cases.
4. Confirm any valid global `task_id` remains inspectable; this is observability, not ACL enforcement.

### Task 7: Documentation, versioning, and examples

**Files:**
- Modify: `README.md`
- Modify: `plugin.yaml`

**Steps:**
1. Bump minor version consistently (recommended `1.3.0`).
2. Document default current-session scope and explicit `current_lane` / `all` behavior.
3. Document additive output fields and advisory liveness semantics.
4. State that older runs remain readable but may report unknown provenance/activity.
5. Replace the vague list/status examples with exact input/output fragments.
6. Do not claim cross-session access control or guaranteed PID ownership.

### Task 8: Verification and independent review

Run from `/opt/data/plugins/profile-delegate`:

```bash
.venv/bin/python -m pytest test_profile_delegate.py -q
.venv/bin/ruff check __init__.py core.py test_profile_delegate.py cli_smoke.py
.venv/bin/python -m py_compile __init__.py core.py cli_smoke.py
.venv/bin/python cli_smoke.py --help
```

Then run a live smoke after a fresh process loads the plugin:

1. Start two background delegates from two distinct caller sessions with unique `session_title` values.
2. From each caller, call `profile_delegate_list()` with no scope and verify only its own run appears.
3. Call `scope="all"` and verify both appear with distinct origin metadata.
4. Inspect each by task id and verify `belongs_to_current_session` flips correctly.
5. While one worker runs, verify `activity="active"`; after normal completion, verify `finished`.
6. Create a fixture with `status="running"` and a dead PID under a temporary runs root; verify `stale` without mutating the artifact.
7. Verify a pre-v2 real run remains readable and is not rewritten.
8. Run `git diff --check` and inspect that changes stay within `__init__.py`, `core.py`, `test_profile_delegate.py`, `README.md`, `plugin.yaml`, and this plan.
9. Have an independent reviewer check identity precedence, privacy fields, legacy compatibility, and read-only liveness behavior.

## 5. Acceptance criteria

1. Default `profile_delegate_list()` never mixes known runs from different durable caller sessions.
2. Global inspection remains available only through explicit `scope="all"`.
3. Same-lane inspection across session rotations is explicit through `scope="current_lane"`.
4. `profile_delegate_status(task_id)` exposes provenance and whether the task belongs to the inspecting session.
5. Every new run persists normalized origin metadata from concurrency-safe Hermes context.
6. Existing `origin_session_key` notifications keep working.
7. Running detached workers are classified as active, dead-worker runs as stale, and unverifiable runs as unknown.
8. Inspection performs no lifecycle mutations.
9. Legacy runs remain readable without migration.
10. No database, background heartbeat, new dependency, alternate run root, or Hermes core patch is introduced.
11. Unit suite, lint, compile, CLI smoke, and two-session live smoke pass.

## 6. Explicit non-goals

- Enforcing authorization between local Hermes sessions.
- Guaranteeing PID ownership across arbitrary host reboot/PID reuse scenarios.
- Adding heartbeats, leases, cancellation, or stale-run repair.
- Moving artifacts or introducing SQLite.
- Persisting user identity, chat names, or message content.
- Pagination before retained run volume proves it necessary.
- Refactoring Hermes' native async completion queue.

## 7. Rollout and rollback

**Rollout:** additive artifact schema and tool output; fresh sessions/gateway restart required for updated schemas. No historical migration.

**Rollback:** revert plugin code/version. New artifacts remain compatible because old readers ignore additive `origin` and `artifact_schema_version` fields; legacy top-level `origin_session_key` remains present.

**Future escalation trigger:** only consider an indexed registry or worker leases if measured retention/query volume, restart recovery, or cancellation requirements exceed this artifact-based design.

## 8. Recommended commit sequence

1. `test: lock profile delegate origin scoping contracts`
2. `feat: scope profile delegate inspection by caller session`
3. `docs: document profile delegate run provenance`

Do not push or restart gateways without explicit approval.
