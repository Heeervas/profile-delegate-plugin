# Per-task repair — runtime matrix verified, final bounded re-review pending

## Historical missing-envelope review fix (latest)

Independent review `/opt/data/profile_delegate/runs/pd_20261001_231809_b80ll9/stdout.txt` verified the **64-case installed CLI/TUI matrix** at `.artifacts/task-approval-runtime-5zkkraa1` (receipt read back: status ok, matrix_complete true, case_count 64). This supersedes earlier NOT RUN/pending runtime statements below. Review remained BLOCKED by historical resume recomputation; final re-review is still required, not claimed PASS.

`native_resolution.py` now refuses matching historical requests lacking native_approval and unknown sessions without a trustworthy frozen envelope with `approval_policy_error`: **create a new session**. Neither branch calls current resolution/config. Legacy selectors including approve_yolo cannot refresh authority. Valid frozen resume/ancestry/conflict handling is unchanged. Regression covers six stored selectors against empty/new permanent grants and widened live posture, prohibits current resolution/config reads, and verifies persisted request unchanged. Three narrowly affected transport/continuity fixtures now seed actual frozen request/status records instead of relying on the removed unknown-session fallback; existing transport assertions retained.

Process/dirty-tree inspection before edits found only this delegated worker/TUI, no concurrent delegate writer. Incoming index/dirty work preserved. No harness/matrix rerun, production config/core/restart/activation/commit or future audit/refactor.

Validation: focused approval/selection/resume **72 passed in 26.71s**. Initial full run **630 passed, 21 failed** because old transport fixtures lacked frozen envelopes; repaired fixtures. Focused continuity/profile aggregate exposed unrelated ordering-dependent foreign `cli` import (`279 passed, 1 failed`), unchanged production import code. Final exact canonical full suite **651 passed in 102.85s**, lock/sync, whole-tree Ruff, canonical compilation plus changed modules/tests, six-tool registration/handler smoke, staged/unstaged diff checks passed. Controller commissions bounded re-review; activation remains separately authorized.

## Grant fixture follow-up (latest receipt)

Matrix failure was diagnosed against actual installed native matching: permanent exact command survived snapshot, but quoted Python semicolon/parentheses combined with -c disqualify the command-text allowlist shortcut. Only harness fixture changed: distinct harmless marker modules prepared in disposable effects cwd, simple flagged import commands with exact disjoint grants, module-name deny patterns retaining target/ancestor prohibitions. No production plugin/core changes or runtime retry. Focused `test_runtime_fixture_commands.py test_native_approval.py test_task_approval_selection.py`: **53 passed in 23.21s**; whole-tree Ruff/compile/diff passed. Prior full production gate reused. Controller owns fresh probe/matrix and review; details in RUNTIME_HARNESS.md.

## Same-session follow-up (earlier receipt)

Controller authorized minimal artifact-lint/provider repair. `pyproject.toml` now adds Ruff `extend-exclude = [".artifacts"]` while preserving all lint rules and generated evidence. Failed probe request dump proved the provider received a literal `@file:.../runs/.../prompt.txt` user message. Existing provider now resolves only bounded prompt references inside its own run root. Existing resume operations cover CLI and TUI and assert identical frozen envelope/session identity; no new framework or runtime guard changes.

Exact canonical gate rerun: **640 passed in 102.24s**, lock/sync, whole-tree Ruff, compilation including harness, six-tool registration/handler smoke and final diff check passed. No harness execution or isolated runtime launch from delegated ancestry; controller must execute probe then matrix. See RUNTIME_HARNESS.md.

This actual installed TUI resume is run `pd_20261001_224447_dxcm0b`: request session_mode resume, requested and observed durable child id both `20261001_223934_2050fe`, UI id `9b009d5f`. Session context retained the prior task/result; terminal reports repository cwd `/opt/data/plugins/profile-delegate`, matching requested/stored workspace. Request/status retain native schema-v2 effective profile/source task authority. This verifies real same-session resume admission/tool execution in the repository workspace, not an isolated contrasting-cwd matrix or final exit/notification.

## Post-restart bounded follow-up (earlier receipt)

Run `pd_20261001_223924_8qzx00` reached the actual installed TUI (`selected_transport=interactive`, `actual_transport=tui_stdio`, readiness ready). Its own `/opt/data/profile_delegate/runs/pd_20261001_223924_8qzx00/request.json` has artifact schema 3, **native approval schema 2**, `child_approval_mode=profile`, effective profile, source task, bypass false, native manual/single-query deny/unattended deny. Durable child session: `20261001_223934_2050fe`; UI session: `b19abd31`, independently observed in status.json and live session identity. The previous schema-v1 gateway/schema-v2 bootstrap startup mismatch is absent in this run. This receipt does not establish clean terminal exit or notification delivery while the child is still running.

Actual native tools used successfully: `read_file`, `search_files`, `patch`, `terminal`, and read-only `lcm_inspect` (parallel wrapper used for independent calls). Reads, the real test-fixture patch, and actual repository validation exercised installed tool execution; no simulated provider, dangerous operation, permission change, nested delegation, denial retry, or runtime harness repair. No four-mode behavior contrast or resume acceptance is claimed.

The preflight conflict fixture now explicitly sets isolated plugin policy `allow_child_approval_override=false` and `allow_reasoning_override=false`; all existing actionable-patch/no-run assertions are retained. Its pre-fix focused run already passed in this Builder's caller context (1 passed in 0.62s), so live caller-policy contamination is consistent with the controller's prior failure but not reproduced here.

Latest executed gates:

- `uv lock --check`: 11 packages resolved; `uv sync --frozen`: 9 checked.
- Focused preflight/selection suite: **26 passed in 0.80s**.
- Complete frozen warnings-as-errors suite: **640 passed in 103.70s**.
- Exact canonical `uv run --frozen ruff check .`: **FAILED, 24 errors**, all in incoming `.artifacts/task-approval-runtime-{18v6g72s,_0aukij2}/homes/profiles/accept-target/skills/` copies. Incoming artifacts were preserved, not repaired/deleted; therefore the complete exact release gate is NOT green.
- Diagnostic repository-source Ruff with explicit `--exclude .artifacts`: all checks passed; this is not a substitute for the exact canonical gate.
- Canonical compilation: passed. Six-tool registration/validation-error handler smoke: success, version 1.10.0. `git diff --check`: passed.

Controller owns disposition of the incoming runtime artifacts/Ruff discovery blocker, subsequent four-mode real runs and stored-workspace resume, and independent Reviewer. No staging, commit, reset, stash, restart, publication, production config or Hermes-core edit. Earlier blocked receipts below remain historical, not this run's current authority.

Authoritative scope: `/opt/data/cache/documents/doc_9094ddb74402_astra-per-task-permissions.txt` (read in full). The prior A8/model-selector rejection is NOT acceptance for this repair. Controller owns DRIFT.md and independent review.

## Implemented selection/admission

The public handler passes the selector to core. Exact `deny|profile|inherit|yolo` and `approve_yolo` alias are accepted; wrong types, blank strings and unknown values return actionable validation failures. Null/omission uses configured defaults (new default profile; historical resume missing selector deny). Explicit selection beats target-map defaults without changing target settings.

Caller YAML `allow_child_approval_override: true` is an explicit delegated task-selection grant, not a native setting or default. False/missing refuses profile/inherit/yolo selection before run allocation. Deny narrowing requires no such grant. The configured default selects omitted requests; it is not an authority ceiling. Root yolo needs this real grant, not merely native mode off or an alias. Target allowlist, depth, and same-home admission remain independent.

Profile snapshots target posture/permanent grants; inherit snapshots caller posture/permanent grants (not session yolo or transient consent). Process-frozen operator yolo and native mode off remain native posture. No credentials enter the approval snapshot. Target/ancestor explicit denies remain. Hooks retain their independent native consent gate.

Deny forces manual/deny unattended posture and bypass=false, retaining permanent command grants. Native guard evaluates floors and permanent grants before fresh approval; the old unconditional dangerous-command rejection was removed. Host execute_code still refuses under deny: installed native single-query execute_code requires whole-script consent and does not consult terminal permanent grants. No command-level sandbox claim.

Nested execution permits exact frozen inherit or deny narrowing; new target permanent grants never replace ancestor grants. Other switches are incomparable and refused. Resume retains the original envelope; a different explicit selector refuses. Deny resume requires matching narrowed ordinary policy, no bypass and all current ancestor denies.

## Public examples (same admitted target; caller grant required except deny)

```json
{"profile":"worker","session_title":"deny task","task":"Inspect project","child_approval_mode":"deny"}
{"profile":"worker","session_title":"target task","task":"Run project checks","child_approval_mode":"profile"}
{"profile":"worker","session_title":"caller task","task":"Run project checks","child_approval_mode":"inherit"}
{"profile":"worker","session_title":"bypass task","task":"Run disposable operation","child_approval_mode":"yolo"}
```

## Expected / observed matrix

| Mode | Expected ordinary behavior | Public handler and argv regression | Actual installed CLI/TUI tool + filesystem |
|---|---|---|---|
| deny | fresh ordinary consent refused; permanent command grants retained | PASS | NOT RUN for repaired path |
| profile | target posture and permanent grants | PASS | NOT RUN |
| inherit | caller posture and permanent grants; target denies | PASS | NOT RUN |
| yolo | ordinary bypass, explicit denial floors retained | PASS | NOT RUN |

Fresh-child native guard regression exercises installed Hermes manual/smart/off and unattended deny/approve, floor refusal, isolated/host execute_code, and zero approval queues. This is helper integration, NOT end-to-end acceptance; no allowlisted printf or fabricated filesystem proof is substituted.

## Early real boundary and exact blocker

The first attempted runtime probe used execute_code for batched file discovery and returned exactly:

`BLOCKED: execute_code is disabled by profile-delegate child approval policy.`

No retries via interpreter/tool, no frozen live envelope mutation. Ordinary reads/edits/pytest were permitted. The repair delegate itself has frozen deny authority; it must not launch broader isolated authority as a workaround. Controller must execute the authorized isolated CLI/TUI runtime matrix from its own admitted authority or redispatch with explicit scoped validation authority. No live config widening is requested.

Minimum validation needed: same disposable target and fixed config across task selectors; disposable `rm -rf` fixtures genuinely detected as ordinary approval; disjoint caller and target permanent command grants and contrasting unattended postures; tool responses AND existence checks; target deny under yolo/inherit; no alternate operations after refusal; alias/omission/invalid/unauthorized; narrowed nesting and immutable resume. Run real public handler launch, not snapshot helpers, against `/opt/hermes` entrypoint, using isolated homes under repository `.artifacts` or pytest TMPDIR, no live credential/config writes. Controller commissions independent Reviewer only after this receipt is closed.

## Local validation

Initial full suite exposed invoking-child ancestry leaking into unrelated pytest fixtures (49 failures/2 teardown errors). Added pytest-only autouse isolation of `PROFILE_DELEGATE_APPROVAL_REQUEST`; explicit ancestry tests install their own fixture. Does not modify the live agent envelope. Subsequent full frozen warnings-as-errors suite: 615 passed, Ruff passed. Additional unauthorized/narrowing tests added afterward; final gate is recorded in STATE.md. Incoming package-relative imports and lock changes preserved; package-loading regression retained.

No activation/restart/core/config/credential changes, commits, pushes, publication or nested delegation. No repair acceptance or activation-ready claim until actual runtime evidence and independent review are complete.

## Independent review fixes (bounded follow-up)

Verified findings against installed Hermes session contracts/native guard and `git show HEAD` historical snapshot/bootstrap. Implemented:

- TUI resume emits only profile/session_id/source/cols, with no cwd, title, model/provider/reasoning override or creation flags. Create still sends cwd. Installed `SessionCreateParams` / `SessionResumeParams` validate actual emitted payloads in the installed Hermes interpreter (plugin venv intentionally lacks pydantic). Stored cwd restoration remains Hermes-owned; frozen approval lookup is unchanged.
- New snapshots use **approval envelope schema v2**, identifying normalized deny's permanent-grant semantics. Every historical schema-v1 deny is rejected with an actionable **create a new session** error, including apparently manual/deny envelopes: the old bootstrap refused dangerous commands before checking permanent grants, so merely rejecting off/bypass/approve would still silently widen historical granted-command behavior. Historical v1 profile/inherit/yolo remain accepted byte-for-byte, with no migration. New v2 deny requires bypass=false and manual/deny/deny posture. Resume converts matching invalid frozen authority into `approval_policy_error`; no fallback/recomputation and no persisted envelope writes. Binding independently refuses historical deny before installing policy. Intermediate repaired v1 deny candidates must also start fresh; their origin is indistinguishable from old v1 authority.
- Pytest-only ancestry isolation also clears `PROFILE_DELEGATE_PARENT_TASK_ID`. Real production same-home/depth admission remains unchanged; ancestry tests explicitly install their own markers.
- Public model schema says only profile/inherit/yolo require the caller override grant; deny narrowing is exempt. Registration regression checks the actual emitted schema.

Validation performed without full-suite execution or edits to the other Builder's runtime harness:

```text
PYTHONPATH=/opt/hermes uv run --frozen python -m pytest -q -o 'addopts=' -W error \
  test_native_approval.py test_task_approval_selection.py test_tui_rpc.py \
  test_sync_lifecycle.py test_preflight_contract.py test_package_loading.py test_reliability_reset.py
190 passed in 54.74s

PROFILE_DELEGATE_PARENT_TASK_ID=reviewer-regression \
PROFILE_DELEGATE_APPROVAL_REQUEST=/nonexistent/reviewer-regression.json \
PYTHONPATH=/opt/hermes uv run --frozen python -m pytest -q -o 'addopts=' -W error \
  test_sync_lifecycle.py::test_provider_realm_mismatch_fails_without_session_retry \
  test_task_approval_selection.py::test_pytest_lineage_is_independent_of_invoking_parent \
  test_native_resume_admission.py test_native_selection.py test_recursion_integration.py
16 passed in 0.68s
```

Native guard regressions exercise normalized deny across all six target manual/smart/off and deny/approve combinations: fresh dangerous approval refused, permanent dangerous-command grant accepted, explicit floor beats the overlapping grant, no approval queues. They evaluate guards without executing the dangerous commands; this is not a filesystem/runtime acceptance matrix. Historical tests cover off/bypass, both unattended approve postures, dangerous permanent grants and empty manual configuration, plus normalized resume fingerprint stability.

Affected-file Ruff, compilation, six-tool release-registration/validation-error handler smoke, `uv lock --check`, and `git diff --check` passed. First focused attempt had two test implementation failures (minimal fake context lacked CLI registration; minimal plugin venv lacked pydantic); both fixed and rerun green, no dependency changes.

The live `execute_code` batched-read attempt returned `BLOCKED: execute_code is disabled by profile-delegate child approval policy.` No execute_code retry or equivalent interpreter batching workaround. Existing permitted file tools and focused repository validation used; live frozen deny unchanged.

**Remaining gates:** after harness ownership finishes, controller must run complete frozen warnings-as-errors suite (including delegated Reviewer lineage), whole-tree Ruff/compile and final diff/registration checks; obtain isolated real TUI resume/stored-workspace receipt and complete CLI/TUI four-mode public-handler tool/filesystem matrix; independent re-review. No runtime matrix, full release gate, activation, or acceptance is claimed by this fix delegate. Incoming work preserved; other Builder's harness/usage files not edited. Concurrent index staging was observed but not performed or altered by this delegate.
