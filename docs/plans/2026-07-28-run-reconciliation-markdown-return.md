# Run reconciliation and Markdown return repair

**Status:** implemented and validated; activation/live mutation not performed

**Goal:** stop dead detached workers from remaining authoritative `running` records, and stop successfully completed explicit Markdown reports from being announced as execution errors, without deleting run evidence, touching live processes, or weakening strict wrapper success.

**Approach:** add one locked, conservative reconciliation operation and repair the already-demonstrated Markdown/notification semantics. Keep ordinary status/list reads non-mutating; keep prune separate and terminal-only.

**Evidence:**

- `pd_20260727_220206_aokwr9`: detached TUI status stayed `running`; worker PID `113903` and transport PID `113906` are absent; no `result.json`; events stop at tool start seq 103; a later cancel command has no acknowledgement. This proves missing dead-worker reconciliation, not cancellation.
- `pd_20260728_111404_qmz7z4`: `message.complete(status=complete)` and terminal `completed`, gateway exit `0`, full Markdown in `stdout.txt`, and `result.json` persisted. The report begins `PASS — ...`, but the text-status grammar only accepts exact `OK|BLOCKED|FAILED`; it became task `unknown`, wrapper success false, and `_push_profile_delegate_completion()` converted that into async event `status=error`. Serialization and TUI close succeeded.
- Historical inventory: 49 explicit Markdown runs include 39 completed runs; JSON, Markdown, and text all traverse the same TUI close/persist path. No format-specific transport failure pattern was found.

**Execution graph:** `T1 -> T2 -> T3 -> T4 -> T5`

## T1 — Add sanitized real-run regressions

**Write surface:** `tests/fixtures/profile_delegate/`, `test_reliability_reset.py`, `test_tui_rpc.py`, new focused reconciliation test file if clearer.

- Add a sanitized Markdown report derived from `pd_20260728_111404_qmz7z4`.
- Add sanitized modern stale/pending-cancel status/control test builders derived from `pd_20260727_220206_aokwr9`.
- Establish RED for explicit `PASS — detail` recovery, notification execution/result separation, dead-worker reconciliation, pending-cancel non-causality, live-worker protection, terminal-result authority, and legacy unknown no-op.

## T2 — Implement conservative reconciliation

**Write surface:** `core.py`, `__init__.py`, `plugin.yaml` only if a new operator tool is exposed.

- Add locked `reconcile_run(task_id)` with no process signalling and no deletion.
- Terminal `result.json` with a valid terminal `execution_status` projects terminal truth.
- Explicit interruption metadata projects `cancelled` with `terminal_reason=interrupted`.
- An acknowledged/accepted cancel may project `cancelled`; an unacknowledged late cancel never does.
- Verifiably absent modern detached worker with no terminal result becomes `failed/worker_died`; preserve event/control/stdout/stderr artifacts and write a bounded failure `result.json`.
- Live worker, PID with unverifiable identity, malformed evidence, and legacy records lacking enough liveness evidence remain unchanged with a structured `unknown/unverifiable` reconciliation outcome.
- Ordinary list/status remain read-only. Duplicate-guard candidate checks may invoke reconciliation under the existing narrow fingerprint/window path. Concurrency slots already use kernel locks and need no artifact cleanup.

## T3 — Repair Markdown result and notification semantics

**Write surface:** `core.py`, focused tests.

- Conservatively recognize one explicit Markdown/text terminal line `PASS|OK|BLOCKED|FAILED` with an optional short dash/colon detail; conflicting or negated statuses remain `unknown`.
- Keep wrapper success strict: completed execution + recovered explicit OK/PASS only.
- Build async completion event status from execution lifecycle, not wrapper success. A completed execution with task `unknown/blocked/failed` is still a completed delegation notification; the compact result carries the task/contract outcome. Transport/timeouts/cancellation remain error/cancel paths.

## T4 — Keep cleanup and retention separate

**Write surface:** docs/tests only unless prune safety needs a proven fix.

- Reconciliation never deletes.
- `profile_delegate_prune` remains explicit, dry-run by default, locked, and terminal-only.
- No pruning is run during this task. Recommended retention is documented, not activated: short terminal artifacts may be pruned by operator policy; unresolved/unknown and undelivered evidence stays protected until separately reviewed.

## T5 — Verification

Run:

```bash
PYTHONPATH=/opt/hermes .venv/bin/python -m pytest -q -o 'addopts=' <focused tests>
PYTHONPATH=/opt/hermes .venv/bin/python -m pytest -q -o 'addopts='
.venv/bin/ruff check .
.venv/bin/python -m py_compile __init__.py child_bootstrap.py cli.py cli_smoke.py core.py event_journal.py event_schema.py spectator.py tui_rpc.py tui_runner.py scripts/validate_release.py test_*.py
.venv/bin/python scripts/validate_release.py
git diff --check
git diff --stat
git diff
```

No gateway restart, push, tag, prune, or live run mutation is part of this task.

## Risks and controls

- **False terminalization / PID reuse:** never signal; absent PID is safe dead evidence; present PID without matching identity is no-op. Tests cover live and unverifiable cases.
- **False Markdown success:** accept only one non-negated explicit terminal token in a terminal-style line; conflicting statuses stay unknown.
- **Notification semantics regression:** execution lifecycle controls event completion/error; task and contract remain visible in result. Tests cover completed+ok/blocked/unknown and failed/timed-out/cancelled.
- **Legacy corruption:** legacy records without sufficient evidence are projected as unverifiable and not rewritten.
- **Evidence loss:** no deletion; all original files remain. Reconciliation writes only locked additive/final status/result artifacts.
