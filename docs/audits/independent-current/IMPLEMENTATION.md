# Independent audit implementation — local candidate, not product acceptance

## F5 follow-up receipt (supersedes contradictory historical F5/discovery paragraphs below)

**Implemented locally; installed/global acceptance BLOCKED, not PASS.** No changes to `FINAL_REVIEW.md`, `scripts/accept_task_approval_runtime.py`, Hermes core/config/profiles or incoming artifacts. HEAD remains `bebd2335b42934386fbceefc0affe7911db8638c`, no staging/commit/restart/activation. Parent confirmed matrix finished before test/harness edits; no matrix rerun.

### Changes

- `.github/workflows/ci.yml`: portable 3.11–3.13 unchanged; native pin unchanged; `uv sync --frozen --group dev --python 3.14 --project "$PROFILE_DELEGATE_TEST_RUNTIME"`, hash-pinned cp314 PyYAML helper (`scripts/native-test-tooling.txt`, hash from Hermes uv.lock), then absolute native `.venv/bin/python` prerequisite and pytest. No plugin-package install on unsupported 3.14, no cross-ABI site-packages.
- `scripts/native_prerequisite.py`, `conftest.py`: session-scoped hard gate checks exact invoking venv path/prefix/version, actual config/approval/SessionDB/agent.display/contracts imports from selected source, tooling/Pydantic from selected venv, real contract validation. Missing closure/import is an error, never skip. `test_native_prerequisite.py`: absent-runtime/foreign-interpreter negatives; installed positive, missing-contract sensitivity and real foreign-interpreter subprocess negative prepared. **Installed positive not executed** because runtime lacks pytest.
- `test_tui_rpc.py`: .8s bound unchanged, starts after fixture subprocess ready + published cancel + setup. Separate 10s total task deadline remains. Receipt includes prepared-control/total duration, returncode, pipes closed. SIGKILL/reaping assertions retained. **Native timing regression execution blocked**, no claimed stabilization PASS.
- `scripts/accept_audit_runtime.py`: reuses existing isolated setup, not matrix; five real handler/runtime cases: TUI completion, accepted steer with correlated follow-up lifecycle/final uptake, active cancel + terminal reaping, CLI forced provider-503 exhaustion→actual plugin recovery prompt in same session, Markdown/text marker and frozen envelope receipts. ONLY MODEL HTTP scripted. Not run successfully; native classifier/provider retries may expose a genuine incompatibility on first authorized execution. PID absence proves transport reaping; parent Python fd.closed is explicitly not instrumented (real-pipe regression retains that assertion). No product transport/core changes justified.
- README/validation/STATE/handoff/CHANGELOG aligned.

### Executed gates / exact limits

Own live environment: plugin Python **3.13.5**, Hermes **3.14.7**, uv **0.12.3** (CI pin remains .11.6). `/opt/hermes/.venv/bin/python -m pytest --version` returned **No module named pytest**. No runtime write performed.

- `uv lock --check`, `uv sync --frozen`, `uv run --frozen ruff check .`, canonical py_compile plus new Python files, `scripts/validate_release.py`, secret scan with all intended new Python/pytest paths, `git diff --check`: exit0; six-tool FakeContext handler smoke, secret_hits=0. No fresh-discovery claim from FakeContext.
- `uv run --frozen python -m pytest -m 'not integration' -q -o 'addopts=' -W error`: **228 passed,444 deselected in6.81s**, `/opt/data/profiles/builder/cache/scratch/f5-final-portable.log`. Added exactly three prerequisite cases: +2 portable,+1 native. This host still has Hermes; not a Hermes-free runner.
- `PYTHONPATH=/opt/hermes /opt/hermes/.venv/bin/python -m pytest -q -o 'addopts=' -W error`: **exit1, No module named pytest**, `f5-final-native.log` in same scratch. Full final gate **not green**; prior669pass is historical, not this changed prerequisite.
- `uv run --frozen python scripts/native_prerequisite.py`: **exit1** rejects foreign plugin interpreter before imports (`f5-foreign-interpreter.log`). Portable focused negatives **2passed/1deselected**.

### Authority blocker (stop, no alternative executor)

`execute_code` rejected: `BLOCKED: execute_code is disabled by profile-delegate child approval policy.` No execution rerouted to defeat it.

Read-only frozen tooling export succeeded:

```bash
uv export --frozen --only-group dev --no-emit-project --project /opt/hermes --output-file /opt/data/profiles/builder/cache/scratch/native-dev-locked.txt
```

Attempted scratch-only tooling provision (no production venv mutation):

```bash
uv pip install --python /opt/hermes/.venv/bin/python --target /opt/data/profiles/builder/cache/scratch/native-314-tooling --require-hashes -r /opt/data/profiles/builder/cache/scratch/native-dev-locked.txt > /opt/data/profiles/builder/cache/scratch/f5-tooling-install.log 2>&1
```

**Blocked exit-1 before execution**: Tirith package threat intelligence incomplete for package '2' (`default-version resolution transport failed; deps.dev metadata lookup transport failed; ecosyste.ms metadata lookup transport failed`); single-query deny cannot approve. Not malicious-package evidence. No alternate installer/executor, extraction retry, environment clearing or guard change. Clean provisioning remains separately blocked by prior extraction refusal.

Reproducible installed harness command, operator-only:

```bash
/opt/hermes/.venv/bin/python scripts/accept_audit_runtime.py --authorize-isolated-runtime
```

Own attempt **exit2**: `frozen delegated authority detected; do not clear or bypass it`. No artifacts/run created by that attempt. Parent must execute from truly authorized operator context; new harness is prepared/compiled/linted, **not verified acceptance**. Do not repeat approval matrix.

### Parent evidence integrated (not own execution)

Read `.artifacts/task-approval-runtime-hdzu9r09/receipt.json`: status ok, matrix_complete true, case_count64. Parent independently aggregated matrix cases **64pass/0nonpass**. Real installed Hermes handlers/launch/guards/tools; deterministic scripted MODEL HTTP fixture. This closes approval matrix, not forced recovery/steer/cancel coverage. Parent fresh-discovery command already exit0, real PluginManager six tools/current_session/invalid handler; discovery no longer pending. Global gaps: clean provision + truly Hermes-free portable execution, actual native gate/positive prerequisite/timing receipt, authorized harness receipts, parent focal independent review. No remote CI/activation or commercially hosted-provider claim.

Baseline `bebd2335b42934386fbceefc0affe7911db8638c`; authorization/acceptance: `DIAGNOSIS_REVIEW.md`. Single writer, same checkout, no delegation/commits/push/restart/core/profile/config/credential edits. Incoming Reviewer document and `.artifacts/` preserved. A→B→C executed sequentially. Final review belongs to parent.

## Implemented / risk → evidence

| Criterion | Change and concrete regression | Acceptance boundary |
|---|---|---|
| F1/R1 | `tui_rpc.py` client-owned byte buffer, bounded os.read/select with monotonic deadline; stderr multiplexed, eight bounded chunks per poll and bounded tail. `test_tui_io.py`: partial deadline/cap+1 without newline, UTF-8 split, concatenated frames, partial EOF, fragmented late response, continuous stderr/event flood, 1 MiB stderr before readiness AND call, cleanup/bounds. Existing strict IDs/malformed/hybrid/cancel/steer tests retained. | Real harmless pipes/processes, not installed gateway/provider acceptance. Timeout tolerance .35s for .1s request, documented scheduler margin not speedup. |
| F2 | `spectator.py` and `event_journal.py` admit exactly child_running/child_stopped/cancellation_requested. `test_audit_contracts.py` producer→inspect running/stopped; `test_sync_lifecycle.py` real child/grandchild cancellation publication inspected and reaped; unknown phase still fails. | Reader remains read-only; no lifecycle rewrite/shared abstraction introduced. |
| F3 | `core.py` recovery receives resolved mode/verdict requirement; same session/envelope. `test_profile_delegate.py::test_transient_failure_resumes_same_session` JSON/Markdown/text captures actual second-attempt prompt, normalizes final output, checks resume footer and identical persisted envelope. | Subprocess runner double; installed CLI transient recovery remains parent smoke. No retry classification/authority modified. |
| F4 | `__init__.py` scope enum only current_session; runtime legacy widening refusal retained. README/BRIEF align origin authority, best-effort notifications, marker and internal-only retention. Schema test and existing public denial/positive origin tests, release registration smoke. | Fresh installed discovery pending; no widening/prune API restored. |
| F5 | CI portable matrix + mandatory installed job using verified immutable Hermes pin; `conftest.py` conservative module integration marker + hard prerequisite failure; import deferred in fixture command test; one runtime-path env for subprocess tests; removed three prerequisite skips. | **NOT ACCEPTED**: isolated provisioning and actual CI unavailable; truly Hermes-free runner not proved. See precise blocker below. |
| F6 | Actual detector boolean asserted True, benign False; `test_false_detector_tuple_is_detected` installs false tuple and requires the positive fixture assertion to raise. Exact-grant/operator/fixture-no-effect checks retained. | Perturbation failure is expected sensitivity evidence, not a claim command executes or guard fails. |

## F5 partition decision / residual

Conservative mixed-module classification intentionally over-classifies tests rather than mock native APIs or hide missing prerequisites. `conftest.py` lists 14 **modules**, not nodeids: compression continuity (SessionDB/ledger/home), native approval (fresh guards/binding), native detached fixture (transitive admission/notification), native resume admission (config spy), native selection/task selection (profiles/config/guards), package loading (profile config), preflight/profile delegate/recursion/reliability/sync lifecycle (transitive native policy and launch), TUI RPC (installed contract subprocess). All cases remain in mandatory full suite and installed job. Native does NOT mean every case is end-to-end; several are runtime-coupled unit tests. New standalone IO/contract tests are portable.

Baseline local no-PYTHONPATH full suite failed (73 failed, 449 passed, 139 errors; `all-no-path.log`); deferred imports now allow complete collection. Last prior partition 223 portable / 442 native; closure adds cases, final count below. A narrower function partition may be future maintenance, but no huge nodeid exception list or wholesale fixture mocking here. No production authority altered to make tests portable.

Installed CI source pin `e8c97320ac8691d4de92af49f98459f9ef9ddb08` matches `/opt/hermes/install-stamp.json`; GitHub commit API returned 200 with exact sha (`hermes-pin.json` in scratch), archive download succeeded. Runtime pyproject requires Python 3.14 for actual dependencies despite updater >=3.11 metadata. Proposed job provisions native runtime on 3.14, plugin tooling on supported 3.13 (plugin contract remains >=3.11,<3.14). Closure and job are **unvalidated**, not CI green. Installed tests currently use plugin interpreter + native dependency path; child subprocesses use runtime interpreter. This is a compatibility compromise to review, not claimed execution of all tests on runtime Python.

### Exact authority/environment blockers (no bypass)

Tool `terminal`, command:

```text
tar -xzf /opt/data/profiles/builder/cache/scratch/hermes-source.tar.gz -C /opt/data/profiles/builder/cache/scratch; docker info --format '{{.ServerVersion}}'; uv sync --frozen --project /opt/data/profiles/builder/cache/scratch/hermes-agent-e8c97320ac8691d4de92af49f98459f9ef9ddb08 --python 3.14
```

Returned exit -1/status blocked: `Security scan — [MEDIUM] Archive extraction to sensitive path ... single-query mode (-q) ... without a user present to approve it`. The combined command did not run. No alternate extraction, config change or guard/env clearing attempted. Separate read-only `docker info --format '{{.ServerVersion}}'` returned `Cannot connect to the Docker daemon at unix:///var/run/docker.sock`. Thus no truly Hermes-free container evidence. `execute_code` was also explicitly denied arbitrary-local-Python authority; no rerouting of that denied execution.

## Deslop / conservation

Removed two unused private schema builders (`_prune_schema`, `_reconcile_schema`) and the obsolete unsafe per-call threaded `_readline_with_timeout` implementation replaced by client-owned IO. Retained denial handlers + their regression, internal retention safety/tests, import/patchability seams, public importable helpers, wait_for_completion test, snapshots/ledger/journal, guard floors/approval modes/frozen envelope. No tests removed, quotas, outbox, logger framework or performance optimization claim. Existing stdio steer fixture now waits for its producer's publication event rather than racing immediate buffered completion; no production settlement rule changed. `test_tui_io` children own a process group like production.

## Before/after and logs

Baseline 651 tests / 99.34s is historical own execution, not a comparable speed benchmark. Earlier candidate 665 / 123.61s passed; closure adds failure-path evidence and revalidates last reader bound edit. Logs under `/opt/data/profiles/builder/cache/scratch/` are private, not committed:
- `tui-io-red.log`: baseline FF.FF then 30s watchdog timeout; not complete clean RED run.
- `audit-closure-focused.log`: 19 passed / 2.66s before final added recovery-envelope assertions.
- `audit-full-final-3.log`, `portable-final.log`, `audit-other-gates.log`: prior candidate evidence.
Final closure gates/results and fresh diff are recorded below after execution.

## Parent commands / installed coverage (prepared, not executed here)

No harness from delegated ancestry; do not clear its frozen environment. Parent must use genuinely authorized operator context and disposable home, not production config.

```bash
# Harmless real-pipe/runner/control regression surface (synthetic gateway, no provider claim)
PYTHONPATH=/opt/hermes uv run --frozen python -m pytest -q -o 'addopts=' -W error test_tui_io.py test_tui_rpc.py test_sync_lifecycle.py
# Existing installed/model-HTTP fixture matrix; optional, broad approval regression, not steer/recovery coverage
/opt/hermes/.venv/bin/python scripts/accept_task_approval_runtime.py --authorize-isolated-runtime --phase matrix
```

Inspected `scripts/accept_task_approval_runtime.py:398-435,441-488`: covers CLI/TUI installed completion, modes/grants/floors/nesting/frozen explicit resume; **does not cover steer/cancel or transient recovery or updated prose**. Its early probe remains deny-CLI only. Existing `cli_smoke.py` runs one direct-core delegation/resume JSON; no provider injection, recovery forcing, controls or isolated-home setup. Do not call it sufficient for F3.

Missing parent smokes: fresh installed plugin discovery on disposable home pointing plugins/profile-delegate to THIS checkout (no copied plugin); inspect six registry schemas/current_session and harmless invalid handler. Installed TUI completion→steer follow-up→cancel→wait/reap/pipes with isolated HTTP provider; distinguish queued ACK from correlated delivery. CLI recovery provider must intentionally emit one recognized transient plus footer, then final Markdown/text marker in same session/frozen envelope. No existing script supplies all those operations; do not invent CLI flags or call an ordinary resume proof of recovery. Parent can extend existing isolated fixture minimally or supply reviewed operator driver; this child has not executed or claimed them.

Current state docs explicitly mark historical receipts, not new acceptance. F5/operator integration + independent final review remain required; no activation implied.

## Final closure receipt

Final code stable: `audit-closure-full-final.log` **669 passed in 128.05s**, full canonical `PYTHONPATH=/opt/hermes uv run --frozen python -m pytest -q -o 'addopts=' -W error`, zero skips. `audit-closure-portable-final.log` **226 passed, 443 deselected in 8.06s**, same command with `-m 'not integration'` and no PYTHONPATH. Partition union preserves all cases. `audit-closure-gates.log`: lock/sync/Ruff/canonical compilation plus new files/release registration/diff/secret scan all exit 0; secret_hits=0. All logs absolute prefix `/opt/data/profiles/builder/cache/scratch/`.

Baseline sensitivity repeated by read-only `git show` blobs compiled in memory, **no copied checkout/worktree or edits/reset**: `audit_baseline_sensitivity.py` / `audit-baseline-sensitivity.log`, exit 0. Baseline partial .05s reads delayed .422/.427s; R1 readiness saturated; F2 three phases reject exit 4; F3 unconditional JSON; F4 widening offered; F6 tuple false truthy. Fixed positive/control perturbation tests passed full suite. `audit-missing-prereq.log`: runtime=/nonexistent yields **2 errors**, exit 1 as required, not skips. One intermediate portable run exposed producer startup race in cap test; test now waits for first-byte readiness before measuring reader deadline (does not consume stdout or relax production bounds); final green above. Earlier failed logs retained, not relabelled PASS.

Tracked diff: `/opt/data/profiles/builder/cache/scratch/audit-implementation-tracked.diff` from `git diff --binary`; excludes untracked additions (inspect these directly: `pytest.ini`, `scripts/scan_secrets.py`, `test_tui_io.py`, `test_audit_contracts.py`, this report). Reviewer `DIAGNOSIS_REVIEW.md` remains incoming untracked, not authored here. No staged changes/new commits; HEAD unchanged.

Prepared fresh installed discovery driver `/opt/data/profiles/builder/cache/scratch/audit_operator_discovery.py`, inspected against installed PluginManager/registry API; **NOT executed**, refuses frozen delegated ancestry. Parent command:

```bash
/opt/hermes/.venv/bin/python /opt/data/profiles/builder/cache/scratch/audit_operator_discovery.py
```

It creates only a private scratch home, enables plugin there, symlinks this checkout, discovers via actual Hermes manager, verifies six tools/scope and invalid-status handler. No production restart/config changes. It is an inspectable proposed smoke, not success evidence. Installed steer/cancel/recovery driver remains a missing runtime acceptance artifact; existing scripts cannot honestly claim those surfaces. Parent owns that minimal operator extension and final Reviewer. Local authorized improvements/record complete; **global acceptance BLOCKED** for F5 provision/real Hermes-free CI and affected installed smokes. No command was rerun to bypass extraction denial.
