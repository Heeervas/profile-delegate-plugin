# Profile Delegate backlog

This is unresolved public-checkout work, not an issue tracker or implementation authorization. Current source version: 1.12.0. Coordinate with the maintainer before overlapping unpublished work. [Contribution entry points](docs/contribution-opportunities.md) give reproductions and acceptance criteria.

## Correctness first — reproduce against current main

- [x] Reject contradictory recognized JSON statuses before unequal-score selection.
- [x] Bound RPC dispatch under stdin backpressure with the total deadline.
- [x] Preserve split UTF-8 in CLI capture and TUI diagnostic tails.

These fixes and their regression tests are included in the integrated 1.12 source;
they no longer represent open housekeeping proposals.

## Lifecycle residual risk

- [ ] Reconcile an exceptional background reaper `process.wait()` failure.
  The permit remains held unless exit is confirmed; this cannot produce false
  success but may strand status/capacity. Add bounded recovery only with focused
  lifecycle evidence, not by releasing capacity while a child may be alive.

## Evidence-led follow-up

- [ ] Publish sanitized independent-installation CLI/TUI completion, resume/recovery, cancellation, consumed steering and notification evidence. Use existing opt-in harnesses and operator approval, never frozen-authority bypass. Fixture/native import checks do not establish real provider or platform delivery.
- [x] Make changed-code quality tooling reproducible with hash-locked vendored analyzer and trusted CI. Governance adoption is separate; the first bootstrap quality is intentionally fail-closed. The tooling README's reference to an absent policy describes the earlier adoption design; current remote has policy but lacks the trusted gate. Preserve immutable baseline and both reviewed expiring exceptions.
- [ ] Propose focused TUI lifecycle simplification only after correctness work; preserve state ownership and safety cases. Historical numerical line/case targets are not test-deletion authority.

## Intentionally deferred design/operations

- [ ] Measure transport failure/startup/control behavior before extending routing policy; see [accepted reliability direction](docs/plans/2026-07-22-plugin-only-reliability-reset-p0-p4.md) and [later steer-first plan](docs/plans/2026-09-27-reliability-and-steer-first-implementation.md). Existing transport selection must not be mistaken for an entirely unimplemented feature.
- [ ] Consider compact run-health reporting across independent execution/task/contract/notification/transport outcomes.
- [ ] Agree on retention policy only with explicit operator approval; reconciliation and destructive retention remain separate. No public prune tool/CLI is registered.
- [ ] Revisit native preview API/installation packaging only when Hermes supplies an applicable supported surface.

## Closed items — do not reopen as missing features

Native prerequisite/3.14 CI partition, frozen portable matrix, preflight admission fixture isolation, obsolete compile target removal and managed-scope regression repair are already present. Policy/preflight, deterministic environment admission, explicit session discrimination, origin-scoped tools, approval snapshots, nested lineage, same-session recovery, operator reconciliation and steering uncertainty/receipts already have implementation and tests; historical roadmap checkboxes are not proof they remain absent.

Historical plans/reviews and completed-work provenance are indexed in [docs/README.md](docs/README.md). No phantom issue numbers, new version promises, Hermes-core patch, outbox, sandbox or guaranteed-delivery claim is introduced.
