# Handoff

Updated: 2026-08-04

## Current state

The detached notification loss after origin-session expiry/reset is repaired locally. Profile Delegate now registers and completes notifications in Hermes' native durable async-delegation ledger, deliberately omits the expiring logical parent session id, routes by the durable Discord/Telegram lane key, relies on Hermes' existing boot restoration, and uses the Profile Delegate task id for delivery idempotency.

An automatic compatibility circuit breaker checks required native API signatures and the minimum ledger schema through a read-only SQLite connection before each durable-notification run. It never initializes or migrates `state.db`; incompatibility fails with `native_async_ledger_incompatible` before creating run artifacts or writing native state.

## Remaining release steps

1. Restart/reload from outside the running gateway; the gateway correctly blocks self-restart commands issued through its own tool process.
2. After activation, run one credentialed detached task that outlives `/new` and confirm the user-visible Discord delivery plus durable `delivered` state.
3. Commit the intentional lifecycle files; do not push unless explicitly requested.

## Deferred product work

See `TODO.md` for P2–P4. P3 remains evidence-gated; do not implement it from architecture preference alone.

## Hard boundary

No Hermes-core patches, plugin-owned durable outbox/message bus, compression-lineage router, or guaranteed post-restart delivery claim.