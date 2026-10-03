# Native simplification — final local candidate evidence

Production candidate: TUI deadline batch atop `e160a35`, following native query-file input and CLI owner corrections. The latter correction retains the supervisor identity and uses existing transport fields for the CLI child; same-caller cancellation still verifies the child group. Its regression fails on `2aeeb8f` and focal independent review approves the patch subject to final gates. Historical nonterminal artifacts are not repaired retroactively. Functional release remains v1.10.0; this is an unactivated local candidate. The Codex goal remains active because the full acceptance criteria below are pending.

## Exact scope and measurements

All tracked Python files are counted: root production including `cli_smoke.py`, root `test_*.py`, and support including `conftest.py`, scripts and fixture helpers. Movement between modules does not count as reduction. Physical lines use `splitlines()`; nonblank/noncomment excludes blank and comment-only lines using Python tokenization and retains docstrings. Metrics cover the same paths/rules at all revisions; no `.artifacts` were tracked at either baseline.

| Scope | Historical `a579142` physical / substantive | Initial `5ddc731` physical / substantive | Candidate physical / substantive |
| --- | ---: | ---: | ---: |
| Production (13 files) | 7643 / 6787 | 7658 / 6799 | 7252 / 6382 |
| Tests (27 files) | 7948 / 6759 | 8006 / 6808 | 8164 / 6949 |
| Support (historical 5; initial/current 6 files) | 698 / 606 | 969 / 839 | 969 / 839 |
| Collected cases | 709 | 712 | 719 |

All tracked Python totals: historical 16289, incoming 16633, candidate 16385 physical lines. The candidate is -248 versus incoming and +96 versus historical; production-only reduction is not whole-tree historical reduction.

Production <=7253 is met: -391 physical and -405 substantive lines versus historical. Tests <=6908 and cases <=654 remain pending: gaps 1256 lines and 65 cases. Support growth predates this refactor and is not excluded. Fifteen redundant cases were retired; twenty-two meaningful selection/delivery/safety regressions were added. Net case count versus initial is +7. [Coverage retirement rationale](2026-10-03-test-retirement.md) identifies retired families and surviving assertions. Independent review found no evidence that another 55 distinct safety cases can be deleted safely. Remaining authority/compression/malformed artifact/native503/publication race cases stay covered; The reviewed fixture slice removes 107 net test lines counting its local helpers. It preserves 177 test definitions/decorators and 680 assertions across the three edited modules. The independent review found about 95–135 lines of safe setup consolidation, not evidence supporting the full remaining deficit.

The native worker ownership defect was reproduced against exact `3fed48e`: dispatch owner was the launcher PID; native abandoned recovery terminalized a live detached task. Both process/ledger regressions fail there and pass on this candidate. The actual native SessionDB and detached processes run in a disposable caller home, provider workload is a fixture, and replay goes only to a local test queue. Silent execution creates no native notification row. Reviewer findings on conflict finalization and thread-local home propagation have regression coverage and focal approval; full Discord acceptance remains pending; real provider subcases below now pass.

Private reproducible receipts: `.artifacts/refactor-20261003/final-line-metrics-tui-budget.json` (latest counts), `final-line-metrics-query-file.json` (prior input fix), `final-line-metrics-cli-owner.json` (prior owner correction), `final-line-metrics.json` (prior fixture revision) and `import-benchmark-current.json`. Historical counts use `git ls-tree -r --name-only REV` and `git show REV:PATH`; the working candidate uses the same tracked scope from `git ls-files`, reading files before commit. Both apply the three categories above and count full-line comments with `tokenize.generate_tokens`.

Controlled fresh-process import measurement at production revision `482b2d7` (before the subsequent CLI ownership correction): Hermes Python 3.14.7, seven samples after one warmup, alternating initial/candidate order, identical interpreter and installed closure. All root production modules are precompiled on both sides; imported source origins are verified. Median import of core/TUI/plugin modules: **11.38 -> 12.53 ms**; median maximum RSS: **56960 -> 56960 KiB**. The prior receipt did not establish matching bytecode-cache policy and is superseded for performance claims. No provider startup, detached acceptance, Discord delivery or memory under a real workload is inferred from this import-only comparison; it establishes no workload speedup.

## Canonical gates

From `.agents/validation.md`, final candidate:

- Native full suite, installed Python 3.14.7, `-W error`: **719 passed in 127.28 s**. Integration prerequisites execute against the real installed native closure; no skipped missing-runtime partition.
- Portable partition, frozen plugin Python 3.13: **238 passed / 481 deselected in 8.15 s**. This is interpreter/partition coverage in the existing installed container, not a newly provisioned Hermes-free environment.
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

Private receipts remain ignored: `real-cli-6ph7i_ix/acceptance.json`, `real-tui-3afzajlx/{acceptance,resume-acceptance}.json`, `service-cli-_gv2p6n3/{acceptance,owner-fix-acceptance}.json` and `service-handler-i3i11nxu/{public-handler-receipt,cli-cancel-owner-receipt}.json`, under `.artifacts/refactor-20261003/`. Earlier probe setup mistakes (literal @file used by the parent invocation; an omitted isolated runs root) are excluded from acceptance. The later controlled child-workload comparison independently exposes the same literal-file-input defect in plugin production and motivates the native query-file fix below. Single acceptance observations are not evidence of a speedup.

## Native CLI file input and real workload comparison

Installed Hermes treats `-q @file:...` as literal query text. All four real executions in the balanced baseline/old-candidate comparison used `read_file` solely to read their own prompt. The existing argv privacy test now invokes the installed native parser and file reader; it fails before the production change. `--query-file` delivers the complete task directly and preserves raw-task argv privacy, named-profile selection, frozen authority, execution overrides and recovery/resume flags. One production line changes; no adapter or additional test case was added. Independent focal review verifies eight parser/reader combinations, including Unicode and literal shell characters, and approves subject to the completed gates.

The controlled comparison uses exact precompiled production snapshots, installed Python 3.14.7, the configured UID, the same harmless task, profile, cwd, native route and frozen `deny` fingerprint. Same-executor runs finish valid with owned processes gone; caller and target YAML hashes agree before/after. SessionDB reads are confined to the newly created child sessions.

| Snapshot | Samples | Median wall time | API calls per sample | Tool calls |
| --- | ---: | ---: | ---: | --- |
| Initial `5ddc731` | 2 | 28.61 s | 2 | Read own prompt |
| Prior candidate `1c4fe3a` | 2 | 27.78 s | 2 | Read own prompt |
| Native query-file `e160a35` | 2 | 22.86 s | 1 | None |

The four earlier runs alternate baseline/candidate/candidate/baseline; fixed runs follow them. Two samples per version and variable provider timing support no statistical latency claim. The eliminated tool/API roundtrip is directly observed. Parent and maximum-child RSS show no established reduction; maximum-child RSS is not aggregate concurrent memory. Receipt hashes match every production module at `e160a35`, the measured revision; this comparison predates the TUI deadline correction.

A separate first-call detached acceptance measurement uses an explicit harmless literal task, with no private request/prompt copied. Acceptance is 945.79 ms baseline / 933.65 ms fixed; one sample each establishes no speedup. The fixed job completes ok/valid with one API call, no tools, notification false, paired supervisor identity and both processes gone. The baseline accepts dispatch but its child exits -7 before a result; cause is unproven and it is excluded from completion/performance equivalence. Configuration hashes remain unchanged since the controlled comparison. No workload was restarted after an observation timeout.

Automatic approval review rejected an earlier proposed measurement because it copied the payload from a private `request.json`; that command did not run. The explicit harmless-literal alternative passed review. Earlier observer mistakes (expecting a response PID, omitting the required session title) provide no performance evidence and are excluded; they prompted no product API or harness changes.

Private receipts: `.artifacts/refactor-20261003/cli-workload-comparison-z4yvy224/{receipt,query-file-receipt,query-file-async-acceptance-valid}.json`. The fixed receipt records source SHA256 per production file, exact child identities, native API-call count and route-field equality. Metrics are in `final-line-metrics-query-file.json`. Real failure/recovery equivalence and gateway/Discord acceptance remain pending.

## Shared TUI initialization budget

Creation previously received the original timeout after preparation, and prompt submission received the full initialization allowance again after session preparation. The existing call-flow/readiness tests reproduce the extra budget (creation 60 instead of 59.75 seconds; submission 5 instead of the remaining 2). Both stages now consume one deadline. A third existing test reproduces zero-budget dispatch: the client previously wrote the RPC before failing; it now refuses before allocating a request ID or writing. Subsequent positive-timeout/late-response correlation assertions remain intact. No test case was added. Focal independent review approves the final three-file change. Positive-timeout write/backpressure behavior is unchanged and is not certified by this slice.

Real provider TUI new and resume both complete ok/valid, with inherited selection, frozen deny, notification false, no tool calls and both owned processes gone. Resume retains the existing child identity. Terminal artifacts were initially observed just before worker exit; a separate liveness observation confirms cleanup, without restarting either task. Global and target YAML hashes agree before/after. Source hashes and observations: `.artifacts/refactor-20261003/real-tui-budget-r92o8lcc/receipt.json`.

A separate real native-parent probe on `e160a35` verifies public dispatch/status and delivery to that exact local CLI origin: native ledger completed/delivered, one completion user row, worker/transport gone, unchanged YAML. The native ledger parent_session_id is null; origin_session matches the real caller. Its selected parent policy requires notification true. Only the own child's sanitized journal was read. Steering is not acceptance: no command was sent, because the probe demanded initialization kinds absent from that journal before the child completed. The earlier direct control without a session origin was correctly refused. Receipt: `public-real-steer-1befi1l1/receipt.json`. No further journal polling or simulated-provider mechanism was added to the product.

Live effort override preflight refuses under the current caller policy (`execution_overrides_not_allowed`); no task/configuration was changed to force positive selection. Native writer-trap tests still validate authorized session-scoped selection. Gateway generation remains unchanged; Discord and applied steering acceptance stay pending.

## No-YAML boundary

Native model selection always supplies `--session` in addition to live-session RPC scope. The installed resolver returns persistence=false before considering profile defaults. Native effort selection uses only none/minimal/low/medium/high/xhigh/max, a verified session ID and session scope. Native setters are tested with configuration writers replaced by failure traps; model/provider/resume, provider-only creation, effort override and stale session refusal are covered.

An explicit native regression demonstrated that `reasoning=show` reaches `_write_display_sections` -> `_save_cfg` despite session scope. Its writer was trapped: no real file was written. The session starter now refuses display commands before any RPC, in addition to public preflight validation. Native confirmation requirements remain controlled refusals, not automatic approval.

## Pending acceptance

Independent combined review was authorized by the project-routed requesting-code-review skill. It identified the launcher ownership defect and reviewed test retirement. The corrected ownership/conflict/context/identity paths received focal approval, and the complete local suite passes. The combined local candidate has independent approval, including exact equivalence for 45 environment variants, 12 recovery results and 120 argv variants. The fixture slice has independent approval and full gates. Numeric test/case criteria and real operator acceptance remain open; no extra user permission is needed for the already-authorized isolated review.

Real fresh-process provider, child identity, same-caller public dispatch/status and owned cancellation subcases are now demonstrated as above. Discord visible round trip, applied steering, failure/recovery in the real provider path remain pending. Comparable CLI workload and first-call async-acceptance measurements are now recorded above, with their small-sample and baseline child-failure limits; broader performance equivalence remains pending. Gateway-loaded acceptance requires the operator-controlled activation stage. No test or historical receipt establishes that the current gateway has loaded this code.

Automatic goal wait/resumption remains pending: [native goal boundary and concrete prior-runtime counterexample](2026-10-03-native-goal-boundary.md). Independent detached execution and silent notification behavior are preserved; no unsupported bridge was installed.
