# Changelog

All notable changes to Profile Delegate are documented here.

## [Unreleased]

### Deferred

- P2 honest best-effort notification semantics.
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
