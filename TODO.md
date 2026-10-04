# Profile Delegate backlog

This is unresolved public-checkout work, not an issue tracker or implementation authorization. Version remains 1.10.0. Coordinate with the maintainer before overlapping unpublished work. [Contribution entry points](docs/contribution-opportunities.md) give reproductions and acceptance criteria.

## Correctness first — reproduce against current main

- [ ] Reject contradictory recognized JSON task statuses **before** unequal-score selection (`contracts.py`; `tests/test_profile_delegate.py`, `tests/test_reliability_reset.py`). Preserve custom output and raw evidence; use existing ambiguity/non-success semantics.
- [ ] Bound RPC dispatch under stdin backpressure with the existing total deadline (`tui_rpc.py`, `tests/test_tui_rpc.py`). Current inspection shows blocking write/flush; a real installed Hermes hang has not been established. Start with a disposable peer/watchdog reproduction.
- [ ] Preserve split UTF-8 in CLI capture and TUI diagnostic tails (`core.py`, `tui_rpc.py`). Keep stream independence, EOF replacement and existing capture/tail/truncation bounds. JSON byte framing is not this defect.

These three findings were not fixed by the CI/preflight fixture repair or managed-scope guard repair. They are plan-only here; no broad audit implementation is authorized by housekeeping.

## Evidence-led follow-up

- [ ] Publish sanitized independent-installation CLI/TUI completion, resume/recovery, cancellation, consumed steering and notification evidence. Use existing opt-in harnesses and operator approval, never frozen-authority bypass. Fixture/native import checks do not establish real provider or platform delivery.
- [ ] Make changed-code quality tooling reproducible for contributors/CI. The policy/schema and local measurement recipe exist; they do not constitute a portable automated quality job. Preserve immutable baseline, approved expiring exception and behavior gates.
- [ ] Propose focused TUI lifecycle simplification only after correctness work; preserve state ownership and safety cases. Historical numerical line/case targets are not test-deletion authority.

## Intentionally deferred design/operations

- [ ] Measure transport failure/startup/control behavior before extending routing policy; see [accepted reliability direction](docs/plans/2026-07-22-plugin-only-reliability-reset-p0-p4.md) and [later steer-first plan](docs/plans/2026-09-27-reliability-and-steer-first-implementation.md). Existing transport selection must not be mistaken for an entirely unimplemented feature.
- [ ] Consider compact run-health reporting across independent execution/task/contract/notification/transport outcomes.
- [ ] Agree on retention policy only with explicit operator approval; reconciliation and destructive retention remain separate. No public prune tool/CLI is registered.
- [ ] Revisit native preview API/installation packaging only when Hermes supplies an applicable supported surface.

## Closed items — do not reopen as missing features

Native prerequisite/3.14 CI partition, frozen portable matrix, preflight admission fixture isolation, obsolete compile target removal and managed-scope regression repair are already present. Policy/preflight, deterministic environment admission, explicit session discrimination, origin-scoped tools, approval snapshots, nested lineage, same-session recovery, operator reconciliation and steering uncertainty/receipts already have implementation and tests; historical roadmap checkboxes are not proof they remain absent.

Historical plans/reviews and completed-work provenance are indexed in [docs/README.md](docs/README.md). No phantom issue numbers, new version promises, Hermes-core patch, outbox, sandbox or guaranteed-delivery claim is introduced.
