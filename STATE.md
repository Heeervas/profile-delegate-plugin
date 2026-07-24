# Profile Delegate project state

Last updated: 2026-07-24 by Adán
Status: synchronous lifecycle repair independently approved; commit pending

## Active objective

Ship the plugin-only reliability reset and minimal agent-managed project operating contract as the next Profile Delegate release, without reviving rejected Hermes-core, outbox, or lineage machinery.

## Implementation status

- Current phase: lifecycle repair validation
- Active plan: `docs/plans/2026-07-24-sync-lifecycle-heartbeat-cancellation.md`
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
- Direct nested `profile_delegate` runs are linked to their parent and surfaced under `result.nested_delegations`, allowing controllers to reuse child-performed reviews instead of repeating them.
- Foreground subprocesses propagate bounded parent activity, consume Hermes interruption state and exact-origin cancellation markers, terminate/reap their complete owned process group, and publish truthful bounded lifecycle status.
- Historical durable-delivery/outbox plans marked rejected or superseded.
- Minimal tracked agent-managed project contracts.

## Blockers

- No code/test review blockers remain.
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

- Full pytest: 324 passed after synchronous lifecycle repair.
- Ruff, Python compilation, `git diff --check`, and release registration/handler smoke: passed.
- Live gateway processes still require restart/reload before this code and schema guidance become active.

## Next action

Resolve final review findings, rerun the release gate, commit the lifecycle repair, then request operator approval before any activation restart or live acceptance smoke.

## Known limitations

- Notifications are best-effort; status/result artifacts are durable truth.
- P3 transport-mode changes remain evidence-gated.
- Profiles are not OS sandboxes.
- Working tree may include historical plan/audit documents retained as clearly superseded decision history.

## Live handoff

See `.hermes/handoff.md`.