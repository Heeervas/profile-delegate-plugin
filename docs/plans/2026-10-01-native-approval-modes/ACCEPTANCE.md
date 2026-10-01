# Native approval modes — final acceptance

Status: **READY_FOR_REVIEW / activation-ready local candidate**. No production activation authorized or performed. Builder implementation session retained: `20261001_092528_6cb685`.

## Acceptance matrix

| Criterion | Evidence / outcome |
|---|---|
| A1 selectors/target resolution | `test_native_selection.py`, `test_native_approval.py`; operator target map validated before allocation. No new environment selector API: installed project had no approval-selector env consumer. Global-env provenance guard preserves precedence if supplied through supported policy. |
| A2 migration | Historical omitted selector deny; explicit approve_yolo aliases yolo. `test_native_resume_admission.py`. New configuration default profile. |
| A3 target isolation | Fresh child installed-native guard tests; profile excludes caller grants/yolo; snapshots tested separately. |
| A4 exact inherit | Actual nested provider child `pd_20261001_101341_3brsk9`: caller grant only, target-only grant absent, parent + target denies retained, parent prohibition refused. Private `inherit-receipt.json`; no transient consent copied. |
| A5 native behavior | Real installed native manual/smart/off × approve/deny matrix, terminal/execute_code local vs isolated vs host-mounted, target git-push floor; `test_native_approval.py`. Smart unattended approve is not LLM screening. |
| A6 no unanswered waits | Provider simple `pd_20261001_094506_4g0g8r`, TUI `pd_20261001_094540_nwm8f1`: execute_code fresh consent refused, guard `approval_required`, worker blocked, TUI transport stopped. No workaround. |
| A7 scoped deletion | CLI `pd_20261001_091607_jdeu9a`, TUI `pd_20261001_091704_wvx3tu`: disposable create/test/delete + execute_code, fixture absent, exact receipt files present. No blanket deletion blacklist. |
| A8 authority | Explicit model override rejected by `validate_preflight`; target/depth admission regressions. Actual nested inherit child admitted; nested yolo rejected before any run artifact (`widening_probe.py`). Deny ancestry containment regressions and independent closure. |
| A9 lifecycle | Replay `pd_20261001_093659_stp9qt` and final revision `pd_20261001_104827_916d3v`: same child session, frozen fingerprint, actual SIGNED_REPLAY_OK, exit 0. Historical seeded cancelled attempts require observed evidence; requested intent alone cannot alter authority. Control `pd_20261001_094821_qdb66o` cancelled; worker/transport PIDs absent. Steer ACK remains delivery unknown, not delivery proof. |
| A10 safety | Native guard floors exercised under bypass; hooks separately authorized; non-Hermes production executable refuses unless literal fixture-only test_shim supplied; installed child policy before imports, no real-process fallback. No arbitrary-code sandbox claim. |
| A11 local release | Frozen lock/sync, final full `-W error` gate **599 passed in 65.96s**, Ruff, all Python compilation, registration/handler smoke, diff check. Security-pattern scan 91 intended/tracked files: no findings/forbidden paths. No commits/publication/core/prod changes. Incoming snapshot preserved. |

## Three independent evidence classes

### Behavior
Private root `/opt/data/profiles/builder/workspace/native-approval-modes/` contains `final-revision-gate.log`, `final-replay.log`, probe scripts and incoming snapshot. Disposable artifacts `/opt/data/profiles/builder/workspace/pd-native-approval-ooyelz4j/` contain receipts and exact run files; inspect actual guard events/status/files rather than worker summaries alone.

### Deterministic quality
`evidence/feature-quality.json`: **QUALITY_PASS at TOP**, no exceptions, no evidence gaps. Baseline `e4053cfededf327d42b58dca09d1b4e2dd7f0f28` is an immutable disposable local commit reconstructed from the incoming tracked patch/untracked snapshot, NOT a product commit. Collector `/opt/data/profiles/builder/workspace/native-approval-modes/measure_feature.py`; disposable baseline repo `/opt/data/profiles/builder/workspace/pd-incoming-quality-k_ecqz6y/repo`.

`evidence/measurement-policy.yaml` uses unchanged builder-assurance template thresholds; it is scoped measurement configuration, not installed repository governance. Historical HEAD-based `quality.json` remains FAIL because it also includes unrelated incoming continuity work. No thresholds lowered, human exceptions claimed or unrelated continuity refactored. Incoming oversized/complex functions remain reported debt. Native source/resume and launch extraction plus bootstrap decision/filter helpers remove feature-caused worsening while retaining surrounding core seams.

### Independent review
- Earlier `deleg_96425a7f/task-0`, `deleg_f0e29879/task-0`: concrete findings fixed; original reviews were not PASS.
- `deleg_96275bb8/task-0`: **PASS** historical evidence strict typing, no compression bypass, deny containment/resolution extraction.
- `deleg_44a4026d/task-0`: **PASS** final argv/config-helper refactor and model override refusal. Reused failed `deleg_0084765a` inspection after upstream HTTP 503; its failure was not approval.
- Handles: `/opt/data/profiles/builder/cache/delegation/live/<review-id>/task-0.log`.

## Scope and residual limitations

No production settings, gateways, credentials, Hermes core, publication or product commits changed. Private disposable baseline commits are measurement artifacts only. Native shell denial does not contain arbitrary Python/subprocess/MCP/API behavior. Nested admission intentionally permits frozen inheritance or deny, not arbitrary incomparable source switches. Unsupported transitions refuse before spawn. Smart unattended policy is deterministic native consent posture, not promised screening. Wrapper task-error code remains `target_reported_errors`; exact guard refusal classification is recorded in native approval events/results. Human approval relay, post-restart delivery guarantees and OS sandboxing remain out of scope.

Activation and non-destructive rollback: `OPERATOR.md`.
