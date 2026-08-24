# Profile Delegate TODO

Canonical design: [`docs/plans/2026-07-22-plugin-only-reliability-reset-p0-p4.md`](docs/plans/2026-07-22-plugin-only-reliability-reset-p0-p4.md)

## Completed release gate

- [x] P0 — Separate execution, task, and contract outcomes; prevent false success.
- [x] P1 — Deterministic `auto|json|markdown|text` output handling and recovery.
- [x] Portable real-run regression fixtures, lifecycle/schema alignment, docs, and adversarial CLI/TUI tests completed as part of the P0/P1 gate.
- [x] Independent Reviewer verdict: PASS; full suite: 303 passed.

## Deferred intentionally

### Maintenance follow-up

- [x] Close the historical `profile_delegate_status` task-ID rejection: current create/list/status formats are aligned, emitted suffixes fit the accepted 6–12 lowercase-alphanumeric form, and the regression suite covers listed IDs.

Historical observation: `pd_20260627_143510_na5ck4` was listed but status lookup reportedly returned `invalid task_id format`. Expected behavior is that every ID emitted/listed by the plugin is accepted by status lookup.

### P2 — Honest durable notifications

- [x] Model notification state independently from execution/task state.
- [x] Persist dispatch/completion through Hermes' native async-delegation ledger and rehydrate across gateway restart.
- [x] Project legacy notification states without rewriting old artifacts.
- [x] Preserve execution/task results independently from notification availability.
- [x] Gate durable notification on a read-only native API/schema compatibility probe.

Implemented without a plugin-owned outbox; Hermes remains the durable delivery owner.

### P3 — Simpler background transport

- [ ] Collect post-repair failure-rate and startup-latency evidence by transport; the 2026-08-24 incident is one strong data point, not a complete rollout sample.
- [x] Architecture decision: preserve TUI for native cross-process steer/cancel, but do not require it for every run. Target `transport_mode=auto|simple|interactive`, where `auto` uses simple CLI unless interactive control is explicitly requested.
- [ ] If justified, add validation, persistence, fingerprinting, and transport-selection cancellation/steer semantics. Explicit dead-worker reconciliation is implemented independently and does not change transport defaults.

Hermes' native `delegate_task(action=list|steer|stop)` is the reference control-plane design for ownership and lineage, but not a replacement: it is an in-process same-profile registry, while Profile Delegate owns cross-profile process isolation, resumable profile sessions, approval policy, durable artifacts, reconciliation, and notification state.

**Do not start from theory alone:** this changes execution routing and should be evidence-led.

### P4 — Remaining observability and release work

Already absorbed into P0/P1: portable fixtures, README/schema alignment, lifecycle filters, parser cleanup, rejected-plan banners, parity and wrapper-success tests.

- [ ] Add compact run-health reporting by execution/task/contract/notification/transport state.
- [ ] Add legacy artifact compatibility projectors only when the next schema change is actually required.
- [x] Run real detached execution and interactive steer/cancel smokes for the TUI transport release.
- [ ] Decide and approve a retention schedule only after reviewing unresolved legacy runs; keep prune separate from reconciliation.
- [x] Complete bounded independent re-reviews of the final functional diff: concurrency/lifecycle PASS, API/compatibility PASS, and security/release PASS_WITH_RESIDUAL_RISK.
- [x] Close the remaining low CI supply-chain residual with `uv.lock`, frozen installs, artifact hashes, immutable action revisions, and a pinned uv runtime; verify the same lock in isolated Python 3.11–3.13 suites.

## Explicit non-goals

- No Hermes-core patches.
- No plugin-owned durable message bus/outbox.
- No compression-lineage router.
- No exactly-once or guaranteed post-restart notification claim.
