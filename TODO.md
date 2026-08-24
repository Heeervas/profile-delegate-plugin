# Profile Delegate TODO

Canonical design: [`docs/plans/2026-07-22-plugin-only-reliability-reset-p0-p4.md`](docs/plans/2026-07-22-plugin-only-reliability-reset-p0-p4.md)

## Completed release gate

- [x] P0 — Separate execution, task, and contract outcomes; prevent false success.
- [x] P1 — Deterministic `auto|json|markdown|text` output handling and recovery.
- [x] Portable real-run regression fixtures, lifecycle/schema alignment, docs, and adversarial CLI/TUI tests completed as part of the P0/P1 gate.
- [x] Independent Reviewer verdict: PASS; full suite: 303 passed.

## Deferred intentionally

### Maintenance follow-up

- [ ] Reproduce the historical `profile_delegate_status` task-ID rejection against the current shared validator. Current create/list/status regexes appear aligned and emitted suffixes fit the accepted 6–12 lowercase-alphanumeric form; close this item if a fresh regression cannot reproduce it.

Historical observation: `pd_20260627_143510_na5ck4` was listed but status lookup reportedly returned `invalid task_id format`. Expected behavior is that every ID emitted/listed by the plugin is accepted by status lookup.

### P2 — Honest best-effort notifications

- [ ] Model notification state independently from execution/task state.
- [ ] Persist completion before queue attempts; bounded retry only while parent is alive.
- [ ] Project legacy notification states without rewriting old artifacts.
- [ ] Make status output lead with result preservation when notification is unavailable.
- [ ] Document that guaranteed delivery across gateway restart is unsupported plugin-only.

**Start gate:** preserve the reviewed P0/P1 baseline in the v1.9 release commit before beginning this slice.

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
- [ ] Run real simple sync, detached background, and interactive steer/cancel smokes for the relevant transport release.
- [ ] Decide and approve a retention schedule only after reviewing unresolved legacy runs; keep prune separate from reconciliation.
- [ ] Re-review each shipped slice independently.

## Explicit non-goals

- No Hermes-core patches.
- No plugin-owned durable message bus/outbox.
- No compression-lineage router.
- No exactly-once or guaranteed post-restart notification claim.
