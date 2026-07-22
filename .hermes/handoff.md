# Handoff

Updated: 2026-07-22

## Current state

P0/P1 reliability implementation, adversarial fixes, and the minimal agent-managed project contracts are complete. The full local gate passed with 303 tests. Final Reviewer re-review passed after correcting the CI dependency and stale state contracts.

## Remaining release steps

1. Stage and inspect the intentional release files.
2. Commit and push to `main`.
3. Verify remote SHA and GitHub Actions.
4. Restart/reload Hermes gateways before claiming live schema/code adoption.

## Deferred product work

See `TODO.md` for P2–P4. P3 remains evidence-gated; do not implement it from architecture preference alone.

## Hard boundary

No Hermes-core patches, plugin-owned durable outbox/message bus, compression-lineage router, or guaranteed post-restart delivery claim.