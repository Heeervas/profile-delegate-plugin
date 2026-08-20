# Handoff

Updated: 2026-08-20

## Current state

The detached notification loss after origin-session expiry/reset is repaired locally. Profile Delegate now registers and completes notifications in Hermes' native durable async-delegation ledger, deliberately omits the expiring logical parent session id, routes by the durable Discord/Telegram lane key, relies on Hermes' existing boot restoration, and uses the Profile Delegate task id for delivery idempotency.

An automatic compatibility circuit breaker checks required native API signatures and the minimum ledger schema through a read-only SQLite connection before each durable-notification run. It never initializes or migrates `state.db`; incompatibility fails with `native_async_ledger_incompatible` before creating run artifacts or writing native state.

The TUI control path now validates exact integer JSON-RPC correlation and strict response shapes across local timeouts, rejects id-bearing event hybrids, reports steer rejection/delivery uncertainty without killing healthy turns, and makes accepted local cancellation terminally authoritative by exiting event polling immediately and reserving the shared five-second deadline for TERM/KILL escalation and confirmed reaping. Two independent reviews found four edge defects in malformed late-response handling, hybrid frame classification, and cleanup budgeting; all are corrected with adversarial and runner-level stubborn-process regressions. The code is not loaded into any running gateway.

The original pre-turn `agent=None` build stall is not fixed here. It reproduced twice for Builder with zero messages/API/tools. The strongest current boundary is unrestricted tool discovery: Reviewer runs using explicit `web,file` built successfully, while Builder's unfiltered build did not reach model-client creation. That is evidence for the next investigation, not a proven root cause.

## Remaining release steps

1. Restart/reload from outside the running gateway only with operator approval; the gateway correctly blocks self-restart commands issued through its own tool process.
2. After activation, run a fresh-process interactive steer/cancel smoke with process-cleanup evidence, plus one credentialed detached task that outlives `/new` and confirms user-visible Discord delivery and durable `delivered` state.
3. Commit/push only if explicitly requested.

## Deferred product work

See `TODO.md` for P2–P4. P3 remains evidence-gated; do not implement it from architecture preference alone.

## Hard boundary

No Hermes-core patches, plugin-owned durable outbox/message bus, compression-lineage router, or guaranteed post-restart delivery claim.