# Native simplification — final local candidate evidence

Production candidate: `79427bc`. Documentation commits after it do not change executable code. Functional release remains v1.10.0; this is an unactivated local candidate. The Codex goal remains active because the full acceptance criteria below are pending.

## Exact scope and measurements

All tracked Python files are counted: root production including `cli_smoke.py`, root `test_*.py`, and support including `conftest.py`, scripts and fixture helpers. Movement between modules does not count as reduction. Physical lines use `splitlines()`; nonblank/noncomment excludes blank and comment-only lines using Python tokenization and retains docstrings. Metrics cover the same paths/rules at all revisions; no `.artifacts` were tracked at either baseline.

| Scope | Historical `a579142` physical / substantive | Initial `5ddc731` physical / substantive | Candidate physical / substantive |
| --- | ---: | ---: | ---: |
| Production (13 files) | 7643 / 6787 | 7658 / 6799 | 7252 / 6379 |
| Tests (27 files) | 7948 / 6759 | 8006 / 6808 | 8011 / 6807 |
| Support (historical 5; initial/current 6 files) | 698 / 606 | 969 / 839 | 969 / 839 |
| Collected cases | 709 | 712 | 709 |

Production meets <=7253: net -391 physical and -408 substantive versus historical. Tests <=6908 and cases <=654 remain pending: gaps 1103 lines and 55 cases. Support growth predates this refactor and is not excluded. Fifteen redundant cases were retired across the refactor; twelve meaningful selection/delivery regressions were added. Net case count compared with the initial candidate is -3, not -55. [Coverage retirement rationale](2026-10-03-test-retirement.md) identifies each family and surviving assertions. No evidence establishes that another 55 distinct safety cases can be deleted safely; remaining frozen-authority, compression, malformed artifact, native 503 and publication-race cases were retained. Further safe fixture consolidation and coverage review remain open; these numbers do not justify claiming complete acceptance.

Private reproducible receipts: `.artifacts/refactor-20261003/final-line-metrics.json` and `import-benchmark.json`. Counts come from `git ls-tree -r --name-only REV`, retrieving each `.py` with `git show REV:PATH`, applying the three categories above and counting full-line comments with `tokenize.generate_tokens`.

Fresh-process import measurement: Hermes Python 3.14.7, seven samples after one warmup, alternating baseline/candidate order, identical interpreter. Median import of core/TUI/plugin modules: 89.40 -> 79.68 ms; median maximum RSS: 55692 -> 52608 KiB. Baseline `de74498` is the initial architecture plus the first selection fix. No profile execution, provider startup, detached acceptance, Discord delivery or memory under a real workload is inferred from import measurements.

## Canonical gates

From `.agents/validation.md`, final candidate:

- Native full suite, installed Python 3.14.7, `-W error`: **709 passed in 103.35 s**. Integration prerequisites execute against the real installed native closure; no skipped missing-runtime partition.
- Portable partition, frozen plugin Python 3.13: **232 passed / 477 deselected in 6.66 s**. This is interpreter/partition coverage in the existing installed container, not a newly provisioned Hermes-free environment.
- `uv lock --check`, `uv sync --frozen`: pass; lock unchanged.
- Whole-tree frozen Ruff, canonical 21-file compilation, six-tool/CLI registration and validation-error handler smoke: pass.
- Secret scan: `secret_hits=0`; staged/unstaged diff whitespace checks: pass.
- Disk floor: 5.3 GB free. No builds, pushes or gateway restart.

The secret scan's first container invocation encountered Git's ownership protection. Re-run passed with `GIT_CONFIG_COUNT=1`, `GIT_CONFIG_KEY_0=safe.directory`, `GIT_CONFIG_VALUE_0=/opt/data/plugins/profile-delegate` on that single invocation. No persistent Git configuration was written.

## No-YAML boundary

Native model selection always supplies `--session` in addition to live-session RPC scope. The installed resolver returns persistence=false before considering profile defaults. Native effort selection uses only none/minimal/low/medium/high/xhigh/max, a verified session ID and session scope. Native setters are tested with configuration writers replaced by failure traps; model/provider/resume, provider-only creation, effort override and stale session refusal are covered.

An explicit native regression demonstrated that `reasoning=show` reaches `_write_display_sections` -> `_save_cfg` despite session scope. Its writer was trapped: no real file was written. The session starter now refuses display commands before any RPC, in addition to public preflight validation. Native confirmation requirements remain controlled refusals, not automatic approval.

## Pending acceptance

Independent final code and retirement review has not occurred. The accepted plan requires it before operator activation; this session requires an explicit user request before spawning a reviewer agent. Review must include additional safe test reduction and the remaining native API dependency risks.

Real changed-candidate provider/Discord round trip, actual selected child identity, detached completion/control/recovery cleanup and comparable full-startup/async-acceptance performance remain pending. They require the accepted operator-controlled runtime stage after review. No test or historical receipt establishes that the current gateway has loaded this code.

Automatic goal wait/resumption remains pending: [native goal boundary and concrete prior-runtime counterexample](2026-10-03-native-goal-boundary.md). Independent detached execution and silent notification behavior are preserved; no unsupported bridge was installed.
