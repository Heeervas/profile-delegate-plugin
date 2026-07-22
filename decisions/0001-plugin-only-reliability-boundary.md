# 0001 — Plugin-only reliability boundary

Date: 2026-07-22
Status: accepted

## Context

Detached completion notifications and child output-contract drift were initially framed as possible durable-delivery, compression-lineage, and strict-envelope problems. Early proposals introduced a plugin-owned SQLite outbox, gateway reconciliation, completion manifests, or Hermes-core routing changes.

Historical evidence showed that delegated work and artifacts were normally preserved. The primary regression was conflating execution completion, task outcome, contract quality, and notification availability.

## Decision

Keep this remediation plugin-only and model outcomes independently:

1. execution lifecycle;
2. task status;
3. contract quality;
4. notification state;
5. transport state.

Use tolerant deterministic parsing, conservative recovery, durable local run artifacts, and honest best-effort notification labels. Wrapper success remains strict.

## Rejected alternatives

- Hermes-core routing or compression-lineage patches.
- Plugin-owned durable message bus or SQLite notification outbox.
- Completion manifest/transaction protocols.
- Exactly-once or guaranteed post-restart notification claims.
- Strict default-envelope validation that rejects caller-requested custom JSON or explicit Markdown/text contracts.

## Consequences

- `profile_delegate_status` and run artifacts remain durable truth.
- A missed notification never means lost execution.
- Useful noncanonical output may be preserved as blocked/unknown/recovered without false success.
- P2 may improve honest best-effort notification semantics.
- P3 transport changes require measured post-fix evidence.
- Stronger cross-restart delivery remains unsupported unless Hermes exposes an appropriate native extension point and a new decision explicitly approves it.

## Evidence

- Accepted plan: `docs/plans/2026-07-22-plugin-only-reliability-reset-p0-p4.md`.
- Reviewer release gate: PASS after adversarial malformed-output and TUI nonzero-exit fixes.
- Regression suite: 303 passing tests before the operating-contract-only retrofit.
