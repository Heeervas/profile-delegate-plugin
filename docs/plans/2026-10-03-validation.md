# Native simplification — final local candidate evidence

Production candidate: `2aeeb8f` plus the CLI ownership correction, following `045319d` and `482b2d7`. The latter correction retains the supervisor identity and uses existing transport fields for the CLI child; same-caller cancellation still verifies the child group. Its regression fails on `2aeeb8f` and focal independent review approves the patch subject to final gates. Historical nonterminal artifacts are not repaired retroactively. Functional release remains v1.10.0; this is an unactivated local candidate. The Codex goal remains active because the full acceptance criteria below are pending.

## Exact scope and measurements

All tracked Python files are counted: root production including `cli_smoke.py`, root `test_*.py`, and support including `conftest.py`, scripts and fixture helpers. Movement between modules does not count as reduction. Physical lines use `splitlines()`; nonblank/noncomment excludes blank and comment-only lines using Python tokenization and retains docstrings. Metrics cover the same paths/rules at all revisions; no `.artifacts` were tracked at either baseline.

| Scope | Historical `a579142` physical / substantive | Initial `5ddc731` physical / substantive | Candidate physical / substantive |
| --- | ---: | ---: | ---: |
| Production (13 files) | 7643 / 6787 | 7658 / 6799 | 7251 / 6381 |
| Tests (27 files) | 7948 / 6759 | 8006 / 6808 | 8143 / 6929 |
| Support (historical 5; initial/current 6 files) | 698 / 606 | 969 / 839 | 969 / 839 |
| Collected cases | 709 | 712 | 719 |

All tracked Python totals: historical 16289, incoming 16633, candidate 16363 physical lines. The candidate is -270 versus incoming and +74 versus historical; production-only reduction is not whole-tree historical reduction.

Production <=7253 is met: -392 physical and -406 substantive lines versus historical. Tests <=6908 and cases <=654 remain pending: gaps 1235 lines and 65 cases. Support growth predates this refactor and is not excluded. Fifteen redundant cases were retired; twenty-two meaningful selection/delivery/safety regressions were added. Net case count versus initial is +7. [Coverage retirement rationale](2026-10-03-test-retirement.md) identifies retired families and surviving assertions. Independent review found no evidence that another 55 distinct safety cases can be deleted safely. Remaining authority/compression/malformed artifact/native503/publication race cases stay covered; The reviewed fixture slice removes 107 net test lines counting its local helpers. It preserves 177 test definitions/decorators and 680 assertions across the three edited modules. The independent review found about 95–135 lines of safe setup consolidation, not evidence supporting the full remaining deficit.

The native worker ownership defect was reproduced against exact `3fed48e`: dispatch owner was the launcher PID; native abandoned recovery terminalized a live detached task. Both process/ledger regressions fail there and pass on this candidate. The actual native SessionDB and detached processes run in a disposable caller home, provider workload is a fixture, and replay goes only to a local test queue. Silent execution creates no native notification row. Reviewer findings on conflict finalization and thread-local home propagation have regression coverage and focal approval; full Discord acceptance remains pending; real provider subcases below now pass.

Private reproducible receipts: `.artifacts/refactor-20261003/final-line-metrics-cli-owner.json` (latest counts), `final-line-metrics.json` (prior fixture revision) and `import-benchmark-current.json`. Counts come from `git ls-tree -r --name-only REV`, retrieving each `.py` with `git show REV:PATH`, applying the three categories above and counting full-line comments with `tokenize.generate_tokens`.

Controlled fresh-process import measurement at production revision `482b2d7` (before the subsequent CLI ownership correction): Hermes Python 3.14.7, seven samples after one warmup, alternating initial/candidate order, identical interpreter and installed closure. All root production modules are precompiled on both sides; imported source origins are verified. Median import of core/TUI/plugin modules: **11.38 -> 12.53 ms**; median maximum RSS: **56960 -> 56960 KiB**. The prior receipt did not establish matching bytecode-cache policy and is superseded for performance claims. No provider startup, detached acceptance, Discord delivery or memory under a real workload is inferred from this import-only comparison; it establishes no workload speedup.

## Canonical gates

From `.agents/validation.md`, final candidate:

- Native full suite, installed Python 3.14.7, `-W error`: **719 passed in 123.84 s**. Integration prerequisites execute against the real installed native closure; no skipped missing-runtime partition.
- Portable partition, frozen plugin Python 3.13: **238 passed / 481 deselected in 6.86 s**. This is interpreter/partition coverage in the existing installed container, not a newly provisioned Hermes-free environment.
- `uv lock --check`, `uv sync --frozen`: pass; lock unchanged.
- Whole-tree frozen Ruff, canonical 21-file compilation, six-tool/CLI registration and validation-error handler smoke: pass.
- Secret scan: `secret_hits=0`; staged/unstaged diff whitespace checks: pass.
- Disk floor: 5.3 GB free. No builds, pushes or gateway restart.

The secret scan's first container invocation encountered Git's ownership protection. Re-run passed with `GIT_CONFIG_COUNT=1`, `GIT_CONFIG_KEY_0=safe.directory`, `GIT_CONFIG_VALUE_0=/opt/data/plugins/profile-delegate` on that single invocation. No persistent Git configuration was written.

## Real fresh-process runtime evidence

Harmless real-provider probes ran in fresh native Hermes processes without rebuilding or restarting the gateway. They preserve the target profile and inherited model/provider, frozen `deny` authority and the existing runtime configuration. These are functional subcases, not Discord release acceptance or a baseline performance comparison.

| Path | Observed result | Boundary |
| --- | --- | --- |
| CLI detached/new | completed / task ok / contract valid | Initial direct API probe used UID0; worker and transport gone. Configuration mtime predates the run; no before/after hash was captured for this first case. |
| TUI detached/new and resume | completed / task ok / contract valid; resume keeps child identity | Initial direct API probes used UID0; notification disabled, owned processes gone, before/after global and target YAML hashes equal. Native SessionDB confirms child identity and route; CLI/TUI inherited route tuples agree. |
| CLI sync/new and detached/resume | completed / task ok / contract valid; resume keeps child identity | Configured gateway UID1000; notification false, global/target YAML hashes equal. |
| Native public dispatch, then same-caller status | completed / task ok / contract valid; exact real parent identity retained | Configured gateway UID1000; native ledger completed and delivered. The model supplied notify=true despite the prompt asking false; the plugin honored the actual argument. |
| Native public TUI cancel | cancelled; task failed; contract not evaluated; native ledger error delivered | Same real originating caller. Interrupt RPC timed out after 2.5s; owned local cancellation is authoritative, with worker and transport gone. Early steer ACK is rejected: no initialized native agent; it proves no applied steering. |
| CLI detached/resume after owner correction | completed / task ok / contract valid; same child session | Supervisor and transport PIDs remain distinct and correctly paired; both gone, transport_alive=false, notification disabled, YAML hashes equal. |
| Native public CLI cancel after owner correction | cancelled; task failed; contract not evaluated; native ledger error delivered | Same originating caller; ACK confirms owned CLI group terminated and leader reaped. Supervisor and child both gone; YAML hashes equal. |

The actual supervised gateway runs with configured UID1000. The root launcher shim drops to static UID10000, which cannot read the UID1000 configuration/plugin paths. The service probes therefore invoke the same launcher as UID1000, matching the existing deployment actor; no shim, file permissions, authority guards or configuration were changed. Fresh-process discovery and these CLI parent results do not establish that the long-running gateway loaded the candidate or that a Discord recipient received it.

Private receipts remain ignored: `real-cli-6ph7i_ix/acceptance.json`, `real-tui-3afzajlx/{acceptance,resume-acceptance}.json`, `service-cli-_gv2p6n3/{acceptance,owner-fix-acceptance}.json` and `service-handler-i3i11nxu/{public-handler-receipt,cli-cancel-owner-receipt}.json`, under `.artifacts/refactor-20261003/`. Probe setup mistakes (native CLI does not expand @file prompts; an omitted isolated runs root) created no product fix and are excluded from acceptance. Single acceptance observations are not evidence of a speedup.

## No-YAML boundary

Native model selection always supplies `--session` in addition to live-session RPC scope. The installed resolver returns persistence=false before considering profile defaults. Native effort selection uses only none/minimal/low/medium/high/xhigh/max, a verified session ID and session scope. Native setters are tested with configuration writers replaced by failure traps; model/provider/resume, provider-only creation, effort override and stale session refusal are covered.

An explicit native regression demonstrated that `reasoning=show` reaches `_write_display_sections` -> `_save_cfg` despite session scope. Its writer was trapped: no real file was written. The session starter now refuses display commands before any RPC, in addition to public preflight validation. Native confirmation requirements remain controlled refusals, not automatic approval.

## Pending acceptance

Independent combined review was authorized by the project-routed requesting-code-review skill. It identified the launcher ownership defect and reviewed test retirement. The corrected ownership/conflict/context/identity paths received focal approval, and the complete local suite passes. The combined local candidate has independent approval, including exact equivalence for 45 environment variants, 12 recovery results and 120 argv variants. The fixture slice has independent approval and full gates. Numeric test/case criteria and real operator acceptance remain open; no extra user permission is needed for the already-authorized isolated review.

Real fresh-process provider, child identity, same-caller public dispatch/status and owned cancellation subcases are now demonstrated as above. Discord visible round trip, applied steering, failure/recovery in the real provider path and comparable full-startup/async-acceptance performance remain pending. Gateway-loaded acceptance requires the operator-controlled activation stage. No test or historical receipt establishes that the current gateway has loaded this code.

Automatic goal wait/resumption remains pending: [native goal boundary and concrete prior-runtime counterexample](2026-10-03-native-goal-boundary.md). Independent detached execution and silent notification behavior are preserved; no unsupported bridge was installed.
