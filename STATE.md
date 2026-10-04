# Profile Delegate — current public state

## Checkpoint and authority

- Version **1.10.1**: authorized metadata/documentation release, annotated tag after exact-commit CI. No runtime activation is included.
- Public source baseline: `9089f86d24346791aba01bdfe0f28779212dac45`.
- Baseline CI: [run 37204513835](https://github.com/Heeervas/profile-delegate-plugin/actions/runs/37204513835), portable Python 3.11/3.12/3.13 and installed integration on pinned Hermes/Python 3.14 passed (controller-provided exact-SHA evidence).
- Current authority: **1.10.1 release packaging** — README, version metadata, changelog and project-state reconciliation; push and annotated tag explicitly requested. Product logic, Hermes/core/profile configuration and activation remain excluded.
- Separate unpublished implementation work must be coordinated with the maintainer; it is not part of this checkout or evidence of shipped behavior.

## Layout and validation

Runtime Python stays at the plugin root for discovery. All test modules and pytest fixtures live in `tests/`; historical sanitized outputs remain in `tests/fixtures/profile_delegate/`. Shared test helpers remain in their existing test modules to preserve import and scenario boundaries.

Canonical commands: [.agents/validation.md](.agents/validation.md). Housekeeping scope, path map and gate receipt: [review evidence](docs/reviews/2026-10-04-housekeeping.md).

Housekeeping validation retains all **716** ordered collected cases; portable
**234** and native **482** partitions pass, serial full **716** passes after one
retained existing cancel timing failure. Independent scoped review found no
behavior blocker. The unmodified collector reports **QUALITY_FAIL** because its
100%-similarity rename requirement classifies path-adjusted tests as additions.
Controller adjudication using Git-detected renames and baseline/current metrics
confirms no housekeeping-introduced strong finding: the only metric increase is
the already-approved managed-scope regression (1960 → 1965 logical lines).
Thresholds, immutable baseline and existing exception remain unchanged. This is
scoped housekeeping acceptance, not a claim that the raw collector passed.

## Remaining work

The public repairs isolated preflight/native fixtures (`6cd0434`) and fixed inherited managed-scope admission (`9089f86`). They did **not** resolve:

1. Contradictory recognized JSON task statuses with unequal candidate scores.
2. Blocking RPC write/flush before response deadline accounting.
3. Independent per-chunk UTF-8 decoding in CLI capture/diagnostic tails.

See [TODO.md](TODO.md) and [contribution opportunities](docs/contribution-opportunities.md) for evidence boundaries and coordination. These are opportunities, not tickets or authority to implement them in this task. Green CI is not universal runtime reliability or provider/platform acceptance.

## Boundaries and continuity

Profiles are context boundaries, not OS sandboxes. Execution/task/contract/notification/transport remain independent; native notification is best effort, not exactly-once or guaranteed after restart. Real-provider, gateway-loaded, Discord delivery and operator acceptance remain separate from fixture/native dependency tests.

Historical state and contradictory intermediate acceptance/permission claims are preserved in [state archive](docs/archive/state-through-9089f86.md) and [handoff archive](docs/archive/hermes-handoff-through-9089f86.md), not current instructions. Plan status/navigation lives in [docs/README.md](docs/README.md); durable architectural decisions remain in `decisions/`. `.hermes/` is a thin navigation adapter.

Housekeeping was published at `10d131a604e068bf75b9e72873d1faed52fdc3b8`; exact-SHA CI [37208686318](https://github.com/Heeervas/profile-delegate-plugin/actions/runs/37208686318) passed all four jobs. Next: validate and push 1.10.1 packaging, verify exact-commit CI, then publish the annotated tag. No restart or loaded-runtime change is included.
