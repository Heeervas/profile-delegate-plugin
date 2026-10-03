# Changelog

All notable changes to Profile Delegate are documented here.

## [Unreleased]

### Changed

- CLI tasks and recovery use native `--query-file`, delivering the full prompt without a model tool call or exposing task text in argv. Named-profile selection and frozen approval remain unchanged.

- Detached CLI supervision keeps the wrapper identity separate from the child transport. Recovery and capacity track the wrapper; cancellation verifies and stops the child process group.

- Native session selection refuses reasoning display commands before RPC; these commands persist display YAML even with session scope.

- Native durable dispatch is registered by the actual worker before profile execution, surviving launcher exit. Startup metadata failures reap the worker before releasing its status lock; duplicate workers and foreign completion origins are refused without replacing existing records. In-process workers preserve the caller home through native context propagation.

- Detached workers own durable completion, including failure; parent watchers only offer matching pending records, and explicit dead-worker repair restores delivery.
- CLI and TUI share child interpreter/approval/bootstrap and environment/reasoning preparation. CLI argv is built once; child environment uses one whitelist and supervision failures reuse the shared result contract.
- CLI and TUI share pure result contracts and terminal enrichment/publication, retaining transport-specific failure and recovery evidence.

- Provider-only TUI creation and TUI resume apply authorized model/provider/reasoning selections through native session-scoped config.set, preserving stored workspace, frozen authority and operator confirmations.

- Installed audit gate now invokes Hermes Python 3.14 directly with frozen native dev tooling and a hash-pinned YAML helper; fail-closed interpreter/closure checks and regressions added. Portable support remains 3.11–3.13. Installed execution/provisioning evidence remains blocked, not implicitly accepted.
- Independent-audit candidate: bounded incremental TUI frames/deadlines and fair stderr draining; CLI journal/spectator phases; same-session recovery preserves resolved format/marker.
- Public scopes/notification/retention/prose docs aligned with authority. Portable/native CI partitions proposed; isolated provisioning/CI and final runtime review pending, not acceptance.
- Detector assertion checks boolean; unused private prune/reconcile schema builders removed, denial handlers/internal retention safety retained.

- Local native approval-source candidate adds `deny|profile|inherit|yolo`, per-target operator selection and frozen snapshots; preserves historical selectors, checks resumed ancestry and decouples hook consent. Activation remains separately authorized.

- Deterministic child environment and request preflight now separate inherited, resolved, and observed capabilities; schema-local validation and provider/session mismatch diagnostics fail before unsafe execution or retry.
- Model-facing status, list, and control enforce exact origin; approval elevation and global maintenance remain operator-only. Same-home nested delegation is refused while cross-home nesting retains the configured depth and shared capacity.
- Detached transport selection records requested/selected/actual modes; interactive remains the auto background default, with explicit simple mode and identity-checked cancellation. Steer ACK acceptance is not delivery proof: unobserved late follow-up fails closed as `steer_outcome_uncertain`.
- Terminal result/status publication and operator dead-worker repair use a verified shared lock and bounded, no-follow artifact reads; notification recovery observes coherent terminal evidence.
- Prose and Markdown terminal verdict handling preserves useful content without promoting ambiguous or contradictory results to success. Bootstrap and startup stages expose bounded non-secret diagnostics.

### Verification

- Added focused regressions for hostile environment, authorization, preflight, publication/repair races, recursion, transport cancellation, notification read safety, prose verdicts, and delayed steer settlement. The remaining test groups protect distinct owner boundaries; see `STATE.md`.
- The default gateway's loaded-tool preflight succeeded after Alberto's restart, and Discord-origin detached interactive run `pd_20260927_183748_ynvczn` completed `ok` with `notification_status=delivered` on status readback. This does not claim parity on named-profile gateways, correlated steer delivery, tag, push, or publication.

## [1.10.0] — 2026-08-24

### Added

- Foreground lifecycle heartbeats through Hermes' thread-local activity callback.
- Exact-origin foreground cancellation through private control markers consumed by the synchronous process owner.
- Bounded foreground lifecycle status including owned worker identity, liveness, deadline, activity, and terminal reason.
- Explicit conservative per-run reconciliation for dead detached workers, with live/legacy fail-closed behavior and artifact preservation.

### Fixed

- Closed all owned TUI subprocess pipes deterministically after bounded reaping, and made the stubborn-process escalation regression wait until its SIGTERM handler is installed.
- Closed the read-only native-ledger SQLite probe explicitly instead of relying on transaction context or garbage collection.
- Kept RPC deadlines authoritative even when the gateway continuously emits immediately available events, preventing event-flood starvation and CPU spin past the caller's timeout.
- Hardened CI with least-privilege permissions, immutable action SHAs, a pinned uv installer/runtime, frozen hash-locked dependencies, a job timeout, and Python 3.11–3.13 coverage matching Hermes' supported interpreter window.
- Correlated locally timed-out TUI RPC calls by exact integer request id so one strictly valid known late `result`/`error` is consumed without weakening handling of id-bearing event hybrids, unknown/type-confused ids, malformed response shapes, duplicate late responses, EOF, or real channel failures.
- Kept native steer rejection (`4010`) and delivery timeout in the control ACK lifecycle instead of converting them into false run-level transport failures.
- Made local cancellation terminally authoritative before native interrupt delivery, exits event polling immediately after acceptance, and uses one absolute cleanup deadline covering control draining, graceful close, TERM/KILL escalation, and reaping; diagnostics remain truthful when interrupt is rejected, late, timed out, or the channel fails.

- Added a non-destructive native-ledger compatibility circuit breaker: required API signatures and minimum `async_delegations` columns are inspected read-only before durable background notification; incompatible Hermes upgrades fail before run creation or database writes.
- Detached `notify_on_complete` now persists through Hermes' native durable async-delegation ledger before execution and on completion, routes by the origin lane `session_key` rather than an expired logical session id, and rehydrates on gateway restart with task-id delivery idempotency.
- Notification state now distinguishes `pending`, live-queue `queued`, gateway-confirmed `delivered`, unroutable/terminal `failed`, and `disabled` without changing execution/task outcomes.
- Parent interruption and foreground cancellation now terminate and reap the owned process group with TERM-then-KILL escalation and finalize as `cancelled`.
- Plugin deadline remains authoritative and finalizes as `timed_out`; cancellation, interruption, and timeout cannot enter transient recovery.
- Terminal lifecycle metadata is immutable, and synchronous selectors/streams are closed on every exit path.
- Explicit Markdown `PASS` verdicts now recover task success conservatively; conflicting or negated verdicts remain unknown.
- Async completion notifications now report execution completion independently from task/contract success, preventing completed Markdown work from being announced as an execution error.

### Verification

- Focused synchronous lifecycle suite covers heartbeat stop conditions, exact-origin authorization, descendant cleanup, timeout/cancel distinction, atomic private status, retry-delay interruption, and advisory execution-mode guidance.
- Full frozen-lock suites pass on isolated Python 3.11, 3.12, and 3.13 environments; the synchronized real-stdio steer regression enqueues control only after event polling begins, then verifies RPC correlation, accepted ACK, terminal event, session close, closed pipes, and direct subprocess reaping.

### Deferred

- Evidence-gated P3 transport simplification and dead-worker reconciliation.
- Remaining P4 run-health reporting and live transport release smokes.

## [1.9.0] — 2026-07-22

### Added

- Explicit `output_mode=auto|json|markdown|text` with deterministic legacy-contract inference and contradiction checks before run allocation.
- Independent `execution_status` and `contract_status` result fields alongside task `status`.
- Deterministic JSON candidate parsing with provenance metadata and conservative recovery for useful prose and Markdown.
- Portable sanitized regression fixtures derived from real delegated runs.
- Complete public lifecycle filters, including cancelling, cancelled, and timed-out runs.
- Minimal agent-managed project contracts: `AGENTS.md`, `BRIEF.md`, `DESIGN.md`, tracked `STATE.md`/`TODO.md`, `.agents/`, `.hermes/`, and decision records.

### Changed

- Wrapper success now requires completed execution, task status `ok`, acceptable contract status, and no parse error.
- Blocked, unknown, malformed, ambiguous, cancelled, timed-out, transport-failed, and nonzero-exit results remain non-successful without discarding useful output.
- Fenced or warning-prefixed JSON is marked recovered and retains the raw-output artifact path.
- TUI process exit is authoritative even after an apparent successful `message.complete` event.
- README and CI validation now reflect the complete plugin surface.

### Fixed

- Prevented malformed/truncated JSON plus textual `OK` from becoming false success.
- Prevented nested, multiple, equal-score, conflicting, negated, or late terminal statuses from becoming false success.
- Corrected execution/contract state parity across CLI, detached worker, timeout, cancellation, approval timeout, integrity failure, and TUI transport paths.
- Removed dependency on mutable runtime artifacts from regression tests.
- Marked superseded durable-outbox/Hermes-core plans and audits as historical, rejected decision records.

### Verification

- Final independent Reviewer re-review: PASS.
- Full suite: 303 passing tests after the operating-contract retrofit.
- Ruff, Python compilation, YAML parsing, release registration/handler smoke, secret scan, and diff checks passed.

## [1.8.0] — 2026-07-21

### Added

- Persistent TUI Gateway JSON-RPC stdio workers for background delegation.
- `profile_delegate_steer` and `profile_delegate_cancel` native controls.
- Read-only spectator watch/inspect CLI with bounded sanitized event output.
- Capability presets, explicit child approval modes, effective policy inspection, duplicate protection, and origin-scoped run inspection.
- Same-session transient recovery and lifecycle-safe run artifacts.

### Security

- Exact-origin authorization, private control inboxes, bounded event handling, deterministic child approval policy, and verified process cleanup.

## [1.7.0]

- Previous stable release baseline before persistent TUI/live-control work.
