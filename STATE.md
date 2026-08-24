# Profile Delegate project state

Last updated: 2026-08-24 by Adán
Status: TUI startup deadlock fixed and full execution/steer/cancel smokes passed; gateway restart only needed to reload the optional preview hook

## Active objective

Ship the plugin-only reliability reset and minimal agent-managed project operating contract as the next Profile Delegate release, without reviving rejected Hermes-core, outbox, or lineage machinery.

## Implementation status

- Current phase: lifecycle repair validation
- Active plan: `docs/plans/2026-07-24-sync-lifecycle-heartbeat-cancellation.md`
- Branch: `main`
- P0/P1: implemented and independently approved
- P2–P4: intentionally deferred in `TODO.md`
- Working tree: deadlock repair and validation evidence pending commit/push

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
- TUI RPC calls now retain exact correlation after a local timeout: one strictly valid response for the exact integer id is consumed, while id-bearing event hybrids, type-confused/unknown ids, malformed response shapes, duplicates, EOF, and channel failures remain fatal.
- Steer rejection/timeout is reported through control ACKs without falsely killing a healthy turn, and accepted local cancellation exits event polling immediately and remains terminally authoritative under one five-second deadline covering native interrupt, transport close, TERM/KILL escalation, and reaping.
- Delegated TUI bootstrap completes plugin discovery synchronously before MCP discovery and deferred agent build can race. This removes the plugin-lock/import-lock inversion that stranded Builder prompts until the 600-second agent initialization timeout.
- Profile Delegate's preview hook no longer imports `run_agent` from plugin registration; already-loaded display executors are patched without pulling the agent runtime into discovery.

## Blockers

- No known blocker remains for new delegated runs. Fresh child processes read the repaired bootstrap directly.
- The long-running parent gateway still holds the prior optional display-preview hook until restart; this does not block delegation execution or controls.
- P3 transport selection remains a separate design change, not part of this incident repair.

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

- 2026-08-24: exact all-thread stacks proved a lock inversion: the deferred agent build held the `run_agent` import path while waiting in `discover_plugins`; concurrent MCP discovery held the plugin-manager lock while plugin register hooks imported `run_agent`. Profile Delegate and `self-improvement-orchestrator` both exposed the antipattern. The plugin now serializes discovery before TUI concurrency and avoids its own registration-time runtime import.
- 2026-08-24: full gate passed with 387 tests, Ruff, Python compilation, registration/handler smoke, and `git diff --check`. Fresh Builder execution smoke `pd_20260824_092006_hup3w2` completed in 27.58s with one API call and exact output `PROFILE_DELEGATE_E2E_OK`. Interactive steer smoke `pd_20260824_092143_4gcn7l` accepted the command during a live tool and returned `STEER_APPLIED_OK`. Cancel smoke `pd_20260824_092144_u04e1x` accepted native interrupt and reached authoritative `cancelled` state without false completion.
- 2026-08-20: full release gate passed with 385 tests after resolving two rounds of independent-review blockers: strict late-response validation, id-bearing event hybrids, immediate exit from polling after accepted cancellation, and end-to-end cleanup/reaping under the shared deadline. Ruff, Python compilation, plugin registration/handler smoke, secret scan, and `git diff --check` passed. Final independent re-review returned PASS with no material blocker; fresh-process interactive steer/cancel smoke remains pending activation approval.
- 2026-08-04: full release gate passed with 361 tests; Ruff, compilation, registration/handler smoke, diff check, and live read-only native-ledger compatibility probe passed.
- Real detached process smoke `pd_20260804_071319_ksvge5`: dispatcher exited before child completion; terminal result persisted with the exact Discord thread lane, `parent_session_id=null`, stable task-id delivery identity, `delivery_state=pending`, and zero attempts. The child itself failed because the isolated smoke shell lacked OpenAI credentials, so this certifies detached durable handoff—not successful model execution or visual platform delivery.
- Focused reconciliation/Markdown/notification regressions passed, including sanitized real-run fixtures and adversarial review cases.
- Full release gate: 351 tests passed; Ruff, Python compilation, registration/handler smoke, and `git diff --check` passed.
- Independent review found no release blocker after its Markdown ambiguity and artifact/ack validation findings were fixed.
- Live gateway processes still require restart/reload before this code and schema guidance become active; no restart is authorized in this task.

## Next action

Commit the incident repair when requested. Treat P3 as a separate evidence-led change: `auto` should select CLI for ordinary foreground/background runs and TUI only when interactive control is requested. Obtain operator approval before gateway restart, live reconcile, or prune.

## Known limitations

- Platform delivery is at-least-once under crash ambiguity; status/result artifacts and Hermes' delivery ledger are durable truth.
- P3 transport-mode changes remain evidence-gated.
- Profiles are not OS sandboxes.
- Working tree may include historical plan/audit documents retained as clearly superseded decision history.

## Live handoff

See `.hermes/handoff.md`.