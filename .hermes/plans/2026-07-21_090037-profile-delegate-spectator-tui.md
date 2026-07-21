# Profile Delegate Spectator TUI Implementation Plan

> **For Hermes:** Use `subagent-driven-development` to implement this plan task-by-task. After context compression, re-read this file; it is the implementation source of truth.
>
> **Plan-only artifact:** This document authorizes no production edits by itself.

**Goal:** Let a user launch an asynchronous `profile_delegate` run from Discord and observe bounded live progress from a terminal using a strictly read-only command. V1 persists lifecycle/tool metadata by default; assistant text is explicit opt-in because no regex can guarantee removal of secrets from free text.

**Architecture:** Keep the detached Profile Delegate worker as the sole owner of the child TUI Gateway JSON-RPC stdio channel. The worker projects an allowlisted, bounded event stream to private run artifacts (`events.jsonl` plus an enriched atomic `status.json`); a plugin-owned terminal command renders those artifacts without opening child stdin, `control/`, `state.db`, or the TUI transport. No Hermes-core changes, network listener, shared daemon, or second RPC consumer.

**Tech Stack:** Python 3.13 runtime with Python 3.10-compatible syntax, Hermes plugin CLI registration, newline-delimited JSON, atomic JSON snapshots, ANSI terminal rendering using the standard library, pytest, Ruff.

**Execution Graph:** `T0 -> T1 -> T2 -> (T3 || T4) -> T5 -> (T6 || T7) -> T8`

---

## 1. Scope and product decisions

### User journey

1. Discord launches `profile_delegate(background=true)`.
2. The response includes a `task_id` and a copyable watch command.
3. In a terminal, the user runs:

```bash
hermes profile-delegate watch <task_id>
```

4. The spectator shows live lifecycle, phase, delegated profile, model/provider when available, elapsed time, authoritative counters, and allowlisted tool activity. Assistant-visible text appears only when `persist_message_text=true` was configured before launch.
5. The spectator exits when the run becomes terminal or the user presses `q`/`Ctrl+C`; neither action affects the delegated run.

### V1 command contract

```bash
hermes profile-delegate watch <task_id>
hermes profile-delegate watch <task_id> --hermes-home <caller-hermes-home>
hermes profile-delegate watch <task_id> --runs-root <exact-runs-root>
hermes profile-delegate watch <task_id> --jsonl
hermes profile-delegate inspect <task_id> --json
```

Preferred normal command:

```bash
hermes profile-delegate watch pd_20260721_085059_dzk2o9
```

Root precedence is normative and must match `core.get_runs_root()`: explicit `--runs-root`, then `PROFILE_DELEGATE_RUNS_ROOT`, then explicit `--hermes-home`, then active `HERMES_HOME/profile_delegate/runs`. `--hermes-home` means the caller profile's Hermes home, never the delegated profile home. Do not auto-scan homes. For a named caller profile, the returned hint is `hermes -p <origin_profile> profile-delegate watch <task_id>`; default remains `hermes profile-delegate watch <task_id>`. V1 omits `list`: provenance-free global discovery is unnecessary and too easy to get wrong.

### Read-only invariant

The spectator process may read only:

- `<run>/status.json`
- `<run>/events.jsonl`
- `<run>/result.json`
- bounded, already-sanitized metadata from `<run>/request.json` only if required for backward compatibility

It must never:

- open or write `<run>/control/**`;
- call `session.resume`, `session.status`, `session.steer`, `session.interrupt`, or any TUI RPC;
- attach to the worker PID or transport PID;
- read the child profile's `state.db` for live rendering;
- modify lifecycle, notification, result, or run artifacts;
- expose raw prompt/context, reasoning deltas, tool arguments, full tool results, credentials, or approval input.

### V1 event visibility

Persist and render by default:

- lifecycle and phase changes;
- `message.start` / `message.complete` metadata with no text;
- `tool.start` / `tool.complete`: normalized tool class/name, duration, and `complete|unknown`; never infer success from result text;
- `session.info`: delegated profile, model, provider, token/API-call usage when emitted;
- `status.update`: allowlisted status kind, not arbitrary raw text;
- terminal completion/error/interruption metadata;
- sequence number and timestamp.

Never persist by default:

- `thinking.delta` or hidden reasoning;
- raw JSON-RPC frames;
- prompts, context, output contracts, steer/cancel text;
- tool arguments or complete results;
- arbitrary status text;
- environment variables, paths discovered inside tool payloads, secrets, or approval command/code content.

### Optional message-text policy

- Configuration: `PROFILE_DELEGATE_PERSIST_MESSAGE_TEXT`, default `false`; freeze its effective boolean into `request.json` at launch. It cannot be toggled mid-run.
- When false, drop all `message.delta` text and `message.complete.text`; retain only start/complete metadata and counters.
- When true, persist only assistant-visible text after: removing ESC/CSI/OSC and all C0/C1 controls except newline/tab; replacing invalid Unicode; bounding each fragment and aggregate message; and applying clearly labelled best-effort secret-pattern redaction.
- Opt-in text is sensitive derivative data. Never claim it is secret-free: the model may repeat private material and secrets may be split across deltas. Coalescing/redaction therefore runs on the aggregate bounded message buffer, not each token independently.
- The renderer repeats control-character neutralization even though the journal is already projected.
- `message.complete` must not duplicate text already persisted from deltas; it closes the message and may supply text only when no deltas were retained.

### Counter definitions

- `turn_count`: increment on a matching `message.start`; reconcile with `message.complete`, never infer from arbitrary deltas.
- `api_calls`: use authoritative usage/session metadata when available; otherwise display `unknown`, not a fabricated count.
- `tool_calls`: increment on unique `tool_id` at `tool.start`; duplicate/replayed events must not double count.

### Out of scope

- General spectator attach for arbitrary Hermes Discord/Telegram sessions.
- Remote browser/SSE/WebSocket observation.
- Interactive steering/cancellation from the spectator.
- Persisting or rendering private reasoning.
- Hermes-core edits.
- New process supervisor, IPC daemon, socket, FIFO, or transport abstraction.
- Windows support beyond graceful unsupported behavior in V1 if filesystem-follow semantics differ.

## 2. Options considered

### A. Worker-owned sanitized journal + read-only plugin CLI — chosen

- Preserves the current single-owner RPC model.
- Requires only Profile Delegate changes.
- Reconnects from durable sequence numbers.
- Makes privacy policy explicit before disk persistence.

### B. Attach a second client to TUI stdio — rejected

`TuiRpcClient` is single-owner and correlates responses with interleaved events. A second reader can steal frames, break request correlation, and corrupt control/completion behavior.

### C. Resume the child Hermes session in another TUI — rejected

This creates a second active writer against the same logical session and is not observation-only.

### D. Tail only `status.json` / `stdout.txt` — rejected as final design

Useful as backward-compatible fallback, but `status.json` only exposes the latest reduced activity and `stdout.txt` is written at completion. It cannot provide a meaningful live transcript.

### E. Hermes-core remote attach/broker — deferred

Would enable a broader product but adds authentication, transport lifecycle, compatibility, and cross-platform scope that this concrete Profile Delegate need does not justify.

## 3. Dependency and concurrency map

| Task | Depends on | Mode | Write surface | Produces |
|---|---|---|---|---|
| T0 Contract/design gate | none | sequential | this plan only | frozen V1 event/privacy/CLI contract |
| T1 RED contract tests | T0 | sequential | `test_event_journal.py`, fixtures only | failing tests for schema, sanitization, bounds, ordering |
| T2 Event journal and snapshot | T1 | sequential | new `event_journal.py`; `tui_runner.py`; `tui_rpc.py`; `core.py`; `test_event_journal.py`; targeted existing tests | durable sanitized event source |
| T3 Spectator renderer/CLI | T2 | parallel-wave-1 | new `spectator.py`, `cli.py`, `test_spectator.py` | read-only watch/inspect implementation |
| T4 Lifecycle/retention hardening | T2 | parallel-wave-1 | `core.py`, `test_profile_delegate.py` only; coordinate with T2 ownership transfer first | active-run prune safety, legacy fallback, artifact bounds |
| T5 Plugin integration | T3, T4 | sequential | `__init__.py`, `plugin.yaml`, `core.py`, registration/subprocess tests | `hermes profile-delegate ...` command and returned watch hint |
| T6 Documentation/release notes | T5 | parallel-wave-2 | `README.md`, optional `CHANGELOG.md` if present | operator/user documentation |
| T7 Automated and live verification | T5 | parallel-wave-2 | tests and run artifacts only; implementation only for discovered defects | proof from unit/integration/live runs |
| T8 Independent acceptance review | T6, T7 | sequential | review report; production files only for mandatory fixes | release verdict |

### Concurrency rules

- T3 and T4 may run in parallel only after T2 commits and ownership of `core.py` transfers to T4. T3 must not touch `core.py`.
- T6 and T7 may run in parallel because documentation and verification own non-overlapping write surfaces. T7 must stop and transfer ownership before patching any defect.
- Never run two implementation agents against `tui_runner.py`, `tui_rpc.py`, `core.py`, or shared tests concurrently.
- Reviewer work is read-only until all active writers finish.

## 4. Risk assessment

| Risk | Likelihood | Impact | Detection | Mitigation | Rollback | Owner/Gate |
|---|---|---:|---|---|---|---|
| Raw tool payload or free text is persisted unintentionally | medium | critical | adversarial projection tests; byte inspection over live run artifacts | positive allowlist; text off by default; never serialize raw frames; strict field bounds | revert journal integration, delete derivative journals, and review affected run IDs | T1/T2, T8 security gate |
| A spectator becomes a second RPC consumer/writer | low | critical | code review; test monkeypatches fail if RPC/control/write APIs are opened | spectator module has filesystem-read dependencies only; no import of `tui_rpc`; read-only invariant test | remove CLI registration; existing worker remains unaffected | T3, T8 architecture gate |
| Partial/torn JSONL line crashes watcher or loses progress | medium | medium | fault-injection tests with partial final line and concurrent append | one encoded line per append, flush, monotonic `seq`; reader retains incomplete tail and retries | fall back to atomic `status.json`; terminal `result.json` remains canonical | T1/T2/T3 |
| Event volume causes disk or rendering blow-up | medium | high | size-bound tests; long-delta smoke; run artifact size inspection | coalesce `message.delta` by time/size; cap journal bytes/events; preserve terminal event; emit truncation marker | disable message deltas and continue status-only; prune affected run artifacts | T2/T7 |
| Duplicate/reordered events corrupt counters | medium | medium | replay/out-of-order fixtures | unique `seq`; tool ID dedupe; authoritative usage beats inferred counts; counter reconciliation | display counters as unknown and preserve lifecycle/result | T1/T2 |
| `status.json` and journal disagree around terminal races | medium | high | cancellation/completion race tests; terminal live smoke | terminal lifecycle remains canonical in status/result; journal is observability only; immutable terminal outcomes | watcher trusts `status.json`/`result.json` and flags journal lag | T2/T4/T7 |
| Prune deletes an active run while watched | low-medium | high | prune/watch concurrency test | prune skips active/cancelling runs; terminal deletion uses rename/tombstone; watcher exits cleanly on disappearance | restore from retained run directory if rename occurred; report not-found without touching worker | T4 |
| Wrong runs root exposes or misses runs | medium | high | explicit wrong-home/root and named-profile tests | exact precedence: `--runs-root`, env override, `--hermes-home`, active home; validate UID/mode; no broad auto-scan | user reruns with the correct caller profile/root; no mutation occurred | T3/T5 |
| Local user can inspect another origin's private run | low on personal host, medium on shared host | high | permission/UID tests and threat-model review | retain 0700/0600; reject symlinks; same-UID baseline; document that local OS account is trust boundary; optional origin/token deferred | disable CLI on shared host; restrict runs root permissions | T3/T8; residual risk accepted for single-user V1 |
| Plugin CLI registration API differs across Hermes versions | low | medium | command discovery and `--help` smoke | use existing `ctx.register_cli_command`; no core patch; version requirement documented | retain model-callable status tools and direct module diagnostic command only if needed | T5/T7 |
| Opt-in message deltas expose sensitive assistant text | low-medium | high | privacy review with split-secret and real delegate samples | default off; explicit launch-time opt-in; aggregate neutralization/redaction; honest warning that redaction is best-effort | revert opt-in/journal integration and delete derivative journals | T0/T2/T8 |
| Additional writes slow high-volume delegates | low-medium | medium | timing benchmark against the pre-feature baseline | buffered/coalesced appends; no `fsync` per token; atomic snapshot at bounded cadence | revert journal integration; worker completion path remains canonical | T2/T7 |
| A Hermes-core event shape changes | medium over time | medium | unknown-event tests and live smoke | versioned projection, ignore unknown fields/events, never fail delegated run because observability failed | mark spectator degraded while worker continues | T2/T7 |
| ANSI/OSC/control injection reaches the terminal | medium | high | adversarial C0/C1/CSI/OSC fixtures in projector and renderer | text off by default; neutralize before persistence and again before rendering | force plain metadata-only mode; delete derivative journal | T1/T2/T3/T8 |
| Concurrent status writers lose fields | medium | critical | startup/cancel/complete/notification race tests | all `status.json` read-modify-write uses one per-run `status.lock` and merge helper; terminal fields immutable | journal degrades; canonical result remains | T2/T4/T8 |
| Worker dies while status remains running | medium | medium | stale PID fixture and live killed-worker smoke | spectator labels stale and exits 4 after a 2 s confirmation window; never signals worker | inspect canonical artifacts manually | T3/T7 |
| Journal reopens after crash/partial line | medium | high | partial-tail/reopen and seq recovery tests | truncate only incomplete tail under journal lock; recover last complete seq | status-only fallback | T1/T2 |
| CLI handler return code is discarded | high without explicit handling | medium | real subprocess return-code tests | leaf handler raises `SystemExit(code)`; no Hermes-core change | direct module diagnostic only during rollback | T3/T5/T7 |
| Prune races a terminal transition or follows symlink | low-medium | critical | concurrent prune/transition fixtures | fail-closed terminal allowlist, shared run lock, no symlinks, atomic tombstone rename | leave candidate untouched and report skipped | T4/T8 |

### Residual risks accepted for V1

- Same local OS user can read private run artifacts; this matches the plugin's current local-power-user security model.
- A hard crash can lose the last buffered/coalesced opt-in text, but canonical terminal status/result must remain intact.
- Runs created before this release have status-only observation and final output fallback.

### Stop conditions

Stop implementation and escalate rather than widening scope if:

- live message/tool events cannot be projected without raw sensitive payload persistence;
- plugin CLI registration requires a Hermes-core patch in the supported runtime;
- journal I/O materially delays or destabilizes child completion;
- preserving process cleanup and terminal race semantics would require a second worker/control architecture.

## 5. Artifact contracts

### `events.jsonl`

Path:

```text
<effective-runs-root>/<task_id>/events.jsonl
```

`effective-runs-root` follows the exact precedence defined in §1 and `core.get_runs_root()`; it is not necessarily under `HERMES_HOME`.

Each line:

```json
{
  "schema_version": 1,
  "task_id": "pd_20260721_085059_dzk2o9",
  "seq": 42,
  "at": "2026-07-21T08:53:10.068648+00:00",
  "type": "tool.complete",
  "phase": "model_running",
  "payload": {
    "tool": "search_files",
    "duration_s": 1.42,
    "outcome": "ok"
  },
  "redacted": false,
  "dropped_fields": ["args", "result"]
}
```

Rules:

- UTF-8, one compact JSON object per newline.
- `seq` starts at 1 and increases exactly once per persisted projected event.
- Payload keys are event-type-specific allowlists.
- Unknown event types are ignored or projected to bounded generic lifecycle metadata; raw payload is never copied.
- Journal failure degrades observability only. It must not fail or cancel the delegated run.
- File mode `0600`, containing directory `0700`, reject symlink destination.

#### Normative limits and durability algorithm

- Defaults: `max_bytes=1_048_576`, `terminal_reserve_bytes=4_096`, `max_events=10_000`, `max_record_bytes=16_384`, `max_text_fragment_chars=2_048`, `max_message_chars=32_768`, coalescing window `100 ms` or `4_096` chars, whichever occurs first.
- `max_bytes` includes newlines. No ordinary record may consume the terminal reserve. At the first cap/event-limit breach, flush pending text, append exactly one bounded `journal.truncated` marker if it fits outside the reserve, then drop later non-terminal records.
- A bounded terminal record is always attempted from the reserve. If even the minimal terminal record cannot fit, set snapshot degradation and rely on canonical `status.json`/`result.json`; never rewrite valid earlier records to fake room.
- Open with `os.open(O_WRONLY|O_APPEND|O_CREAT|O_NOFOLLOW, 0o600)`, then `fstat` and reject non-regular files or wrong UID. All journal recovery/appends use `<run>/events.lock` with `flock`.
- On reopen, scan backward for the last complete newline, truncate only an incomplete tail under lock, validate the final complete record, and recover its `seq`; corrupt complete records cause metadata-only degradation rather than destructive repair.
- Flush a pending message buffer before any non-delta record so visible order is stable. One append call writes one fully encoded record plus newline; oversized projected records are reduced to a bounded `event.dropped` marker.
- Buffered writes may flush on the coalescing interval; never `fsync` per token. Force flush and `fsync` on journal close and terminal finalization. Disk/full/permission failures set observability degraded under the status lock and never escape into delegate execution.

#### Normative projected schema

Common fields are exactly `schema_version`, `task_id`, `seq`, `at`, `type`, `phase`, `payload`, `redacted`, `dropped_fields`. Unknown top-level/frame fields are discarded.

| Event | Allowed input | Persisted payload | Limits/transformation |
|---|---|---|---|
| `lifecycle` | plugin-owned lifecycle/phase | `status`, `phase` | enums only: running/cancelling/completed/failed/cancelled/timed_out and known phases |
| `message.start` | matching `session_id`, message id/role | `message_id`, `role=assistant` | IDs bounded 128; other roles dropped |
| `message.delta` | matching assistant text | `message_id`, optional `text` | record only with text opt-in; aggregate then neutralize/redact/bound/coalesce |
| `message.complete` | matching assistant status/text | `message_id`, `status`, optional fallback `text` | status enum; text follows opt-in and no-duplication rule |
| `tool.start` | tool id/name, timestamp | `tool_id`, `tool`, `tool_class` | IDs/name 128; class enum `file|web|shell|browser|delegate|other`; args dropped |
| `tool.complete` | tool id/name/timestamps | `tool_id`, `tool`, `tool_class`, `duration_s`, `outcome` | outcome `complete|unknown`; no result/summary/diff inspection; duration clamped 0..86400 |
| `session.info` | profile/model/provider and usage | `profile`, `model`, `provider`, `usage` | map server usage keys `input`, `output`, `reasoning`, `total`, `calls`; nonnegative integers only |
| `status.update` | `kind`, raw text | `kind` | allowlist known kinds; text always dropped |
| `journal.truncated` | plugin-owned | `reason`, `dropped_after_seq` | one marker maximum |
| `terminal` | plugin-owned canonical final state | `status`, `error_code`, `child_session_id` | emitted synthetically after canonical result/status write; no error prose |

Pre-session handling: before `ui_session_id` is known, accept only `gateway.ready` as non-persisted transport readiness and buffer at most 32 events/64 KiB. Once identity arrives, replay only matching-session frames and drop every other session. Overflow degrades observation without affecting execution.

### Enriched `status.json`

Add bounded optional fields while preserving compatibility:

```json
{
  "event_schema_version": 1,
  "event_seq": 42,
  "event_stream_truncated": false,
  "delegated_profile": "reviewer",
  "model": "codex/gpt-5.6-sol",
  "provider": "openai-api",
  "turn_count": 3,
  "api_calls": 4,
  "tool_calls": 6,
  "usage": {"input": 1234, "output": 456, "reasoning": 0, "total": 1690, "calls": 4}
}
```

Missing authoritative values are omitted or `null`; never infer fake precision.

### Status mutation and terminalization protocol

- Create `<run>/status.lock` mode `0600`. Every parent, worker, control, notification, journal-degradation, and terminal `status.json` read-modify-write acquires an exclusive `flock`, rereads the latest file, merges only owned fields, and atomically replaces it before unlock.
- Parent owns launch/provenance/`worker_pid`/notification fields; worker owns transport/session/phase/observability fields; terminal finalizer owns terminal status, ended/error/exit fields. A terminal state can never be replaced by a non-terminal state.
- The worker does not write status for each token. Snapshot cadence is at most once per 500 ms, plus forced writes for session identity, cancellation, degradation and terminalization.
- Startup handshake: parent writes initial status, starts worker, then under lock merges `worker_pid`; worker under the same lock may proceed without deleting parent fields.
- Finalization order: close transport; write canonical `result.json`; under status lock commit immutable terminal status; append/flush/fsync synthetic terminal event from those canonical values. Missing RPC terminal frames therefore cannot leave the journal hanging.
- Notification updates use the same lock helper. Lock acquisition failure or unsupported `fcntl` disables journal/spectator enrichment fail-closed; it must not weaken canonical existing execution behavior.

### Spectator output modes

- Default: interactive ANSI TUI if stdout is a TTY; plain incremental lines if not.
- `--jsonl`: emit the sanitized journal records unchanged and exit after terminal status.
- `inspect --json`: print one bounded snapshot and exit.
- No third-party TUI dependency for V1. Avoid dragging Textual/Rich into a five-file plugin unless the standard-library renderer proves inadequate.

### User- and agent-friendly help contract

`hermes profile-delegate -h` and `--help` are first-class discovery surfaces, not argparse afterthoughts. The root help must:

- state that the command is a local, read-only spectator and never attaches to or controls the child;
- show `watch` and `inspect` as the only V1 subcommands, each with a one-line purpose;
- include copyable examples for default home, named profile, `--jsonl`, and one-shot JSON inspection;
- explain task IDs, run-root resolution precedence, terminal exit codes `0..4`, default privacy (no assistant text), and `q`/`Ctrl+C` detach semantics;
- point agents to `inspect --json` for bounded machine-readable state and `watch --jsonl` for streaming sanitized records;
- keep stdout for successful help/data and stderr for errors, with no ANSI when non-TTY.

Leaf help (`watch -h`, `inspect -h`) must document every option, defaults, resolution behavior, safety boundary, output mode, and exit-code implications. Parser errors must remain concise and actionable.

## 6. Implementation tasks

### T0: Contract and independent design gate

**Objective:** Freeze the V1 event/privacy/CLI contract before production code.

**Execution:**
- Depends on: `none`
- Mode: `sequential`
- Write surface: this plan only
- Produces: approved event allowlist, counter definitions, bounds, and read-only invariant

**Steps:**

1. Reviewer inspects this plan plus:
   - `tui_runner.py:65-308`
   - `tui_rpc.py:121-305`
   - `core.py:246-331,1415-1513`
   - `/opt/hermes/tui_gateway/server.py` event emitters
   - `/opt/hermes/hermes_cli/plugins.py:504-525`
2. Challenge privacy, concurrency, and compatibility assumptions without proposing Hermes-core work unless a proven blocker exists.
3. Patch this plan for mandatory findings.
4. Gate: event payload allowlists, maximum journal size/coalescing policy, and same-UID trust boundary are explicit.

**Verification:** Reviewer returns `approve|changes_required` with exact path/symbol evidence.

**Commit:**

```bash
git add .hermes/plans/2026-07-21_090037-profile-delegate-spectator-tui.md
git commit -m "docs: plan profile delegate spectator TUI"
```

### T1: RED tests for event projection and journal semantics

**Objective:** Establish failing behavioral tests for sanitization, ordering, bounds, and crash tolerance.

**Execution:**
- Depends on: `T0`
- Mode: `sequential`
- Write surface: create `test_event_journal.py`; fixture files under test temp dirs only
- Produces: RED evidence for T2

**Files:**
- Create: `test_event_journal.py`
- Do not modify production files.

**Required tests:**

1. `tool.start` and `tool.complete` retain only bounded IDs/name/class, duration, and `complete|unknown`.
2. Raw args/results, prompt/context, reasoning, status text, paths from payloads, and secret-shaped fixture values never appear in default serialized output.
3. `thinking.delta` is dropped.
4. Message text is absent by default; opt-in text is coalesced without changing visible order, aggregate-redacted, bounded, and neutralized against C0/C1/ANSI/CSI/OSC.
5. Sequence numbers are monotonic and duplicate `tool_id` does not inflate counters.
6. Unknown/malformed events do not fail the run projection.
7. Crash/reopen truncates only a partial final line, recovers the last complete `seq`, and refuses destructive repair of a corrupt complete line.
8. Exact byte/event caps emit one truncation marker, preserve the terminal reserve, and reduce oversized records safely.
9. Symlink journal destination is rejected.
10. Observability write failure returns a degraded status signal but does not raise into the delegated execution path.
11. Pre-session events are bounded and only matching-session frames survive identity resolution.
12. Interleaved delta/non-delta records preserve order; terminal close force-flushes and fsyncs.

**RED command:**

```bash
PYTHONPATH=/opt/hermes .venv/bin/python -m pytest test_event_journal.py -q
```

Expected: failures caused by missing `event_journal` behavior, not fixture/import errors.

**Commit:**

```bash
git add test_event_journal.py
git commit -m "test: define spectator event journal contract"
```

### T2: Implement sanitized event journal and enriched snapshot

**Objective:** Make the existing detached worker emit a durable, bounded, privacy-safe live event stream while preserving worker ownership and completion semantics.

**Execution:**
- Depends on: `T1`
- Mode: `sequential`
- Write surface: create `event_journal.py`; modify `tui_runner.py`, `tui_rpc.py`, `core.py`, `test_event_journal.py`, and only targeted existing tests needed for compatibility
- Produces: `events.jsonl`, enriched `status.json`, passing journal tests

**Files:**
- Create: `event_journal.py`
- Modify: `tui_runner.py:88-103` (`persist_event`)
- Modify: `tui_rpc.py:263-281` or replace narrow `reduce_event` with projector delegation
- Modify: `core.py:1415-1428` (`base_paths` adds `events`)
- Test: `test_event_journal.py`, `test_tui_rpc.py`, targeted `test_profile_delegate.py`

**Implementation shape:**

```python
class EventJournal:
    def __init__(self, run_dir: Path, *, max_bytes: int, flush_interval_s: float): ...
    def project(self, frame: dict[str, Any]) -> dict[str, Any] | None: ...
    def append(self, event: dict[str, Any]) -> None: ...
    def flush(self, *, force: bool = False) -> None: ...
    def snapshot_fields(self) -> dict[str, Any]: ...
```

Keep projection/sanitization solely inside `event_journal.py`; `tui_rpc.py` remains transport-only. `tui_runner.persist_event` should:

1. apply the bounded pre-session buffer and matching `ui_session_id` filter;
2. feed the frame into the journal projector;
3. update status through the shared per-run lock/merge helper at the bounded cadence;
4. continue current `message.complete` final-text handling independently;
5. catch journal-specific errors, mark observability degraded, and continue the delegated run;
6. force a synthetic terminal record in `finally` after canonical result/status finalization.

**GREEN commands:**

```bash
PYTHONPATH=/opt/hermes .venv/bin/python -m pytest test_event_journal.py test_tui_rpc.py -q
PYTHONPATH=/opt/hermes .venv/bin/python -m pytest test_profile_delegate.py -q
```

Expected: all selected tests pass; no existing result/status/control tests regress.

**Inspection gate:** Search the serialized-event implementation and tests for forbidden keys (`args`, `arguments`, `result`, `prompt`, `reasoning`, `command`, `code`) and prove they are deny-tested rather than accidentally persisted.

**Commit:**

```bash
git add event_journal.py tui_runner.py tui_rpc.py core.py test_event_journal.py test_tui_rpc.py test_profile_delegate.py
git commit -m "feat: persist sanitized delegate progress events"
```

### T3: Build the read-only spectator CLI and renderer

**Objective:** Provide `watch` and `inspect` without any transport/control imports or writes.

**Execution:**
- Depends on: `T2`
- Mode: `parallel-wave-1`
- Write surface: create `spectator.py`, `cli.py`, `test_spectator.py`
- Produces: independently testable terminal UX

**Files:**
- Create: `spectator.py`
- Create: `cli.py`
- Create: `test_spectator.py`
- Do not modify: `core.py`, `tui_runner.py`, `tui_rpc.py`, `__init__.py`

**Functions:**

```python
def resolve_spectator_run(task_id: str, *, runs_root: str = "", hermes_home: str = "") -> Path: ...
def iter_events(path: Path, *, after_seq: int = 0) -> Iterator[dict[str, Any]]: ...
def inspect_run(run_dir: Path) -> dict[str, Any]: ...
def watch_run(run_dir: Path, *, output_mode: str, poll_interval: float) -> int: ...
def register_cli(parser: argparse.ArgumentParser) -> None: ...
def profile_delegate_cli(args: argparse.Namespace) -> NoReturn: ...  # raises SystemExit(code)
```

**Required behavior:**

- Validate `task_id` format and resolved path; reject traversal and symlinks.
- Detect non-TTY and use plain lines automatically.
- Reconstruct existing events, then follow new records from the last complete newline.
- Do not busy-loop; configurable bounded poll interval, default around 200 ms.
- Handle run completion, failure, cancellation, timeout, disappearance, journal truncation, and `Ctrl+C` without affecting the worker.
- Legacy run fallback: header/status updates plus final result/stdout when available; clearly label `limited observability`.
- Render no reasoning section because reasoning is not persisted.
- Unix TTY mode uses cbreak plus nonblocking `select`, restores terminal state in `finally`/SIGINT, redraws on SIGWINCH, and handles BrokenPipe. Non-TTY never reads keys and emits stable incremental lines.
- If `status=running|cancelling` but worker PID is dead, show `stale/degraded`, confirm for 2 seconds, then exit 4 without signalling or attaching.
- CLI leaf dispatch raises `SystemExit(code)` because Hermes currently discards ordinary handler return values.
- Return documented exit codes:
  - `0`: completed or user voluntarily detached;
  - `1`: failed/cancelled/timed_out terminal run;
  - `2`: invalid arguments/not found;
  - `3`: unauthorized/unsafe path;
  - `4`: corrupt/degraded artifact that prevents observation.

**Read-only tests:**

- monkeypatch `open`/`Path.open` and assert no write/append mode;
- assert module does not import `tui_rpc` or control helpers;
- snapshot output tests for running/completed/failed/legacy runs;
- partial line and reconnect-after-seq tests;
- `q`/`Ctrl+C` leaves run files byte-identical.
- root precedence/default/named-profile/wrong-home tests, with no auto-scan;
- ANSI/OSC renderer re-sanitization, resize, BrokenPipe, stale worker, and non-TTY tests;
- real subprocess tests assert stdout/stderr and return codes 0-4.

**RED then GREEN:** First add the tests above and run `pytest test_spectator.py -q`; expected RED is missing spectator behavior, not fixture/import failure. Implement only after capturing that RED result, then run the commands below to GREEN.

**Commands:**

```bash
PYTHONPATH=/opt/hermes .venv/bin/python -m pytest test_spectator.py -q
.venv/bin/ruff check spectator.py cli.py test_spectator.py
```

**Commit:**

```bash
git add spectator.py cli.py test_spectator.py
git commit -m "feat: add read-only delegate spectator CLI"
```

### T4: Harden retention, compatibility, and active-run races

**Objective:** Ensure pruning, legacy runs, and terminal races cannot damage active observation or delegated execution.

**Execution:**
- Depends on: `T2`
- Mode: `parallel-wave-1`
- Write surface: `core.py`, `test_profile_delegate.py`
- Produces: lifecycle-safe retention and compatibility behavior

**Files:**
- Modify: `core.py` only after T2 commits/transfers ownership
- Modify: `test_profile_delegate.py`

**RED first:** Add the race/prune tests below and prove they fail against the current implementation before modifying `core.py`.

**Required behavior/tests:**

1. `base_paths()` exposes `events` without breaking older consumers.
2. `profile_delegate_status()` surfaces safe event metadata and journal degradation/truncation, not message text.
3. `profile_delegate_prune()` is fail-closed: it considers only known terminal states; missing/corrupt/unknown/running/cancelling are always skipped.
4. Under the shared run lock, prune rereads terminal state, rejects symlinks/wrong UID, atomically renames to `.tombstone-<task_id>-<nonce>` outside the `pd_*` namespace, unlocks, then deletes only the tombstone. Watcher disappearance remains honest.
5. Final `status.json`/`result.json` remains canonical if journal ends early.
6. Completion vs cancellation retains existing immutable-terminal semantics.
7. Missing `events.jsonl` is compatible, not `corrupt` by itself.
8. Parent startup, worker snapshot, cancellation, completion, notification and journal-degradation writes preserve each other's owned fields under the status lock.
9. Cancel-vs-complete keeps terminal state immutable; disk-full journal failure cannot change the delegate result.

**Commands:**

```bash
PYTHONPATH=/opt/hermes .venv/bin/python -m pytest test_profile_delegate.py -q
```

**Commit:**

```bash
git add core.py test_profile_delegate.py
git commit -m "fix: harden spectator run lifecycle and retention"
```

### T5: Register the plugin CLI and expose the watch hint

**Objective:** Make the spectator discoverable through the supported Hermes plugin CLI mechanism and give Discord users a copyable command.

**Execution:**
- Depends on: `T3`, `T4`
- Mode: `sequential`
- Write surface: `__init__.py`, `plugin.yaml`, targeted `core.py` hint formatting, registration/subprocess tests
- Produces: installed `hermes profile-delegate` CLI surface

**Files:**
- Modify: `__init__.py:487-507`
- Modify: `plugin.yaml`
- Modify: `test_profile_delegate.py` registration assertions
- Modify targeted async response formatting in `core.py` only if needed to include `watch_command`

**Registration:**

```python
ctx.register_cli_command(
    name="profile-delegate",
    help="Inspect and watch Profile Delegate runs",
    setup_fn=register_cli,
    handler_fn=profile_delegate_cli,
    description="Read-only terminal spectator for delegated profile runs.",
)
```

`handler_fn` must call the leaf dispatcher that raises `SystemExit(code)`; returning an integer is forbidden because `/opt/hermes/hermes_cli/main.py` discards it.

**Async response addition:**

```json
{
  "task_id": "pd_...",
  "watch_command": "hermes profile-delegate watch pd_..."
}
```

Do not include shell quoting hazards or absolute private paths in the Discord-facing hint. For named caller origins, preserve the caller profile name already known at launch and emit `hermes -p <profile> profile-delegate watch pd_...`. Never derive the caller from the delegated target profile.

**RED then GREEN:** Before registration, add a fresh-process subprocess test proving the command is absent and exit behavior unavailable. After registration, rerun it for help plus return codes 0-4 and named/default hints.

**Commands:**

```bash
hermes profile-delegate --help
hermes profile-delegate watch --help
hermes profile-delegate inspect --help
PYTHONPATH=/opt/hermes .venv/bin/python -m pytest test_profile_delegate.py test_spectator.py -q
```

Expected: command discovery works in a fresh Hermes process; tool registration remains unchanged.

**Commit:**

```bash
git add __init__.py plugin.yaml core.py test_profile_delegate.py
git commit -m "feat: register profile delegate spectator commands"
```

### T6: Documentation and release metadata

**Objective:** Document the user flow, security boundary, compatibility, and operational limits.

**Execution:**
- Depends on: `T5`
- Mode: `parallel-wave-2`
- Write surface: `README.md`, `plugin.yaml` version field if release policy requires it, existing changelog only if present
- Produces: release documentation

**README sections:**

- Discord → terminal quickstart.
- Command reference and exit codes.
- Exactly what is and is not persisted.
- Same-UID/local-host trust boundary.
- Legacy run behavior.
- Retention/prune interaction.
- Troubleshooting wrong `HERMES_HOME` / named profile origin.
- Explicit statement: no Hermes-core changes and no direct attach to child TUI.

**Verification:** Commands in docs are copied into an isolated smoke and execute as documented.

**Commit:**

```bash
git add README.md plugin.yaml
git commit -m "docs: document delegate spectator workflow"
```

### T7: Full automated gates and live Discord-origin smoke

**Objective:** Prove the actual user journey and verify that observation cannot interfere with the worker.

**Execution:**
- Depends on: `T5`
- Mode: `parallel-wave-2`
- Write surface: test/run artifacts only; stop and transfer ownership before production fixes
- Produces: command output, run IDs, artifact/privacy inspection, process cleanup evidence

**Automated gates:**

```bash
PYTHONPATH=/opt/hermes .venv/bin/python -m pytest -q
PYTHONPATH=/opt/hermes .venv/bin/python -m py_compile __init__.py core.py child_bootstrap.py tui_rpc.py tui_runner.py event_journal.py spectator.py cli.py
.venv/bin/ruff check __init__.py core.py child_bootstrap.py tui_rpc.py tui_runner.py event_journal.py spectator.py cli.py test_profile_delegate.py test_tui_rpc.py test_event_journal.py test_spectator.py
git diff --check
git status --short
git diff --stat
```

**Live smoke matrix:**

1. Launch a harmless `profile_delegate(background=true)` from a Discord-origin gateway session.
2. Copy the returned `task_id` into `hermes profile-delegate watch <task_id>`.
3. Verify lifecycle and allowlisted tool rows appear before completion with tool progress explicitly enabled for the smoke. Separately run one opt-in-text smoke and one default text-off smoke.
4. Record run file hashes before/after spectator detach; only worker-owned artifacts may change.
5. Start two spectators against one run; both observe, neither affects completion or each other.
6. Detach one spectator with `q`/`Ctrl+C`; worker remains alive and completes.
7. Observe normal completion, controlled failure, cancellation, timeout, and an old run without `events.jsonl`.
8. Run with secret-shaped tool argument/result and split-delta text fixtures; inspect default and opt-in `events.jsonl` byte-for-byte. Default must contain no message text; opt-in is best-effort redacted and control-neutralized, not certified secret-free.
9. Confirm `control/` is absent or byte-identical before/after spectator use.
10. Confirm TUI worker/process group is reaped after terminal completion.
11. Confirm no Hermes source under `/opt/hermes` changed.
12. Run a stale-worker case and a prune-vs-terminal transition; watcher must exit honestly and prune must fail closed.
13. Exercise subprocess exit codes and wrong/named/default home resolution.

**Evidence to retain:**

- task IDs and child session IDs;
- exact watch commands;
- bounded terminal captures;
- `status.json`, `events.jsonl`, and `result.json` paths;
- file mode output;
- privacy grep result;
- process cleanup result;
- elapsed-time comparison journal enabled vs disabled/status-only if a flag exists.

**Acceptance thresholds:**

- No raw forbidden field in journal; default mode contains no assistant text.
- No failed/cancelled run caused by spectator or journal degradation.
- Terminal state appears within 1 second of canonical status on this local runtime.
- Idle spectator does not exceed 5% of one CPU core averaged over 30 seconds.
- Journal stays within configured cap and retains terminal metadata.

### T8: Independent acceptance review and release decision

**Objective:** Obtain an evidence-backed verdict after all writers and smokes finish.

**Execution:**
- Depends on: `T6`, `T7`
- Mode: `sequential`
- Write surface: review report; production files only for explicitly accepted mandatory fixes
- Produces: `approve|changes_required` release verdict

**Reviewer checks:**

1. Diff matches plan scope and changes only the plugin.
2. Spectator cannot import/use RPC, control, process-signalling, or write paths.
3. Event projection is allowlist-first and tested against secrets/raw payloads.
4. Race, bounds, legacy, prune, and degradation behavior are covered.
5. Live Discord-origin proof satisfies the user journey.
6. No core change is hidden in `/opt/hermes` or another profile.
7. Docs accurately state privacy and trust boundaries.

Mandatory findings are patched by one owner, then targeted tests and the affected live gate are rerun. Do not accept reviewer prose as proof without reading the diff and test artifacts.

**Final release command:**

```bash
git status --short --branch
git log -8 --oneline --decorate
```

Release only with clean intended worktree, passing gates, and verified commit lineage.

## 7. Acceptance criteria

1. A Profile Delegate run launched from Discord returns a copyable `task_id` and watch command.
2. `hermes profile-delegate watch <task_id>` displays useful progress before completion.
3. The worker remains the only TUI JSON-RPC owner and the spectator performs no writes or control actions.
4. Lifecycle, bounded tool metadata, profile/model/provider, and authoritative usage are shown when available; visible assistant text requires explicit launch-time opt-in.
5. Hidden reasoning, prompts/context, tool args/results, control text, and raw frames are never persisted or rendered. Default mode persists no free message text. Opt-in message text is explicitly sensitive and best-effort redacted, never advertised as secret-free.
6. Two spectators can observe one run concurrently without interference.
7. Detaching or crashing a spectator does not alter or stop the delegated run.
8. Journal corruption/truncation/degradation cannot fail the delegate; status/result remain canonical.
9. Active/cancelling runs cannot be pruned.
10. Legacy runs remain inspectable with explicitly limited observability.
11. Full pytest, compile, Ruff, diff checks, and live smoke matrix pass.
12. No Hermes-core files, shared daemon, network endpoint, or transport abstraction are added.
13. README documents the workflow and local trust/privacy boundary accurately.

## 8. Rollback strategy

### Fast rollback

No runtime feature flag is promised in V1. Rollback requires reverting/redeploying the plugin commits below. Remove CLI registration/hint first, then journal integration; preserve existing TUI worker, status, steer, cancel, result, and notification behavior. Legacy/new runs without a usable `events.jsonl` fall back to limited observation.

### Code rollback order

1. Revert T5 CLI registration/hint.
2. Revert T3 spectator files.
3. Disable or revert T2 event journal integration.
4. Keep the existing `dbb782a` live-control baseline intact.

### Data rollback

`events.jsonl` is derivative observability data. It can be pruned without affecting canonical session history or `result.json`. If any privacy leak is found, stop journal creation immediately, identify affected run IDs, delete derivative journals under the existing private runs root, and preserve only redacted evidence needed for the incident review.

### Core fallback rule

If implementation appears to require `/opt/hermes` changes, stop. The correct fallback is status-only observation plus terminal result—not a stealth core fork.

## 9. Definition of done

The feature is done when Alberto can launch Profile Delegate from Discord, paste one command into his terminal, observe meaningful live progress, detach safely, and trust that the spectator is incapable of steering, cancelling, corrupting, or leaking the delegated run. Anything less is a log tail wearing a TUI costume.
