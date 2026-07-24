# Nested Profile Delegate visibility hardening plan

**Status:** plan only; no implementation, push, activation, restart, or live mutation authorized

**Goal:** reliably prevent the controller from repeating specialist work already delegated by a child profile. When a parent delegates to `builder` and Builder delegates to `reviewer`, the parent completion must expose a trustworthy bounded direct-child projection. If the nested review is still running, the controller must receive a durable reference and a deterministic status-recovery route rather than silently launching Reviewer again.

**Acceptance signal:** both synchronous and background/TUI parent runs expose direct nested delegations; async completion tells the controller whether nested work is complete or pending; `profile_delegate_status(parent_task_id)` refreshes the nested snapshot safely; custom run roots, hostile artifact layouts, incomplete nested runs, and oversized child output cannot cause false attribution, unsafe reads, incompatible artifacts, or silent truncation.

**Baseline:** local `main` at `a7dd959`, five commits ahead of `origin/main`, clean working tree. Preserve the reviewed synchronous lifecycle changes in `f9bbe2c` and `test_sync_lifecycle.py`. Do not rewrite heartbeat, interruption, cancellation, process-group termination, timeout precedence, recovery, or terminal-state protection unless a focused compatibility test proves it necessary.

**Approach:** replace the current directory scan and loose `parent_task_id` match with an explicit direct-lineage contract established before child launch. Persist the exact nested runs root and a private lineage token in the parent request, propagate both into child delegations, read nested artifacts through bounded no-follow identity checks, and produce one compact projection shared by sync finalization, TUI finalization, async completion, and status refresh. Keep this plugin-only: no Hermes-core patch, durable outbox, general message bus, recursive lineage graph, or exactly-once notification claim.

**Execution graph:**

```text
T0 -> T1 -> T2 -> T3 -> T4 -> T5 -> (T6a || T6b) -> T7 -> T8
```

- T0: freeze and characterize the latest baseline
- T1: define direct-lineage and projection contracts
- T2: add failing regression/adversarial tests
- T3: establish deterministic nested-root and lineage propagation
- T4: harden artifact discovery and bounded projection
- T5: integrate sync, TUI, async completion, and status refresh
- T6a: docs/tool guidance; T6b: compatibility/security regression expansion
- T7: release gate and independent review
- T8: approval-gated activation smoke

---

## T0 — Freeze the latest baseline

**Objective:** ensure implementation starts from the other session's clean, reviewed lifecycle baseline and does not accidentally reopen synchronous lifecycle defects.

**Depends on:** none

**Mode:** sequential hard gate

**Write surface:** none

**Actions:**

1. Confirm `HEAD`, clean status, and the five local commits ahead of `origin/main`.
2. Record the current full gate result and rerun the baseline gate before source edits.
3. Read the failed nested-delegation review artifact at `/opt/data/profile_delegate/runs/pd_20260724_084545_309gyf/stdout.txt` and map every blocker to a task below.
4. Treat `f9bbe2c` synchronous lifecycle behavior as a protected compatibility surface.

**Acceptance evidence:**

```bash
git status --short --branch
git log --oneline origin/main..HEAD
PYTHONPATH=/opt/hermes .venv/bin/python -m pytest -q -o 'addopts='
.venv/bin/ruff check .
.venv/bin/python scripts/validate_release.py
git diff --check
```

Expected starting test count: 324. Any baseline drift stops implementation until reconciled.

---

## T1 — Define one direct-lineage contract

**Objective:** remove ambiguity about attribution, roots, pending nested work, and what the parent/controller receives.

**Depends on:** T0

**Mode:** sequential

**Write surface:** tests and contract comments first; no behavioral implementation yet

**Contract:**

1. Each parent Profile Delegate run owns:
   - canonical parent `task_id`;
   - random private `lineage_token` generated at run creation;
   - exact `expected_nested_runs_root` derived from the child launch environment.
2. Child launch propagates only the parent task ID, lineage token, and expected nested root through bounded internal environment variables.
3. A nested request persists `parent_task_id` and a hash or exact private lineage token. The token is never returned in model-facing results, notifications, logs, or spectator output.
4. A direct nested run is attributable only when all are true:
   - nested directory name is a canonical task ID;
   - directory is a real owned directory under the pinned root, not a symlink;
   - request/status/result files pass bounded no-follow regular-file checks;
   - request `task_id` equals directory name;
   - request parent task ID and lineage token match the parent;
   - status/result identities match when present.
5. Same-UID profiles remain outside an OS security boundary. The token prevents accidental/ambient attribution and raises the bar against forged sibling artifacts; docs must not call it a sandbox.
6. A nested projection has explicit lifecycle:
   - `completed`, `failed`, `cancelled`, or `timed_out` with a bounded result projection;
   - `running`/`pending` with a stable nested task ID and expected result path, even before `result.json` exists;
   - `unreadable`/`invalid` is reported as metadata, never silently promoted to a valid nested result.
7. The parent result is a snapshot. `profile_delegate_status(parent_task_id)` performs a fresh bounded reconciliation before returning, without claiming automatic post-parent notification.
8. Async parent completion must include a compact nested projection or an explicit pending/truncated signal and tell the controller to inspect the parent task before redelegating.

**Required projection fields:**

```json
{
  "task_id": "pd_...",
  "profile": "reviewer",
  "session_title": "review builder output",
  "status": "completed|failed|cancelled|timed_out|running|unknown",
  "result": {
    "status": "ok|blocked|failed|unknown",
    "summary": "bounded",
    "artifacts": ["bounded paths/URLs"],
    "errors": ["bounded"],
    "next_steps": ["bounded"]
  },
  "result_path": "/validated/expected/path/result.json",
  "snapshot_at": "ISO-8601"
}
```

Parent metadata must also expose `nested_delegations_truncated`, `nested_delegations_matched`, and `nested_delegations_returned`.

---

## T2 — Add failing tests for all reviewed blockers

**Objective:** reproduce the defects before changing production behavior.

**Depends on:** T1

**Mode:** sequential

**Write surface:** new `test_nested_delegation_visibility.py`; minimal helper reuse from existing tests

**Required RED tests:**

1. Custom `PROFILE_DELEGATE_RUNS_ROOT` is resolved exactly as the nested child resolves it; no hand-placed artifact under a convenient profile-default directory.
2. Profile-default nested root works when no explicit override exists.
3. Sync parent result exposes a completed direct nested review.
4. TUI/background parent `result.json` exposes the same projection.
5. `_make_profile_delegate_summary()` / queued async completion exposes completed nested review metadata.
6. Async completion exposes pending nested work and the parent status recovery instruction.
7. Parent status reconciliation changes a nested snapshot from running/no result to completed/result after the nested artifact appears.
8. Pending nested entries always expose their validated expected `result_path`.
9. Unrelated request with the parent task ID but wrong lineage token is ignored/reported invalid.
10. Reject symlink root, run directory, request, status, and result artifacts.
11. Reject traversal/out-of-root resolution, noncanonical directory ID, cross-file task-ID mismatch, wrong owner, non-regular files, and oversized files.
12. Bound candidate scan count, matched child count, list lengths, per-string length, and aggregate serialized projection size.
13. Truncation is explicit and deterministic; newest relevant direct children are preferred when the cap is reached.
14. Maximum legal parent `result.json` remains accepted by `spectator.inspect_run()`.
15. Markdown/custom-output nested reviews expose enough bounded information or a safe validated retrieval path to avoid repeating the review.
16. Existing `test_sync_lifecycle.py` remains green throughout.

**Test design rule:** tests must invoke the same root resolver and projection functions used by production. Fixtures that manually write to the directory the assertion expects are insufficient.

**Focused command:**

```bash
PYTHONPATH=/opt/hermes .venv/bin/python -m pytest -q -o 'addopts=' \
  test_nested_delegation_visibility.py test_sync_lifecycle.py
```

---

## T3 — Pin the expected nested root and lineage at launch

**Objective:** make nested discovery independent of guessed profile layout and resistant to accidental attribution.

**Depends on:** T2

**Mode:** sequential

**Write surface:** `core.py`, `tui_runner.py`, focused tests

**Actions:**

1. Add one resolver that computes the child's effective nested runs root:
   - explicit `PROFILE_DELEGATE_RUNS_ROOT` wins;
   - otherwise use the validated target profile home plus `profile_delegate/runs`.
2. Resolve and validate the root before launch; persist it in parent `request.json`.
3. Generate a cryptographically random lineage token at parent run allocation and persist it privately.
4. Extend `child_environment()` to propagate parent task ID, lineage token, and pinned nested root without disturbing the synchronous lifecycle environment cleanup introduced by `f9bbe2c`.
5. When a nested `delegate_profile()` request is created, capture the propagated parent identity/token into its request/status artifacts.
6. Include lineage-bearing fields in duplicate fingerprinting where required so unrelated parent runs cannot collapse into one nested request.
7. Never expose the token through model-facing tool responses, status responses, notifications, spectator events, or error text.

**Acceptance evidence:** root-resolution and token-lineage tests pass under explicit/custom root, default profile root, sync launch, and TUI launch.

---

## T4 — Replace loose scanning with secure bounded reconciliation

**Objective:** collect only trustworthy direct children while keeping parent artifacts within existing inspection limits.

**Depends on:** T3

**Mode:** sequential

**Write surface:** `core.py`; optionally a small standalone helper module only if it materially improves testability

**Actions:**

1. Replace `collect_nested_delegations()` with a reconciler over the pinned root.
2. Use no-follow opens/stat checks, same-owner checks, regular-file/directory checks, resolved containment, canonical task-ID validation, and bounded JSON reads.
3. Validate request/status/result schema and cross-file identity before projection.
4. Cap work before reading content:
   - bounded candidate directory scan;
   - bounded relevant matches;
   - bounded file bytes;
   - bounded list items and string lengths;
   - one aggregate serialized-byte budget safely below the spectator artifact limit.
5. Prefer newest matching direct children, define ordering, and expose total/matched/returned/truncated metadata.
6. Always return a validated expected result path for pending children; do not require the file to exist.
7. Keep custom child fields out of the compact projection unless explicitly allowed. For Markdown/custom JSON, expose a validated bounded retrieval path rather than copying unbounded raw output.
8. Read status/result conservatively: a terminal validated result may refine status; contradictory snapshots must be marked inconsistent rather than fabricated into one clean state.

**Budget gate:** construct the largest allowed parent result and prove it remains below `spectator.MAX_JSON_BYTES` with safety headroom and passes `spectator.inspect_run()`.

---

## T5 — Integrate every controller-visible path

**Objective:** ensure the controller sees and can recover nested work regardless of sync or background/TUI execution.

**Depends on:** T4

**Mode:** sequential

**Write surface:** `core.py`, `tui_runner.py`, `spectator.py` only if schema projection is intentionally expanded, integration tests

**Actions:**

1. Use the same reconciler during synchronous finalization and TUI finalization.
2. Add a compact nested projection to `_make_profile_delegate_summary()` within the existing notification character budget.
3. If nested data cannot fit, include deterministic metadata:
   - nested work exists;
   - completed/pending counts;
   - returned task IDs/statuses;
   - truncation flag;
   - instruction to call `profile_delegate_status(parent_task_id)` before any equivalent follow-up delegation.
4. Make `profile_delegate_status()` refresh the parent nested snapshot in-memory from the pinned root before returning it. Do not mutate terminal execution/task state.
5. Keep `result.json` as the durable completion-time snapshot; status refresh may return a fresher projected view without claiming that historical parent artifacts were atomically rewritten.
6. Ensure `profile_delegate_list()` remains compact and does not expand nested results.
7. Update model-facing tool guidance: a matching pending nested reviewer is a dependency to inspect/wait for, not permission to launch another reviewer.

**Acceptance journeys:**

- `default -> builder -> reviewer(sync)` returns reviewer result directly.
- `default -> builder -> reviewer(background)` returns a pending nested reference; after reviewer completion, parent status returns the completed review without a second delegation.
- custom root and profile-default root behave identically.
- notification truncation still tells the controller nested work exists and how to recover it.

---

## T6a — Correct product and operator guidance

**Objective:** align docs and tool behavior with actual guarantees.

**Depends on:** T5

**Mode:** parallel with T6b after implementation stabilizes

**Write surface:** `README.md`, `CHANGELOG.md`, `STATE.md`, `.hermes/handoff.md`, `__init__.py`, `TODO.md` if follow-up remains

**Actions:**

1. Document direct-child lineage only; no recursive graph/message-bus claim.
2. Document snapshot semantics for pending nested work and the parent-status recovery route.
3. Document custom root behavior and bounded/truncated projections.
4. Remove stale “no blockers” language until independent review passes.
5. Correct `STATE.md` commit/push wording: the current baseline is committed locally and ahead of origin.
6. Add the nested hardening work under `CHANGELOG.md` Unreleased.

---

## T6b — Compatibility and security regression expansion

**Objective:** prove the fix does not damage the latest lifecycle baseline or existing public contracts.

**Depends on:** T5

**Mode:** parallel with T6a; tests own test files only

**Write surface:** tests

**Required coverage:**

- all `test_sync_lifecycle.py` heartbeat/cancel/timeout/process-group tests;
- output parsing and transient resume behavior;
- duplicate guard and recursion depth;
- origin authorization for status/list/cancel/steer;
- current and legacy result/spectator artifacts;
- sync and detached TUI execution;
- notification remains best-effort and independent from task success;
- no private lineage token appears in any public response or journal.

---

## T7 — Full gate and independent review

**Objective:** require evidence stronger than the first fast implementation.

**Depends on:** T6a and T6b

**Mode:** sequential release gate

**Write surface:** no production changes during review; verified findings return to the owning task

**Commands:**

```bash
PYTHONPATH=/opt/hermes .venv/bin/python -m pytest -q -o 'addopts='
.venv/bin/ruff check .
.venv/bin/python -m py_compile \
  __init__.py child_bootstrap.py cli.py cli_smoke.py core.py \
  event_journal.py event_schema.py spectator.py tui_rpc.py tui_runner.py \
  scripts/validate_release.py test_event_journal.py test_profile_delegate.py \
  test_reliability_reset.py test_spectator.py test_tui_rpc.py \
  test_sync_lifecycle.py test_nested_delegation_visibility.py
.venv/bin/python scripts/validate_release.py
git diff --check
```

Then request one clean-room Reviewer pass focused on:

- custom root correctness;
- lineage token secrecy and attribution;
- no-follow/ownership/containment checks;
- bounded reads and parent result size;
- pending-to-completed recovery;
- actual async completion visibility;
- preservation of `f9bbe2c` lifecycle behavior.

**Release gate:** no commit/push/activation claim until Reviewer returns PASS or PASS_WITH_RESIDUAL_RISK with no material blocker and every applicable command passes.

---

## T8 — Approval-gated activation and live acceptance smoke

**Objective:** prove the loaded plugin behaves correctly after explicit operator approval.

**Depends on:** T7

**Mode:** sequential; externally visible runtime action requires Alberto's approval

**Actions:**

1. Confirm no active delegated run would be disrupted.
2. Record current commit as rollback target.
3. Restart/reload only after explicit approval.
4. Run harmless bounded live journeys:
   - parent -> builder -> reviewer sync;
   - parent -> builder -> reviewer background/pending -> status refresh.
5. Inspect actual parent completion payload and verify the controller does not delegate Reviewer again.
6. Roll back to the recorded commit if schema loading, notification, status recovery, or lifecycle behavior regresses.

No push, tag, release, or gateway activation is implied by plan completion.

---

## Risk register

| Risk | Consequence | Mitigation / gate |
|---|---|---|
| Reopening synchronous lifecycle defects | stuck foreground child, bad cancellation, false terminal state | protect `f9bbe2c`; run `test_sync_lifecycle.py` in every focused/full gate |
| Guessed run root | nested work invisible under custom config | persist exact child-effective root before launch; test explicit and default roots |
| Forged/symlinked artifacts | false attribution or outside-root disclosure | token lineage, no-follow owned regular files/dirs, containment, cross-file identity |
| Nested run completes after parent | stale parent snapshot leads to duplicate review | pending reference plus deterministic parent-status reconciliation |
| Oversized nested results | spectator rejection or context/memory pressure | bounded reads/items/strings/aggregate with explicit truncation and size gate |
| Notification omits nested data | controller repeats reviewer | compact completion projection or mandatory pending/truncation recovery signal |
| Scope expands into message bus | complexity and false durability claims | direct children only; no automatic guaranteed delivery or recursive graph |

## Residual uncertainty

- Plugin-only design cannot guarantee a second notification when a nested background run finishes after its parent. The accepted behavior is explicit pending state plus status recovery, not a hidden outbox.
- Profiles sharing one OS user are not security sandboxes. Filesystem hardening and lineage tokens protect correctness and accidental/ambient attribution, not against a fully malicious same-UID profile.
- Whether the model consistently obeys the new “inspect nested work before redelegating” guidance requires the live acceptance smoke after restart; unit tests can prove payload visibility, not model judgment.

## Stop/reassessment triggers

Stop and revisit the design if implementation requires any of:

- Hermes-core modification;
- a durable plugin-owned message bus/outbox;
- rewriting synchronous lifecycle ownership from `f9bbe2c`;
- exposing private lineage tokens to the model;
- parent result sizes that cannot stay below spectator limits;
- cross-profile status access that weakens current origin authorization.

The preferred fallback is a smaller direct-child reference contract with explicit status recovery—not another orchestration cathedral.