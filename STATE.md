# Profile Delegate project state

Last updated: 2026-07-22 by Adán
Status: release candidate verified and independently approved; awaiting commit/push and remote CI

## Active objective

Ship the plugin-only reliability reset and minimal agent-managed project operating contract as the next Profile Delegate release, without reviving rejected Hermes-core, outbox, or lineage machinery.

## Implementation status

- Current phase: release preparation
- Active plan: `docs/plans/2026-07-22-plugin-only-reliability-reset-p0-p4.md`
- Branch: `main`
- P0/P1: implemented and independently approved
- P2–P4: intentionally deferred in `TODO.md`
- Working tree: release changes pending commit/push

## Delivered behavior in this release

- Independent execution/task/contract outcome model.
- Deterministic `auto|json|markdown|text` serialization modes.
- Conservative parsing/recovery that rejects ambiguous, malformed, nested, conflicting, or negated false-success cases.
- Authoritative CLI/TUI timeout, cancellation, transport, and nonzero-exit semantics.
- Portable sanitized historical regression fixtures.
- Public lifecycle/schema parity and updated operator documentation.
- Historical durable-delivery/outbox plans marked rejected or superseded.
- Minimal tracked agent-managed project contracts.

## Blockers

- No release blockers remain.
- Loaded gateway processes require restart/reload after push before the new code/schema is live.

## Skill route

- Routing contract: `.agents/skill-routing.md`
- Freshness: reviewed 2026-07-22
- Execution primary: `hermes-plugin-tool-authoring`
- Supporting: `test-driven-development`, `requesting-code-review`

## Generated runtime adapters

| Runtime | Adapter path | Status | Source | Notes |
|---|---|---|---|---|
| Hermes | `.hermes/` | tracked | `.agents/` | Minimal navigation, validation pointer, landmarks, and handoff only. |

## Latest validation result

- Full pytest: 303 passed after the operating-contract retrofit.
- Ruff, Python compilation, YAML parse, `git diff --check`, secret scan, and release registration/handler smoke: passed.
- Final independent Reviewer re-review: PASS after CI dependency and state-contract corrections.

## Next action

Inspect the staged diff, commit, push `main`, verify remote/CI, then publish the prepared Discord update message.

## Known limitations

- Notifications are best-effort; status/result artifacts are durable truth.
- P3 transport-mode changes remain evidence-gated.
- Profiles are not OS sandboxes.
- Working tree may include historical plan/audit documents retained as clearly superseded decision history.

## Live handoff

See `.hermes/handoff.md`.