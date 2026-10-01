# Builder execution blocker

Status: BLOCKED_WITH_EVIDENCE. No feature source/test implementation or acceptance claim.

## Observed operation

During T0, native terminal was asked to snapshot incoming tracked diff and untracked files into `/opt/data/profiles/builder/workspace/native-approval-modes/incoming` using a Python `-c` script. The script would only read Git state and copy repository files into a new private workspace directory.

Tool result:

```text
exit_code: -1
status: blocked
BLOCKED by profile-delegate deny policy: script execution via -e/-c flag
```

The snapshot did not execute. Builder did not retry using another interpreter/tool, modify policy, or bypass this refusal. T1's actual native-boundary integration probe was not executed. T2–T7 and acceptance A1–A11 remain unverified. No full gates, deterministic quality report, delegated integration IDs, or final independent code review were produced.

## Baseline inspection

Read `PLAN.md`, package `STATE.md`/`REVIEWS.md`, repository `README.md`, `BRIEF.md`, `STATE.md`, `TODO.md`, accepted reliability plan, `.agents/validation.md`, `.agents/skill-routing.md`, architectural decision 0001, `.hermes/handoff.md`, plugin `child_bootstrap.py`, and installed native approval/context code (read-only).

`pwd && git status --short && ps -eo pid,args` succeeded (exit 0). Incoming tracked dirty paths: `STATE.md`, `__init__.py`, `core.py`, `test_profile_delegate.py`, `test_tui_rpc.py`, `tui_rpc.py`, `tui_runner.py`. Incoming untracked surfaces: detached-notification-owner-handoff plan, compression-session-continuity plan, this approval-modes package, and `test_compression_continuity.py`. No overlapping implementation writer was visible beyond this delegated worker; controller declared source ownership transferred. Incoming source files were not edited.

Loaded skills: `hermes-agent`, `builder-engineering-rules` plus Code Complete mini, `builder-assurance`, `test-driven-development`, `requesting-code-review`. Project execution-primary `hermes-plugin-tool-authoring` is unavailable in Builder; documented fallback is the installed Hermes skill plus repository contracts. This missing skill was not the execution blocker.

## Required recovery

Controller/operator must restart this bounded task through an already operator-authorized execution posture permitting the baseline script, installed-native subprocess probes, canonical gates, and disposable provider-backed integration lifecycle. Do not ask the child/model to change its own policy or route the denied operation through another tool. No production/global policy widening is authorized here; choose a scoped authorized dispatch, or obtain explicit operator approval for the necessary change.

Activation candidate: none implemented. Rollback: no source changes to roll back; retain incoming continuity work and this blocker receipt. No production config, core write, deployment, restart, commit, push, tag, or publication performed.
