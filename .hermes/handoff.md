# Handoff

Updated: 2026-07-24

## Current state

The synchronous foreground lifecycle repair is implemented locally on top of the committed P0/P1 and nested-delegation baseline. It adds activity propagation, thread-local interrupt polling, exact-origin foreground cancellation markers, TERM-then-KILL process-group cleanup, bounded truthful status, and terminal-state protection. The final independent review passed; the latest full local gate passed with 324 tests.

## Remaining release steps

1. Commit the intentional lifecycle files; do not push unless explicitly requested.
2. Before activation, verify no delegation is active and preserve the current plugin as a rollback target.
3. Restart/reload only with explicit operator approval, then run bounded foreground/background acceptance smokes.

## Deferred product work

See `TODO.md` for P2–P4. P3 remains evidence-gated; do not implement it from architecture preference alone.

## Hard boundary

No Hermes-core patches, plugin-owned durable outbox/message bus, compression-lineage router, or guaranteed post-restart delivery claim.