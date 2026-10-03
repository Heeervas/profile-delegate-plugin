# Native simplification — final local candidate evidence

Production candidate: worker-ownership repair following `3fed48e` (superseding `79427bc`). Functional release remains v1.10.0; this is an unactivated local candidate. The Codex goal remains active because the full acceptance criteria below are pending.

## Exact scope and measurements

All tracked Python files are counted: root production including `cli_smoke.py`, root `test_*.py`, and support including `conftest.py`, scripts and fixture helpers. Movement between modules does not count as reduction. Physical lines use `splitlines()`; nonblank/noncomment excludes blank and comment-only lines using Python tokenization and retains docstrings. Metrics cover the same paths/rules at all revisions; no `.artifacts` were tracked at either baseline.

| Scope | Historical `a579142` physical / substantive | Initial `5ddc731` physical / substantive | Candidate physical / substantive |
| --- | ---: | ---: | ---: |
| Production (13 files) | 7643 / 6787 | 7658 / 6799 | 7290 / 6413 |
| Tests (27 files) | 7948 / 6759 | 8006 / 6808 | 8236 / 7015 |
| Support (historical 5; initial/current 6 files) | 698 / 606 | 969 / 839 | 969 / 839 |
| Collected cases | 709 | 712 | 718 |

Production <=7253 remains pending: current gap 37 physical lines after required ownership safety repairs. Tests <=6908 and cases <=654 remain pending: gaps 1328 lines and 64 cases. Support growth predates this refactor and is not excluded. Fifteen redundant cases were retired; twenty-one meaningful selection/delivery/safety regressions were added. Net case count versus initial is +6. [Coverage retirement rationale](2026-10-03-test-retirement.md) identifies retired families and surviving assertions. Independent review found no evidence that another 55 distinct safety cases can be deleted safely. Remaining authority/compression/malformed artifact/native503/publication race cases stay covered; fixture consolidation remains open.

The native worker ownership defect was reproduced against exact `3fed48e`: dispatch owner was the launcher PID; native abandoned recovery terminalized a live detached task. Both process/ledger regressions fail there and pass on this candidate. The actual native SessionDB and detached processes run in a disposable caller home, provider workload is a fixture, and replay goes only to a local test queue. Silent execution creates no native notification row. Reviewer findings on conflict finalization and thread-local home propagation have regression coverage and focal approval; full provider/Discord acceptance remains pending.

Private reproducible receipts: `.artifacts/refactor-20261003/worker-owner-metrics.json` and earlier `import-benchmark.json`. Counts come from `git ls-tree -r --name-only REV`, retrieving each `.py` with `git show REV:PATH`, applying the three categories above and counting full-line comments with `tokenize.generate_tokens`.

Earlier `79427bc` fresh-process import measurement (not the current ownership candidate): Hermes Python 3.14.7, seven samples after one warmup, alternating baseline/candidate order, identical interpreter. Median import of core/TUI/plugin modules: 89.40 -> 79.68 ms; median maximum RSS: 55692 -> 52608 KiB. Baseline `de74498` is the initial architecture plus the first selection fix. No profile execution, provider startup, detached acceptance, Discord delivery or memory under a real workload is inferred from import measurements.

## Canonical gates

From `.agents/validation.md`, final candidate:

- Native full suite, installed Python 3.14.7, `-W error`: **718 passed in 122.81 s**. Integration prerequisites execute against the real installed native closure; no skipped missing-runtime partition.
- Portable partition, frozen plugin Python 3.13: **238 passed / 480 deselected in 7.18 s**. This is interpreter/partition coverage in the existing installed container, not a newly provisioned Hermes-free environment.
- `uv lock --check`, `uv sync --frozen`: pass; lock unchanged.
- Whole-tree frozen Ruff, canonical 21-file compilation, six-tool/CLI registration and validation-error handler smoke: pass.
- Secret scan: `secret_hits=0`; staged/unstaged diff whitespace checks: pass.
- Disk floor: 5.3 GB free. No builds, pushes or gateway restart.

The secret scan's first container invocation encountered Git's ownership protection. Re-run passed with `GIT_CONFIG_COUNT=1`, `GIT_CONFIG_KEY_0=safe.directory`, `GIT_CONFIG_VALUE_0=/opt/data/plugins/profile-delegate` on that single invocation. No persistent Git configuration was written.

## No-YAML boundary

Native model selection always supplies `--session` in addition to live-session RPC scope. The installed resolver returns persistence=false before considering profile defaults. Native effort selection uses only none/minimal/low/medium/high/xhigh/max, a verified session ID and session scope. Native setters are tested with configuration writers replaced by failure traps; model/provider/resume, provider-only creation, effort override and stale session refusal are covered.

An explicit native regression demonstrated that `reasoning=show` reaches `_write_display_sections` -> `_save_cfg` despite session scope. Its writer was trapped: no real file was written. The session starter now refuses display commands before any RPC, in addition to public preflight validation. Native confirmation requirements remain controlled refusals, not automatic approval.

## Pending acceptance

Independent combined review was authorized by the project-routed requesting-code-review skill. It identified the launcher ownership defect and reviewed test retirement. The corrected ownership/conflict/context/identity paths received focal approval, and the complete local suite passes. Full candidate review after the next reduction batch and operator acceptance remain open; no extra user permission is needed for the already-authorized isolated review.

Real changed-candidate provider/Discord round trip, actual selected child identity, detached completion/control/recovery cleanup and comparable full-startup/async-acceptance performance remain pending. They require the accepted operator-controlled runtime stage after review. No test or historical receipt establishes that the current gateway has loaded this code.

Automatic goal wait/resumption remains pending: [native goal boundary and concrete prior-runtime counterexample](2026-10-03-native-goal-boundary.md). Independent detached execution and silent notification behavior are preserved; no unsupported bridge was installed.
