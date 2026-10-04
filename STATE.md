# Profile Delegate — current public state

## Checkpoint and authority

- Version remains **1.10.0**; no new tag or activation is implied.
- Public source baseline: `9089f86d24346791aba01bdfe0f28779212dac45`.
- Baseline CI: [run 37204513835](https://github.com/Heeervas/profile-delegate-plugin/actions/runs/37204513835), portable Python 3.11/3.12/3.13 and installed integration on pinned Hermes/Python 3.14 passed (controller-provided exact-SHA evidence).
- Current authority: **complete-target housekeeping only** — test/document relocation, governance reconciliation, validation and reviewed local commit. Product logic, Hermes/core/profile configuration, activation, tags and publication are excluded. Parent owns subsequent push and exact-candidate CI readback.
- Separate unpublished implementation work must be coordinated with the maintainer; it is not part of this checkout or evidence of shipped behavior.

## Layout and validation

Runtime Python stays at the plugin root for discovery. All test modules and pytest fixtures live in `tests/`; historical sanitized outputs remain in `tests/fixtures/profile_delegate/`. Shared test helpers remain in their existing test modules to preserve import and scenario boundaries.

Canonical commands: [.agents/validation.md](.agents/validation.md). Housekeeping scope, path map and gate receipt: [review evidence](docs/reviews/2026-10-04-housekeeping.md).

Housekeeping validation retains all **716** ordered collected cases; portable
**234** and native **482** partitions pass, serial full **716** passes after one
retained existing cancel timing failure. Independent scoped review found no
behavior blocker. Deterministic quality remains **QUALITY_FAIL**: the external
collector maps edited relocations as additions in all/index/committed scopes;
no policy/baseline waiver or publication acceptance is claimed. Parent owns this
measurement gate and exact-candidate CI before pushing.

## Remaining work

The public repairs isolated preflight/native fixtures (`6cd0434`) and fixed inherited managed-scope admission (`9089f86`). They did **not** resolve:

1. Contradictory recognized JSON task statuses with unequal candidate scores.
2. Blocking RPC write/flush before response deadline accounting.
3. Independent per-chunk UTF-8 decoding in CLI capture/diagnostic tails.

See [TODO.md](TODO.md) and [contribution opportunities](docs/contribution-opportunities.md) for evidence boundaries and coordination. These are opportunities, not tickets or authority to implement them in this task. Green CI is not universal runtime reliability or provider/platform acceptance.

## Boundaries and continuity

Profiles are context boundaries, not OS sandboxes. Execution/task/contract/notification/transport remain independent; native notification is best effort, not exactly-once or guaranteed after restart. Real-provider, gateway-loaded, Discord delivery and operator acceptance remain separate from fixture/native dependency tests.

Historical state and contradictory intermediate acceptance/permission claims are preserved in [state archive](docs/archive/state-through-9089f86.md) and [handoff archive](docs/archive/hermes-handoff-through-9089f86.md), not current instructions. Plan status/navigation lives in [docs/README.md](docs/README.md); durable architectural decisions remain in `decisions/`. `.hermes/` is a thin navigation adapter.

Next: parent verifies the reviewed housekeeping commit, pushes if satisfied and reads back CI on that exact SHA. No restart is needed for documentation/test organization; this session does not alter the loaded runtime.
