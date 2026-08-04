# Profile Delegate project state

Last updated: 2026-08-04 by Adán
Status: durable detached notification repair validated; activation and visual delivery smoke pending

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
- Conservative explicit dead-worker reconciliation preserves evidence, protects live/unverifiable workers, and remains separate from prune.
- Explicit Markdown `PASS` results recover task success; async notifications now reflect execution lifecycle rather than wrapper success.
- Detached completion delivery is persisted through Hermes' native async-delegation ledger, lane-routed across logical-session reset/expiry, restored by Hermes after gateway restart, and idempotent by Profile Delegate task id.
- Durable notification has an automatic read-only compatibility gate. Incompatible Hermes API/schema changes fail before run creation or database mutation; foreground and explicit `notify_on_complete=false` execution remain available.

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

- 2026-08-04: full release gate passed with 361 tests; Ruff, compilation, registration/handler smoke, diff check, and live read-only native-ledger compatibility probe passed.
- Real detached process smoke `pd_20260804_071319_ksvge5`: dispatcher exited before child completion; terminal result persisted with the exact Discord thread lane, `parent_session_id=null`, stable task-id delivery identity, `delivery_state=pending`, and zero attempts. The child itself failed because the isolated smoke shell lacked OpenAI credentials, so this certifies detached durable handoff—not successful model execution or visual platform delivery.
- Focused reconciliation/Markdown/notification regressions passed, including sanitized real-run fixtures and adversarial review cases.
- Full release gate: 351 tests passed; Ruff, Python compilation, registration/handler smoke, and `git diff --check` passed.
- Independent review found no release blocker after its Markdown ambiguity and artifact/ack validation findings were fixed.
- Live gateway processes still require restart/reload before this code and schema guidance become active; no restart is authorized in this task.

## Next action

Commit/push only if requested, then obtain operator approval before any activation restart, live reconcile, prune, or acceptance smoke.

## Known limitations

- Platform delivery is at-least-once under crash ambiguity; status/result artifacts and Hermes' delivery ledger are durable truth.
- P3 transport-mode changes remain evidence-gated.
- Profiles are not OS sandboxes.
- Working tree may include historical plan/audit documents retained as clearly superseded decision history.

## Live handoff

See `.hermes/handoff.md`.