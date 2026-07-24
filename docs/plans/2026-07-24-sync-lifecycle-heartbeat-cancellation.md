# Synchronous Profile Delegate lifecycle repair plan

**Status:** plan only; no implementation or activation authorized

**Goal:** repair the confirmed synchronous `profile_delegate` lifecycle defect without changing Hermes core, execution-mode policy, existing result semantics, background TUI behavior, or unrelated local work. Acceptance requires a quiet foreground child to propagate activity, parent interrupt/exact-origin cancellation to reap the complete process group and finalize `cancelled`, plugin deadline to remain authoritative as `timed_out`, and all existing plugin release gates to remain green.

**Approach:** make the smallest plugin-local lifecycle change around the existing synchronous subprocess owner. Extend `run_capped_subprocess()` with defensive Hermes callbacks, explicit stop reasons, verified process-group termination, throttled status publication, and a foreground-consumable cancellation marker. Keep parsing, recovery, duplicate protection, approvals, origin matching, notification behavior, and background TUI control structurally unchanged unless a focused regression proves a required compatibility adjustment.

**Canonical source:** `/opt/data/plugins/profile-delegate`

**Read-only dependency surface:** `/opt/hermes` (inspection/import only; never edit)

**Current constraints and evidence:**

- `core.py:1220-1302` owns the synchronous process group and output streaming but currently checks only its wall-clock deadline; timeout uses immediate `SIGKILL`.
- `core.py:2070-2204` owns synchronous retries, result classification, artifact finalization, and concurrency-slot scope.
- `core.py:2641-2696` authorizes cancellation exactly but only routes it through background TUI control.
- Hermes exposes thread-local `touch_activity_if_due()` in `/opt/hermes/tools/environments/base.py` and `is_interrupted()` in `/opt/hermes/tools/interrupt.py`.
- The current working tree already contains unrelated, uncommitted nested-delegation changes in `README.md`, `STATE.md`, `__init__.py`, `core.py`, `test_profile_delegate.py`, and `tui_runner.py`. Those changes must be preserved byte-for-byte outside intentional overlapping hunks.
- Live status inspection currently reports many historical `running` artifacts, including incident run `pd_20260724_080041_egig47`. Status alone is not proof of live execution; no implementation, smoke, activation, restart, or cancellation may begin until a non-mutating process-identity inventory distinguishes live workers from stale artifacts.
- Existing accepted decision `decisions/0001-plugin-only-reliability-boundary.md` remains authoritative: execution, task, contract, notification, and transport states stay independent.

**Execution graph:**

`T0 -> T1 -> T2 -> T3 -> T4 -> (T5a || T5b) -> T6 -> T7 -> T8`

- T0: safety and baseline gate
- T1: lifecycle contract and test seam
- T2: focused failing regressions
- T3: synchronous polling/termination implementation
- T4: foreground cancellation/status integration
- T5a: guidance/docs; T5b: compatibility regression expansion
- T6: narrow and full validation
- T7: controlled live smokes
- T8: approval-gated activation and rollback verification

---

## T0 — Freeze scope, inventory live execution, and preserve the baseline

**Objective:** prove implementation can start without interfering with an active delegation and create a trustworthy comparison baseline without modifying or discarding unrelated work.

**Depends on:** none

**Mode:** sequential hard gate

**Write surface:** no project writes except execution-time private evidence outside the repository; do not edit source yet

**Actions:**

1. Record `git status --short --branch`, `git diff --stat`, `git diff --check`, and hashes of all dirty files.
2. Save a private binary-capable patch of the pre-existing dirty tree outside the repository, with mode `0600`; record its SHA-256. This is preservation evidence, not a commit.
3. Inspect all plugin run artifacts read-only, then inspect OS process trees and process start identities for plausible Profile Delegate parent/child/Reviewer processes.
4. Classify each apparent `running` entry as:
   - verified live;
   - verified dead/stale;
   - unverifiable.
5. Stop before source edits if any delegation is verified live or unverifiable in a way that could overlap plugin loading/execution. Do not cancel it. Wait for operator direction or natural completion.
6. Once no live delegation exists, run the established full baseline gate without changing files. Compare the result with the documented 306-test local state and record any drift before touching code.

**Acceptance evidence:**

```bash
git status --short --branch
git diff --stat
git diff --check
PYTHONPATH=/opt/hermes .venv/bin/python -m pytest -q -o 'addopts='
.venv/bin/ruff check .
.venv/bin/python scripts/validate_release.py
```

Plus a read-only process inventory containing PID, PPID, PGID/SID, command identity, and process start time for any candidate process. PID existence alone is insufficient.

**Rollback/recovery:** no source change exists yet. If baseline differs from the documented state, stop and reconcile before implementation.

---

## T1 — Define one explicit synchronous lifecycle contract

**Objective:** remove ambiguity before code changes by defining inputs, stop precedence, terminal states, and status ownership.

**Depends on:** T0

**Mode:** sequential

**Write surface:** `core.py` interfaces/tests only after T0 passes

**Contract to implement:**

1. `run_capped_subprocess()` remains the sole owner of its spawned process and process group.
2. It receives optional plugin-local hooks/data rather than importing project state globally:
   - activity touch function or defensive runtime resolver;
   - interrupt predicate or defensive runtime resolver;
   - run directory/control predicate;
   - throttled status callback;
   - injectable monotonic clock/poll cadence only where tests require it.
3. It returns an explicit stop reason, not competing booleans:
   - `exited`;
   - `timed_out`;
   - `cancelled`;
   - `interrupted`;
   - internal spawn/integrity failure through the existing exception path.
4. Parent interrupt and accepted exact-origin cancellation both map to terminal lifecycle `cancelled`, while retaining bounded diagnostic metadata distinguishing their trigger.
5. Deadline remains monotonic and authoritative. Activity touches never alter it.
6. Once a stop reason is selected, no more output is accepted and no transient resume is eligible.
7. Terminal precedence at a polling boundary:
   - validated integrity/policy failure already known by the owner;
   - observed parent interrupt or consumed cancellation marker;
   - expired plugin deadline;
   - natural exit observed by `poll()`.

The precedence must be encoded in tests. If implementation evidence shows natural exit was already reaped before an interrupt/cancel observation, natural exit wins; do not rewrite completed work retroactively.

**Acceptance evidence:** focused tests name and assert every terminal transition and race boundary; no production edit is accepted until those tests fail for the current implementation for the intended reason.

**Rollback/recovery:** keep the interface additive where possible so existing fake `run_capped_subprocess()` test doubles remain easy to adapt and no unrelated parser/result code is rewritten.

---

## T2 — Add focused regressions before behavioral changes

**Objective:** create deterministic evidence for the defect and every required terminal path without real 15/30-minute waits.

**Depends on:** T1

**Mode:** sequential

**Write surface:** preferably a new focused file such as `test_sync_lifecycle.py`; touch `test_profile_delegate.py` only where existing helpers/contracts make that materially safer

**Required tests:**

1. Quiet foreground subprocess crosses a simulated inactivity boundary and emits periodic activity callbacks.
2. Labels are content-free and match `profile_delegate child running (<elapsed>s elapsed)`; private task/context/output cannot appear.
3. Activity callbacks cease after success, child failure, timeout, cancellation, and interrupt.
4. Interrupt kills a direct child plus grandchild process group, waits/reaps, and leaves neither process alive.
5. Exact-origin foreground cancellation creates/recognizes a control marker and succeeds.
6. Repeated foreground cancellation is idempotent.
7. Wrong-origin cancellation remains fail-closed and creates no marker/state mutation.
8. Plugin timeout terminates the process group and reports `timed_out`, never `cancelled`.
9. Interrupted/cancelled execution is not transiently resumed.
10. A terminal `cancelled` status cannot later become `completed`.
11. Foreground running status reports phase, worker PID, verified owner liveness, latest activity, start time, deadline/timeout, cancellation/interruption fields, then truthful terminal metadata.
12. Status writes are atomic, throttled, bounded, and contain no prompt or child output.
13. Existing output caps, diagnostic tails, result parsing, duplicate behavior, and recovery semantics remain unchanged.
14. Tool guidance recommends background mode but does not auto-select, reject, or cap either mode.

**Test design controls:**

- Use subprocess fixtures with private temp run roots.
- Use short real waits only for process-group/reaping proof; inject clocks/cadences for heartbeat/deadline tests.
- Poll `/proc/<pid>/stat` or equivalent process identity data and reap direct children; do not assert only `os.kill(pid, 0)`.
- Add a test-only secret sentinel to task/output and assert it is absent from heartbeat labels and status JSON.
- Assert status write count stays below a defined bound for a given simulated duration.

**Acceptance evidence:** current code fails the new tests specifically because heartbeat, interrupt propagation, foreground marker cancellation, and truthful sync status are absent—not because fixtures are flaky.

**Rollback/recovery:** tests are isolated and can be removed independently if the lifecycle contract is rejected before implementation.

---

## T3 — Implement defensive heartbeat, interruption, and process-group shutdown

**Objective:** make the synchronous polling loop responsive to Hermes lifecycle signals while preserving output caps and plugin deadline semantics.

**Depends on:** T2

**Mode:** sequential

**Write surface:** `core.py`, narrowly around runtime-helper resolution, `run_capped_subprocess()`, and a small process-group termination helper

**Actions:**

1. Add defensive helper resolution:
   - attempt to import `tools.environments.base.touch_activity_if_due`;
   - attempt to import `tools.interrupt.is_interrupted`;
   - fall back to no-op/false for direct plugin tests outside Hermes.
2. Initialize activity state once per subprocess attempt using monotonic timestamps. Call `touch_activity_if_due(state, "profile_delegate child running")` only while the child is verified active and before a terminal reason is selected.
3. Poll interruption and foreground cancellation every loop cycle.
4. Replace timeout's immediate `SIGKILL` with a shared owned-process-group terminator:
   - confirm the direct child is still the `Popen` object owned by this loop;
   - send `SIGTERM` to its process group;
   - wait a short bounded grace period within the original deadline/bookkeeping budget;
   - send `SIGKILL` only if the owned group remains alive;
   - reap the direct child;
   - handle `ProcessLookupError` idempotently.
5. Close selector registrations/streams in `finally` regardless of exit path.
6. Return stop reason, exit code when available, termination escalation metadata, and output-cap metadata without embedding child content.

**Acceptance evidence:** all T2 subprocess tests pass; existing timeout/output-cap tests still pass; direct child and grandchild process identities no longer exist after cancel/interrupt/timeout tests.

**Rollback/recovery:** revert only the new helper and polling-loop hunks using the T0 patch/hash baseline; do not reset the repository or discard pre-existing dirty changes.

---

## T4 — Add foreground control markers, truthful status, and single terminal finalization

**Objective:** connect the synchronous lifecycle owner to exact-origin cancellation and durable state without weakening existing background TUI controls.

**Depends on:** T3

**Mode:** sequential

**Write surface:** `core.py`, `__init__.py`, focused tests

**Actions:**

1. Extend `profile_delegate_cancel()` after the existing exact-origin check:
   - background TUI runs continue through current command/ack transport;
   - foreground CLI runs atomically create a bounded plugin-owned cancellation marker under the existing private `control/` tree;
   - repeat requests return the same pending/accepted cancellation idempotently;
   - no handler signals a PID directly.
2. Keep `profile_delegate_steer()` unchanged and unavailable for foreground CLI runs.
3. Let the synchronous polling loop consume the marker. The process owner performs termination and writes an acknowledgement.
4. Publish foreground lifecycle status at a bounded cadence, not every 200 ms. Additive fields:
   - `phase`;
   - `worker_pid` and process identity token/start identity;
   - verified `worker_alive`/transport liveness owned by the current loop;
   - `latest_activity`;
   - `started_at`, `ended_at`;
   - `timeout_seconds` and/or deadline timestamp;
   - `cancellation_requested`, `interrupted`;
   - `terminal_reason`;
   - `exit_code` when known.
5. Do not use the existing advisory bare-PID probe as authority for process action. It may remain read-only compatibility output, but foreground authoritative liveness must come from the owning `Popen` flow plus identity metadata.
6. Centralize synchronous terminal finalization so each path writes one compatible `result.json`, then atomically finalizes `status.json` once. Existing terminal immutability in `merge_run_status()` must prevent later overwrite.
7. Disable transient recovery for timeout, interrupt, cancellation, policy/integrity failure. Preserve same-session recovery only for the existing recognized transient transport allowlist.
8. Ensure concurrency slot release remains guaranteed by context-manager exit even if result/status writing raises; if artifact finalization itself fails, preserve a fail-closed diagnosable state without pretending completion.

**Acceptance evidence:** cancellation/status tests pass; exact-origin tests show no mutation on denial; terminal status and result artifact agree for completed, failed, timed-out, and cancelled runs.

**Rollback/recovery:** additive status fields permit old readers to continue. Do not bump artifact schema unless a test proves readers require it; if a bump is required, add a read-only compatibility projection and document it explicitly.

---

## T5a — Update advisory execution-mode guidance

**Objective:** improve model/operator choice without changing runtime dispatch policy.

**Depends on:** T4

**Mode:** parallel with T5b; non-overlapping documentation/schema hunks

**Write surface:** `__init__.py`, `README.md`

**Actions:**

- Explain foreground mode waits synchronously and occupies the originating turn.
- Explain background mode returns a task ID and keeps the conversation responsive.
- Recommend background for long, multi-stage, or independently monitorable work.
- Keep short bounded specialist work eligible for foreground.
- State explicitly that this is advisory; no automatic conversion, rejection, or new duration cap exists.
- Update cancellation schema text to cover exact-origin foreground cancellation while keeping steering TUI-only.

**Acceptance evidence:** schema tests assert wording and handler behavior; calls with either `background=false` or `background=true` remain accepted under existing policy.

**Rollback/recovery:** docs/schema-only hunks can be reverted independently.

---

## T5b — Run preservation-focused compatibility tests

**Objective:** prove the repair did not damage already-working surfaces.

**Depends on:** T4

**Mode:** parallel with T5a

**Write surface:** tests only if coverage gaps are discovered

**Required preserved behavior:**

- output caps/truncation and diagnostic tails;
- structured/custom result parsing and output modes;
- same-session transient recovery only for recognized transport failures;
- duplicate guard/fingerprints;
- child approval policy and capability presets;
- exact-origin ownership;
- background TUI steering/cancellation;
- background detached/thread execution and notification behavior;
- private permissions and durable artifacts;
- nested-delegation lineage currently present in the dirty tree;
- reliability-reset adversarial fixtures.

**Acceptance evidence:** focused legacy tests plus full suite pass without weakening assertions.

**Rollback/recovery:** if a regression requires broad redesign outside the synchronous lifecycle boundary, stop and reassess instead of expanding scope.

---

## T6 — Narrow-to-full validation and independent diff review

**Objective:** verify behavior and detect collateral damage before any live smoke or activation.

**Depends on:** T5a and T5b

**Mode:** sequential

**Write surface:** `STATE.md`, `CHANGELOG.md`, or `.hermes/handoff.md` only during implementation if release/project policy requires recording actual completed evidence; preserve current unrelated edits

**Validation order:**

1. New focused lifecycle tests.
2. Existing process/output/status/control tests.
3. Fast feedback contract from `.agents/validation.md`.
4. Full release gate:

```bash
PYTHONPATH=/opt/hermes .venv/bin/python -m pytest -q -o 'addopts='
.venv/bin/ruff check .
.venv/bin/python -m py_compile \
  __init__.py child_bootstrap.py cli.py cli_smoke.py core.py \
  event_journal.py event_schema.py spectator.py tui_rpc.py tui_runner.py \
  scripts/validate_release.py \
  test_event_journal.py test_profile_delegate.py test_reliability_reset.py \
  test_spectator.py test_tui_rpc.py test_sync_lifecycle.py
.venv/bin/python scripts/validate_release.py
git diff --check
```

5. Read-only Hermes discovery/registration smoke from a fresh process; no gateway restart.
6. Secret-pattern scan across intended changes.
7. Compare dirty-file hashes/diff against the T0 snapshot and classify every changed hunk as pre-existing or lifecycle-repair work.
8. Independent review focused on races, process identity, terminal immutability, origin checks, deadline authority, and preservation of unrelated dirty work.

**Acceptance evidence:** exact command outputs, test counts, diff review, and no unclassified changes.

**Rollback/recovery:** if full suite regresses, revert only lifecycle-repair hunks using the preserved patch/hash map. Never use destructive reset on the dirty canonical tree.

---

## T7 — Controlled smoke validation without activation restart

**Objective:** obtain real behavioral proof after tests, only when no delegation is active.

**Depends on:** T6 and a repeated T0 live-process gate

**Mode:** sequential, operator-visible, no restart/recreate

**Write surface:** private temporary run roots/artifacts only; no public Spartan Gate files

**Smokes:**

1. Quiet foreground subprocess with a test-only shortened activity interval or direct harness. Verify periodic parent activity callback labels while the child remains alive and verify callbacks stop at exit.
2. Foreground cancellation smoke that spawns a descendant. Issue cancellation from the exact origin and prove direct child and descendant are gone/reaped; inspect terminal `status.json` and `result.json`.
3. Parent-interrupt harness using the same polling path. Prove `cancelled`, no transient resume, and no later overwrite.
4. Timeout smoke proving `timed_out`, process-group termination, and no cancellation classification.
5. Bounded background smoke proving immediate task-ID return, originating caller usability, completion/status preservation, and unchanged TUI controls/notification behavior.

**Acceptance evidence:** task IDs, private artifact paths, sanitized status excerpts, process identity before/after, callback timestamps, and unchanged gateway restart count.

**Rollback/recovery:** smokes use isolated runs and bounded children. If cleanup cannot be proven, stop; do not restart the gateway as a broom.

---

## T8 — Approval-gated activation and rollback

**Objective:** activate only after explicit operator approval and a final no-active-run check.

**Depends on:** T7

**Mode:** hard approval gate

**Write surface:** installed private plugin activation path/config only if separately approved; never `/opt/hermes`

**Activation preconditions:**

1. No verified active or unverifiable delegation.
2. Current plugin source preserved as a private rollback target with hash/metadata.
3. Focused/full tests and smokes passed.
4. Exact activation method documented; no image rebuild.
5. Operator explicitly approves any required gateway restart/reload.

**Post-activation acceptance:**

- plugin discovery succeeds in a fresh process;
- one bounded foreground and one bounded background acceptance run pass;
- foreground activity reaches the gateway tracker;
- exact-origin cancellation reaps descendants;
- restart count changes only by the explicitly approved activation action.

**Rollback:** restore the preserved plugin snapshot atomically, verify hashes and discovery, then perform a restart/reload only with operator approval and only after confirming no delegation is active. Re-run one bounded foreground and background smoke.

---

# Risk register and assessment method

Likelihood and consequence are kept separate; no fake composite score. Each risk has a discriminating assessment and a stop gate.

| Risk / failure mode | Likelihood before fix | Consequence | Detectability | How to assess | Mitigation / gate | Residual risk |
|---|---:|---:|---|---|---|---|
| Editing while a real delegation is active changes code loaded by a nested/new child | Medium now; live/stale state is ambiguous | High: inconsistent execution or lost work | Medium | Read-only run inventory plus PID/PPID/PGID/SID/start-identity inspection | T0 hard stop on live or unverifiable execution; never cancel automatically | Low after verified quiescence; stale artifacts remain operational debt |
| Overwriting unrelated dirty nested-delegation work | High without controls | High: regression/lost local work | High | T0 binary patch, hashes, hunk classification, final diff comparison | No reset/checkout; minimal overlapping hunks; independent diff review | Low, but `core.py`/tests overlap and require careful reconciliation |
| Heartbeats extend plugin deadline accidentally | Medium | High: unbounded foreground execution | High | Injected monotonic clock test; assert deadline unchanged across touches | Deadline created once and never mutated; heartbeat helper receives no timeout authority | Low |
| Heartbeat label leaks prompt/profile/output | Low–Medium | High privacy impact | High | Secret-sentinel tests over callback labels/status artifacts | Fixed content-free label; no dynamic data except integer elapsed seconds | Very low |
| Heartbeat callback fires after terminal selection | Medium in racey cleanup | Medium: false liveness | High | Per-terminal-path callback count/timestamp tests | Select terminal reason before cleanup; no touches in termination/finally | Low |
| Parent interrupt is checked on the wrong thread | Medium because Hermes interruption is thread-local | High: `/stop` appears ineffective | Medium | Integration test invoking `is_interrupted()` on the actual tool worker thread; compare with Hermes worker propagation behavior | Resolve/call predicate inside synchronous polling thread; no helper thread polling | Low, dependent on Hermes preserving current thread propagation contract |
| Cancellation handler signals a reused/unverified PID | Avoided by marker design | Critical: kills unrelated process | High | Assert handler performs no signal; process owner uses its own `Popen` object and identity | Marker-only external control; owned process-group action | Very low on POSIX |
| SIGTERM grace consumes deadline or hangs | Medium | High: slot/turn remains blocked | High | TERM-ignoring fixture with bounded grace and elapsed-time assertion | Short bounded grace; deadline-aware; SIGKILL fallback; direct-child reap | Low |
| Only direct child dies; Reviewer/MCP/terminal descendants survive | Medium–High in current defect | Critical: orphan side effects/resource leak | High on Linux | Spawn child+grandchild fixture; capture PGID and process start identities; verify group gone | `start_new_session=True`, group TERM→KILL, reap owner | Low for descendants that deliberately daemonize into another session; document as residual |
| Timeout misclassified as cancellation in a race | Medium | High: dishonest lifecycle/recovery policy | High | Deterministic boundary tests with injected clock and cancellation marker timing | Explicit precedence and single stop reason | Low; exact simultaneous OS events remain ordering-dependent but deterministic in poll loop |
| Cancelled run later overwritten as completed | Medium without centralization | High: false success | High | Race test delayed child exit/finalizer plus terminal immutability assertion | Single finalizer; terminal-owned fields immutable; no parsing after cancel | Low |
| Cancellation/interrupt triggers transient resume | Medium because recovery loop wraps attempts | Critical if child had side effects | High | Mock transient-looking output after interrupt; assert one attempt only | Stop reasons categorically ineligible for recovery | Very low |
| Status writes every 200 ms cause IO churn/races | High if naively implemented | Medium | High | Count intercepted atomic writes over simulated runtime | Separate status cadence (e.g. 1–5 s) from 200 ms poll; write on material transitions | Low |
| Status contains child output/prompt | Low if additive metadata is disciplined | High privacy impact | High | Sentinel scan of every status snapshot | Allowlist lifecycle fields; output remains capped files only | Very low |
| `status.json` and `result.json` disagree after artifact-write failure | Medium in exceptional paths | High: unreliable durable truth | Medium | Fault-injection tests on result write and terminal status write | Defined ordering, fail-closed error artifact/status, idempotent finalizer | Low–Medium; two-file atomic transaction is intentionally out of scope |
| Existing terminal lock semantics silently ignore necessary final metadata | Medium | Medium | High | Tests final state fields before/after duplicate finalizer call | Extend `TERMINAL_OWNED_STATUS_FIELDS` deliberately; assert immutable projection | Low |
| Bare PID liveness is mistaken for verified identity | Existing risk in advisory background status | High if used for action | Medium | PID reuse/identity-token tests and code review | Never use `probe_worker_alive()` as process-action authority; owning loop publishes verified state | Low for foreground; background advisory limitation remains |
| Foreground cancellation weakens exact-origin authorization | Low if branch occurs after shared check | Critical security boundary | High | Positive exact-origin and negative mismatched session/lane tests; assert no marker on denial | Reuse unchanged `origin_match(..., "current_session")`; no fallback widening | Very low |
| Repeated cancellation creates multiple commands/races | Medium | Medium | High | Concurrent/idempotency tests | One atomic marker/command identity under existing lock/control tree | Low |
| Foreground steering is accidentally advertised/accepted | Low | Medium trust issue | High | Schema and handler negative tests | Keep `_write_control_command` TUI-only for steer; update cancel separately | Very low |
| Background TUI controls regress due to shared cancellation changes | Medium | High for existing users | High | Existing TUI steer/cancel suite plus live bounded smoke | Branch by transport/background; preserve current command/ack code path | Low |
| Output caps/truncation regress during loop rewrite | Medium | High memory/context risk | High | Existing cap tests, noisy child stress, diagnostic-tail assertions | Leave cap helpers unchanged; refactor loop minimally | Low |
| Result parsing/recovery behavior regresses | Low–Medium because finalization is nearby | High: false failures/success | High | Full parser/reliability suite and custom JSON/Markdown fixtures | Do not rewrite parser; map new stop reasons before parsing | Low |
| Child failure is confused with infrastructure failure | Medium | Medium–High | High | Nonzero-exit and child-reported failed result tests | Preserve current execution/task/contract separation | Low |
| Duplicate guard returns a stale foreground `running` artifact | Existing unrelated risk | Medium | High | Baseline inventory and existing duplicate tests | Do not broaden this repair into reconciliation; document separately unless directly blocking acceptance | Medium residual; explicitly out of synchronous lifecycle scope |
| Direct test environment cannot import Hermes helpers | High if imported eagerly | Medium: suite/distribution break | High | Run tests with and without `PYTHONPATH=/opt/hermes` | Defensive lazy resolver/no-op fallback; injection seam | Very low |
| Provider/tool schema rejects guidance change | Low | High live break | High | `scripts/validate_release.py` plus fresh real-provider schema smoke before activation | Text-only compatible schema edits; no unsupported JSON Schema features | Very low |
| Execution mode becomes silently enforced | Low but explicitly forbidden | High behavior regression | High | Handler tests for both modes and source review for auto-conversion/rejection | Documentation only; no decision logic change | Very low |
| Linux-specific process-group behavior is assumed portable | Medium if cross-platform claimed | Medium | High | Confirm declared platform support and run POSIX tests; avoid unsupported claims | Document POSIX/Linux semantics; guard unavailable APIs fail-closed | Medium on non-POSIX unless separately implemented/tested |
| Activation reloads code while a run is active | Medium operationally | Critical | High | Repeat T0 gate immediately before activation | Explicit operator approval; no-active-run hard gate; no image rebuild | Very low if gate followed |
| Smoke test itself leaves descendants | Low–Medium | High | High | Fixture writes identities; cleanup verified in `finally`; post-smoke process scan | Bounded isolated children, process-group cleanup, stop on uncertainty | Low |

---

# Stop/reassessment triggers

Stop implementation and reassess rather than widening scope if any of these occurs:

1. A delegation is verified live or process identity is unverifiable.
2. Baseline full suite fails beyond known/documented state.
3. The fix requires editing `/opt/hermes` or changing gateway timeout configuration.
4. Exact-origin cancellation cannot be added without weakening current ownership checks.
5. Reliable descendant cleanup requires signalling a PID/process group not owned by the synchronous `Popen` flow.
6. More than three materially different lifecycle fix attempts fail.
7. Background TUI, result parsing, duplicate protection, approval policy, or notification tests regress and the repair is not local.
8. A proposed status design requires a new message bus, outbox, or multi-file transaction protocol.
9. Pre-existing dirty hunks cannot be separated confidently from repair hunks.

# Residual uncertainty

- The incident artifact is stale/ambiguous from status alone; exact surviving process state must be assessed immediately before execution, not inferred from this plan.
- POSIX process groups cannot guarantee termination of a malicious or deliberately daemonized descendant that creates a new session. The controlled Hermes/Reviewer/MCP hierarchy should remain in the inherited group, and smoke evidence must verify that actual shape.
- Atomic replacement protects each JSON file independently, not `status.json` and `result.json` as one transaction. The accepted plugin boundary rejects a heavier transaction protocol; fail-closed ordering and recovery evidence are the proportional mitigation.
- Hermes' thread-local callback/interrupt APIs are inspected from the current runtime. Compatibility depends on those public helper contracts remaining available; defensive imports preserve standalone tests but cannot manufacture gateway propagation if Hermes changes its executor contract later.
- Historical stale `running` artifacts and duplicate reconciliation are real operational debt but should not be folded into this repair unless they directly prevent correct acceptance. Scope creep here would be reliability cosplay.

# Deliverable evidence after execution

The implementation handoff must include:

- verified root cause against current source;
- exact changed files and separation from pre-existing dirty work;
- focused and full test commands/results;
- process identity proof that interrupt/cancel/timeout leave no child or grandchild;
- callback timestamp proof that quiet foreground work remains active past a simulated inactivity boundary and stops at terminal state;
- status/result artifacts for completed, failed, timed-out, interrupted, and exact-origin-cancelled cases;
- proof both execution modes remain accepted and advisory only;
- operator-approved activation steps, restart-count evidence, and rollback artifact/hash;
- concrete residual risks without claiming exactly-once state or universal descendant control.
