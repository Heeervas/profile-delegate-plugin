# Opt-in actual-runtime harness (controller execution required)

## Native grant fixture diagnosis (latest)

Controller probe `.artifacts/task-approval-runtime-18li0hav` passed real refusal/absent-file checks. Matrix `.artifacts/task-approval-runtime-l0r2u1qi` stopped at cli-deny-target-grant. Response/request preserved the exact permanent command grant, but installed `/opt/hermes/tools/approval_floors.py:144-204` rejects command-text allowlist shortcuts when quoted control characters occur in reinterpreted `-c` arguments. The old Python payload contains semicolon and parentheses; exact text equality is insufficient. This is invalid fixture command shape, not evidence of lost plugin grants, and not an executable-only syntax requirement.

Fixture now issues flagged `python3 -c 'import acceptance_target_grant'` (analogous distinct modules per case). Harness preparation writes a tiny private marker module in the existing effects cwd; no operation is executed during preparation. Exact command grants remain disjoint; no broad script-execution key granted. Deny patterns also match module names so target/ancestor prohibitions remain effective. This prepares new explicitly authorized isolated cases, not retrying the failed operation. No runtime harness execution under delegated ancestry.

Focused installed-native matching/detection and existing approval/selection regressions: **53 passed in 23.21s**; whole-tree Ruff, harness/test compilation and diff check passed. Full 640-test prior production gate reused: no production source changed. New `test_runtime_fixture_commands.py` verifies flagged detection, noncompound shape, exact native allowlist matching, preparation creates no marker, and old shape rejection. Controller must rerun fresh probe/matrix; matching tests do not prove filesystem execution.

## Minimal post-probe repair

Controller probe `.artifacts/task-approval-runtime-18v6g72s` failed HTTP400 `missing explicit fixture action; no tools issued`. Its installed-runtime request dump shows the user message was exactly `@file:/opt/data/plugins/profile-delegate/.artifacts/task-approval-runtime-18v6g72s/runs/pd_20261001_221206_ej2ldo/prompt.txt`, not inline task content. Provider parsing now resolves only `prompt.txt` references within its own run root, bounded to 1 MB, before parsing the explicit action marker. No new provider framework or guard/tool simulation. Inline TUI content remains supported.

Resume cases now use the existing operation/public-handler path for both CLI and TUI, checking frozen envelope equality and identical durable session id. Installed TUI contract accepts no cwd in session.resume; plugin regression covers that emitted payload. Runtime harness was NOT executed from Builder's delegated ancestry; guards and environment remain intact. Controller must rerun the narrow probe before matrix.

Ruff now extends exclusions with `.artifacts` (generated evidence, not source); existing lint rules and artifacts preserved. Latest canonical gate: **640 passed in 102.24s**, frozen lock/sync, whole-tree Ruff, compilation (including harness), registration/handler smoke and diff check passed. These checks do not verify the HTTP parser repair or matrix end to end.

Owned new surfaces only:
- `scripts/accept_task_approval_runtime.py`
- this document

Source contract: `/opt/data/cache/documents/doc_9094ddb74402_astra-per-task-permissions.txt` and `PER_TASK_REPAIR.md`. No production implementation/existing-test edits. Existing `cli_smoke.py` was inspected; it calls core directly and lacks isolated fixtures, per-task selectors, tool-effect evidence, and TUI coverage, so it cannot satisfy this gate unchanged.

## Authority and exact controller commands

Run **only from a controller/operator process with the user's isolated testing authorization**, not from this frozen-deny Builder. The harness explicitly refuses a process containing `PROFILE_DELEGATE_APPROVAL_REQUEST` or `PROFILE_DELEGATE_PARENT_TASK_ID`, including its private driver entry. Do not unset either to get around a refusal.

From `/opt/data/plugins/profile-delegate`:

```bash
/opt/hermes/.venv/bin/python scripts/accept_task_approval_runtime.py --authorize-isolated-runtime --phase probe --hermes-bin /opt/hermes/bin/hermes
```

Inspect the printed artifact root and `receipt.json`, provider receipts, run request/status, approval events, and actual terminal tool response. The smallest real probe requires native refusal of a harmless flagged `python3 -c` write, zero resulting file, completed installed CLI launch, and an actual tool response. A provider/config/transport failure is a failure, NOT a refusal PASS. Do not proceed after a failed probe without diagnosis/review.

Then:

```bash
/opt/hermes/.venv/bin/python scripts/accept_task_approval_runtime.py --authorize-isolated-runtime --phase matrix --hermes-bin /opt/hermes/bin/hermes
```

Matrix repeats the narrow probe first and stops at the first unexpected result. `--timeout 180` is the per-child default, configurable. No full-suite invocation, restart, core edits, credential copies, external provider, publication, or live configuration mutation. `probe` and `matrix` each allocate a fresh private `.artifacts/task-approval-runtime-*` root. Run without Python `-O`: assertions are acceptance checks.

## What is real, what is simulated

**Explicit deterministic scripted MODEL/provider fixture:** a loopback OpenAI-compatible HTTP endpoint supplies one predetermined tool call, then echoes the **actual** tool result and ends. It supports streaming and nonstreaming chat completions. It does not generate fake tool results or filesystem evidence. Model output `status: ok` means the scripted turn ended; it is deliberately NOT an acceptance verdict. Controller checks use independently read files, launch status, approval events, and recorded real tool messages.

Real path: package-loaded public `_handler` → candidate core resolution/admission → candidate actual launch/bootstrap → installed `/opt/hermes` CLI or native TUI Gateway → installed terminal implementation/native guards → filesystem. Nested cases use the installed runtime's discovered `profile_delegate` tool to launch another real child. No mocked guard/tool/launch/resolution, shim entrypoint, or alternate command following refusal.

The parent driver is trusted test code calling the public Python handler, not a parent LLM turn. Child sessions, tool calls, CLI/TUI gateway, native approval decisions and effects are real. This proves handler/runtime behavior, not user-interface rendering or real-provider reasoning quality.

## Fixed fixtures and expected behavior

One fixed target profile/config is used throughout both transports; its config SHA-256 must remain unchanged after every ordinary case. All effects are markers under the fresh artifact root, using `python3 -c` with no external destinations, deletion, or shell command chains. Permanent grants are exact command-text grants, not the broad interpreter detector key.

Primary caller: manual / unattended and single-query **approve**, exact caller-marker permanent grant, ancestor-marker deny. Target: manual / unattended and single-query **deny**, different exact target-marker permanent grant, target-marker explicit deny. Selection grant `allow_child_approval_override: true` exists ONLY in disposable caller config. Separate strict caller has deny posture with the caller grant; unauthorized caller has false selection grant.

| Selector | Fresh flagged write | Target grant | Caller grant | Explicit target deny |
|---|---|---|---|---|
| deny | refuse | allow | refuse | refuse |
| profile | refuse | allow | refuse | refuse |
| inherit | allow (caller approve posture) | allow (caller approve posture, NOT inherited target grant) | allow | refuse |
| yolo | allow | allow | allow | refuse |

Strict-caller `inherit`: caller grant allowed, target grant refused. This disambiguates permanent-grant inheritance from unattended approve. Caller explicit prohibition is checked under inherit. Each case runs on CLI and background native TUI, without rewriting target permissions.

Additional executable cases:
- `approve_yolo` alias and omission through actual launch on both transports;
- empty/unknown/wrong-type selectors: actionable validation error and no run allocation;
- unauthorized profile/inherit/yolo requests: explicit authority refusal and no run allocation;
- unauthorized deny narrowing: real launch/refusal;
- real deny seed session, attempted yolo reselection rejected, omitted selector resumes the exact frozen deny envelope and repeats native refusal;
- installed nested tool: deny→yolo and yolo→profile rejected; yolo→inherit allowed; yolo→deny and deny→deny narrowed/refused.

The scripted provider never substitutes another operation after a tool refusal. A refusal ends that child turn. Later matrix cases are distinct explicitly requested tasks, not retries. The harness deletes only its own completed marker before the next distinct task; no child deletion probes are used.

## Evidence and assumptions

Artifact root printed immediately after opt-in:
- `receipt.json`: harness status, phase, matrix completeness; absent/failed is never PASS;
- `matrix.json`: expected/observed effects, exact call/run paths, native envelopes, actual tool results, approval events. `complete: true` only after every assertion succeeds;
- `provider-receipts.json`: issued tool arguments, discovered actual tool names, actual tool result messages (no HTTP headers recorded);
- `calls/*.json`, `*.response.json`, `*.driver.log`, TUI `*.notification.json`;
- `runs/*`: real plugin request/status/result/stdout/stderr/events;
- `homes/`: generated YAML, isolated native state.db, generated profile identity, symlink to candidate plugin;
- `effects/`: independently checked real marker writes.

Environment is constructed from an allowlist rather than inherited wholesale; no API credentials or production session/approval variables are copied. Model placeholder `no-key-required` is public dummy data. OS HOME/TMPDIR and every profile home are inside the artifact root. The installed runtime and plugin repository are read dependencies, not write targets. This is NOT an OS sandbox; native core/model/tool behavior can still have bugs. All fixtures are private and retained for inspection; do not commit `.artifacts`.

Assumptions to resolve through the first probe: installed `/opt/hermes/bin/hermes` and `/opt/hermes/.venv/bin/python` exist; installed Python has YAML/Hermes dependencies; bare custom-provider chat-completions config routes to loopback; exact `python3 -c` is flagged and executable; native profile identity recognizes generated config; tool-search can be disabled in disposable config; installed plugin discovery exposes `profile_delegate` in delegation toolset. Missing schemas or protocol drift fail closed rather than replacing native components.

TUI background requests use `notify_on_complete: true`, native schema/ledger registration, and local synthetic CLI origin only. Each records and asserts a persisted actual native completion payload. No external channel exists and no external messages are sent. This does **not** claim a user consumed/rendered notification. Both CLI and TUI deny resume use the existing public-handler launch path and assert frozen authority plus durable session continuity. The plugin's repaired session.resume payload omits cwd and other creation-only fields; the harness does not work around the installed contract.

Nested accepted cases verify actual child terminal results/effects and refusal cases verify real tool refusal. They do not exhaust every ancestor-policy permutation or transient consent/hook-consent path. Existing independent regression/review gates remain required. Provider/header secrecy is protected by the clean environment, not a general-purpose log scrubber.

## Preparation validation

Permitted preparation checks only (runtime NOT run by frozen-deny Builder):

```bash
uv run --frozen ruff check scripts/accept_task_approval_runtime.py
uv run --frozen python -m py_compile scripts/accept_task_approval_runtime.py
git diff --check -- scripts/accept_task_approval_runtime.py docs/plans/2026-10-01-native-approval-modes/RUNTIME_HARNESS.md
```

Prepared harness is not installed-runtime evidence. Controller must inspect, execute narrow probe then matrix, and pass the resulting artifacts to independent Reviewer before acceptance.
