# Profile Delegate TODO

Canonical design: [`docs/plans/2026-07-22-plugin-only-reliability-reset-p0-p4.md`](docs/plans/2026-07-22-plugin-only-reliability-reset-p0-p4.md)

Current review: [`docs/audits/2026-09-27-multi-pov-reliability-review.md`](docs/audits/2026-09-27-multi-pov-reliability-review.md)

## 2026-09-27 local F/G acceptance follow-up

- [x] Add request-admission tests for top-level self-target, nested cross-home, nested same-home refusal, configured shared lock capacity and depth.
- [x] Run frozen full `-W error` suite, lock/sync, Ruff, compilation, registration/release and diff checks; vary hash seeds for concurrency/control races. Evidence in `STATE.md`.
- [x] Retry isolated real-provider steer only after genuine TUI agent/turn readiness: `pd_20260927_172745_1tdxyn` observed `tool.start` before queued steer and final `READY_STEER_APPLIED`; delivery state remains unknown. Earlier pre-ready rejection `pd_20260927_172249_j0j50h` is not uptake proof.
- [x] Verify actual process reaping/identity after isolated cancel: recorded worker/transport PIDs 56515/56517 absent from `/proc`, transport closed. Subsequent default-gateway Discord-origin notification/status readback passed (`pd_20260927_183748_ynvczn`).
- [x] Consolidated independent diff review found a late-follow-up false-success blocker; focused correction independently re-reviewed PASS. Alberto restarted the default gateway; loaded-tool preflight and one Discord-origin detached completion/notification/status readback passed (`pd_20260927_183748_ynvczn`). Named-profile parity and formal correlated steer delivery remain unverified. No tag, push, or publication.

## 2026-09-27 reliability roadmap

### v1.11 — Deterministic execution and honest introspection

- [ ] Replace broad child `os.environ.copy()` semantics with an allowlisted or fully scrubbed Hermes execution environment; preserve only documented host credentials/proxy inputs and record non-secret provenance.
- [ ] Represent capabilities as inherit/override/preset with requested, resolved, and observed values; stop calling unresolved empty arrays effective.
- [ ] Make session input a discriminated contract: `new` forbids `session_id`; `resume` requires it.
- [ ] Validate schema-local fields before Hermes config/plugin imports and add a real plugin-loader installation smoke.
- [ ] Classify provider/session realm mismatch separately with actionable non-retry guidance.
- [ ] Disambiguate lookup, execution, task, contract, notification, transport, and task-success fields.
- [ ] Add hostile-parent-environment regressions for toolsets, skills, turn limits, managed scope, model, and provider overlays.

### v1.12 — Steer-first interactive transport

- [ ] Implement and persist/fingerprint `transport_mode=auto|simple|interactive`.
- [ ] Keep background/live-steerable delegation interactive by default; allow simple only when explicitly requested or when interactive bootstrap fails before prompt acceptance.
- [ ] Port the native subagent steering contract: exact owner session/transport/generation authority, lock-linearized `accepting_steer`, queue acceptance distinct from delivery, and terminal `missed_steer` evidence.
- [ ] Persist bounded steering lifecycle evidence: request/accept/deliver/miss timestamps, state, and text hash; never claim `delivered` from a `queued` ACK.
- [ ] Define simple-transport cancellation and explicit no-steer behavior before launch; never switch transports after prompt or ambiguous acceptance.
- [ ] Measure CLI/TUI startup latency, RSS, completion, cancellation, and notification behavior before release.

### v1.13 — Schema v2 and request preflight

- [ ] Add request-specific preflight returning normalized input, resolved target-profile capabilities, all conflicts, and a complete retry payload without creating a run.
- [ ] Replace coupled flat controls with versioned discriminated session/execution/capability/authority objects; retain a compatibility adapter.
- [ ] Remove provider-facing JSON Schema defaults from conditionally inherited fields.
- [ ] Use a structured terminal envelope for JSON, Markdown, and text content so transport completion cannot erase task outcome.
- [ ] Replace the advanced primary README example with a minimal inheriting call.

### v1.14 — Authorization and delegation graph

- [ ] Centralize action authorization; exact-origin model access by default for status/control/continue/reconcile.
- [ ] Restrict global list/reconcile/prune to operator CLI or explicit non-model policy.
- [ ] Disable model-callable approval elevation by default; design immutable run-bound operator grants before exposing `approve_yolo` again.
- [ ] Persist root task, parent task, caller/target profile, depth, and resolved home identity.
- [ ] Initially reject same-home recursive delegation explicitly; add lineage-aware permits only if a measured use case justifies recursion.

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
- [x] Architecture decision revised after inspecting Hermes' native subagent harness: preserve TUI/interactive as the normal background path because steer is a core capability. Target `transport_mode=auto|simple|interactive`; `auto` prefers interactive for background/live-steerable runs and may fall back to simple only before prompt acceptance.
- [ ] Add validation, persistence, fingerprinting, native-compatible steering lifecycle (`accepting_steer`, queued vs delivered, `missed_steer`), and transport-selection cancellation semantics. Explicit dead-worker reconciliation remains independent and does not change transport defaults.

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

Native approval-source milestone completed locally: `docs/plans/2026-10-01-native-approval-modes/ACCEPTANCE.md`. No implementation TODO remains for this bounded scope; activation requires Alberto's separate decision. Incoming unrelated TODOs remain unchanged.

- No Hermes-core patches.
- No plugin-owned durable message bus/outbox.
- No compression-lineage router.
- No exactly-once or guaranteed post-restart notification claim.
