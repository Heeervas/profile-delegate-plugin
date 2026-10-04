# Profile Delegate 🤝

Version: `1.10.1`

Delegate to specialist Hermes profiles from one conversation. Keep each specialist's context separate, follow live runs, and reuse nested results such as a Builder's Reviewer report.

## What's new in v1.10.1

This tagged release packages the published reliability work and contributor-ready repository:

- Connected nested results, same-session recovery, and clearer live-control evidence.
- Native background completion tracking with separate notification outcomes.
- Hardened approval, origin and managed-scope admission checks.
- Tests under `tests/`, plans and reviews under `docs/`, and reconciled project contracts.
- 716 retained test cases; portable CI on Python 3.11–3.13 and installed integration on Python 3.14.

See [CHANGELOG.md](CHANGELOG.md) for details and [contribution opportunities](docs/contribution-opportunities.md) for concrete open work. Profiles are context boundaries, not security sandboxes; notifications remain best effort.

### Release policy

Every release must align `plugin.yaml`, `pyproject.toml`, this README and the changelog, pass CI on its exact commit, and have an annotated `vX.Y.Z` tag. Historical untagged checkpoints are not retroactively certified releases.

> Stable local-power-user Hermes Agent plugin. It is **not a sandbox** and should be configured deliberately before broad use.

A Hermes Agent plugin for bounded, model-callable delegation between Hermes profiles.

Instead of opening a Kanban board or running a second long-lived gateway, `profile_delegate` lets one profile ask another profile to perform a focused task and return a compact structured result.

Example uses:

- Ask a `reviewer` profile to critique a plan.
- Ask a `builder` profile to inspect implementation risk.
- Ask a `research` profile to check public sources.
- Ask a domain profile to produce a second opinion without mixing its memory into the caller.

## Features

- Model-callable `profile_delegate` tool.
- Runs the target profile with its normal Hermes context, memory, rules, tools, and model defaults unless a temporary per-call override is requested.
- Supports requested per-call `model`, `provider`, `reasoning_effort`, `max_turns`, `toolsets`, preloaded `skills`, and `review`/`build` capability presets; omitted values inherit profile defaults.
- Launches Hermes in-process through a plugin-owned bootstrap before agent construction. The bootstrap binds frozen native approval-source policy and optional schema filtering, then runs quiet single-query mode with a prompt file reference. Operator `yolo` (legacy `approve_yolo`) enables ordinary bypass; hooks remain separately authorized.
- Foreground mode waits synchronously and keeps the originating turn occupied. Short bounded specialist work can remain foreground. Prefer background mode for long, multi-stage, or independently monitorable work when the conversation should remain responsive. This is advisory only; the plugin does not auto-select, reject, or impose a new duration cap on either mode.
- Explicit target-profile allowlist by default.
- Recursion/depth guard via `PROFILE_DELEGATE_MAX_DEPTH`. A top-level self-target is permitted by profile policy; nested same-home calls are refused explicitly even when spare concurrency slots exist. Cross-home nesting remains subject to depth and the shared configured lock capacity.
- Direct nested-delegation lineage and result surfacing: a child run created through `profile_delegate` is linked to its parent and returned under `result.nested_delegations`, so the controller can reuse a builder's reviewer result instead of paying for the same review twice.
- Global concurrency guard via lock files and `PROFILE_DELEGATE_MAX_CONCURRENT`.
- Bounded streaming stdout/stderr capture via `PROFILE_DELEGATE_MAX_STDOUT_CHARS` and `PROFILE_DELEGATE_MAX_STDERR_CHARS`.
- Optional working-directory allowlist via `PROFILE_DELEGATE_ALLOWED_WORKDIRS`.
- Absolute/configurable Hermes binary path resolution.
- Defensive JSON extraction and schema normalization, including warning-prefixed stdout and nested JSON objects.
- Explicit `auto|json|markdown|text` serialization modes with deterministic conflict detection before launch.
- Independent execution, task, and contract outcomes; blocked, unknown, malformed, ambiguous, cancelled, timed-out, and transport-failed runs never become false success.
- Conservative local fallback for useful non-JSON child output; no automatic profile retry on parse failure.
- Strict automatic recovery for recognized terminal transport failures: resume the same child session up to twice, wait 10 seconds between attempts, and share one total timeout budget. Never restart in a fresh session.
- Private local run artifacts: request, prompt, status, stdout, stderr, result, and redacted/hash-only approval events.
- Async background mode with native durable completion records and best-effort lane-routed notification. Task-id deduplication is not exactly-once or guaranteed post-restart delivery; records can be dropped by native replay age/retry budgets.
- A read-only compatibility circuit breaker runs before every background task with `notify_on_complete=true`. It opens `state.db` with SQLite `mode=ro` plus `PRAGMA query_only`, validates required native API signatures and minimum `async_delegations` columns, and fails before creating a run or writing the database if Hermes has become incompatible.
- Stable error codes for common failures.
- Tool preview patch so users see the target profile and one-line task summary.
- Model-facing read-only status/list with exact-origin checks; explicit reconciliation is operator CLI only. No prune tool is registered.
- Read-only terminal spectator: `hermes profile-delegate watch <task_id>` and bounded `inspect --json`.

## What this is not

- Not a security sandbox. Profiles isolate context/state, not operating-system permissions.
- Not a durable profile message bus.
- Supports explicit target-profile session resume via `session_mode: "resume"` and `session_id`.
- Automatic recovery requires the strict final `session_id:` footer; a recognized transient failure without one fails closed instead of repeating the task.
- Not an exactly-once platform delivery system; Hermes records durable pending/delivered/failed delivery state, while `profile_delegate_status` and run artifacts remain the source of truth.
- Not approval brokering between parent and target profile.
- Not safe for untrusted users without explicit policy configuration.
- The authorization boundary is the registered model-facing delegation tools, not arbitrary same-UID Python, terminal access, or importable plugin helpers. A same-UID operator CLI invocation is trusted local code and can inspect/reconcile other origins. Do not grant untrusted models general Python/terminal execution on this host; profiles provide no OS isolation.

## Requirements

- Hermes Agent installed and available as `hermes` on `PATH`, or configured with `PROFILE_DELEGATE_HERMES_BIN`.
- Hermes version with plugin support and the TUI Gateway JSON-RPC stdio transport. Foreground and rollback execution retain quiet single-query chat compatibility.
- Durable notification additionally requires Hermes' native async-delegation API/schema contract. Inspect `profile_delegate_policy.native_async_ledger`; incompatibility returns `native_async_ledger_incompatible`. Foreground and background calls with `notify_on_complete=false` remain available and do not use the ledger.
- At least one named profile created with `hermes profile create <name>`.
- The plugin enabled in the caller profile.
- Python on a Unix-like platform for lock-file concurrency control.

## Installation

Clone or copy this plugin into your Hermes plugins directory.

Default profile:

```bash
mkdir -p ~/.hermes/plugins
git clone https://github.com/Heeervas/profile-delegate-plugin.git ~/.hermes/plugins/profile-delegate
hermes plugins enable profile-delegate
```

Named profile:

```bash
mkdir -p ~/.hermes/profiles/<profile>/plugins
git clone https://github.com/Heeervas/profile-delegate-plugin.git ~/.hermes/profiles/<profile>/plugins/profile-delegate
hermes -p <profile> plugins enable profile-delegate
```

Restart the CLI/gateway after enabling:

```bash
hermes gateway restart
# or start a fresh `hermes` CLI session
```

## Watch delegated runs from a terminal

A background `profile_delegate` response now includes a copyable `watch_command`. Run it in a local terminal:

```bash
hermes profile-delegate watch pd_20260721_085059_dzk2o9
hermes profile-delegate watch pd_20260721_085059_dzk2o9 --jsonl
hermes profile-delegate inspect pd_20260721_085059_dzk2o9 --json
```

For a named caller profile, use the emitted `hermes -p <profile> ...` command. `watch` and `inspect` only read bounded, sanitized artifacts under the exact caller runs root. They never attach to child stdin, the TUI transport, `control/`, or `state.db`. Pressing `q` or `Ctrl+C` detaches the spectator without stopping the delegated run.

Assistant text is absent by default. Legacy runs without `events.jsonl` remain inspectable with clearly labeled limited observability. Use `hermes profile-delegate -h` for root resolution, output modes, and exit codes.

## Required security configuration

By default, delegation is disabled until you explicitly allow target profiles.

Recommended minimum:

```bash
export PROFILE_DELEGATE_ALLOWED_PROFILES=reviewer,builder,research
export PROFILE_DELEGATE_MAX_DEPTH=1
export PROFILE_DELEGATE_MAX_CONCURRENT=1
# Required only when callers may override capability-bearing fields:
export PROFILE_DELEGATE_ALLOWED_TOOLSETS=file,terminal,web
export PROFILE_DELEGATE_ALLOWED_SKILLS=hermes-agent,test-driven-development
```

Optional hardening:

```bash
export PROFILE_DELEGATE_HERMES_BIN=/opt/hermes/.venv/bin/hermes
export PROFILE_DELEGATE_ALLOWED_WORKDIRS=/opt/data/repos,/workspace
export PROFILE_DELEGATE_RUNS_ROOT=/path/to/private/profile-delegate-runs
```

Delegated child processes are forced non-interactive by stripping inherited gateway/session approval env. Approval is installed inside the child process by the plugin bootstrap before Hermes constructs the agent; it does not depend on cron-session simulation or a parent approval queue. Non-secret operational policy can live in YAML; explicitly present environment variables remain higher-precedence operator overrides:

```yaml
plugins:
  entries:
    profile-delegate:
      child_approval_mode: profile  # deny | profile | inherit | yolo; approve_yolo alias
      child_approval_modes_by_profile: {builder: profile, reviewer: deny}
      allowed_profiles: [builder, reviewer]
      allow_all_profiles: false
      allowed_workdirs: [/opt/data]
      allowed_toolsets: []       # empty means deny per-call toolset overrides
      allowed_skills: []         # empty means deny per-call skill overrides
      allow_model_override: true
      allow_provider_override: true
      allow_reasoning_override: true
      allow_child_approval_override: true
      max_depth: 1
      max_concurrent: 1
      max_async: 2
      default_timeout_seconds: 1200
      max_timeout_seconds: 1800
      max_transient_resumes: 2
      duplicate_guard:
        enabled: true
        active_window_seconds: 120
```

Precedence is safe hardcoded bounds/defaults, then YAML, then explicitly present `PROFILE_DELEGATE_*` environment variables, then permitted per-call values. Missing YAML preserves the previous fail-closed capability policy. Empty allowlists deny overrides. Malformed YAML/config/env values fail with `configuration_error` before a run is created; they are not replaced by broader defaults.

- New omitted configuration selects `profile`; historical stored requests with omitted selectors retain legacy `deny`. Explicit `deny` refuses fresh ordinary approval, retains permanent command grants and forces non-bypass deny unattended posture.
- `profile` freezes target native posture/grants; `inherit` freezes caller posture/permanent grants with target and ancestor denies. Transient session grants are excluded.
- `yolo` (`approve_yolo` alias) bypasses ordinary consent while native terminal floors remain. Approval bypass no longer implicitly consents to hooks.
- Operator target-map entries take precedence over global YAML. See [native approval operator contract](docs/plans/2026-10-01-native-approval-modes/OPERATOR.md) for snapshot/resume, nested restrictions, unattended smart limitations and activation consequences. Published source does not prove activation in a running gateway.
- `strip_only` migration: new tool calls reject it. A legacy YAML value is read as `deny` so existing installations fail closed; update configuration to `deny` explicitly.

Model-facing `child_approval_mode` selects the mode **per task**. `profile`, `inherit`, and `yolo` require the trusted caller plugin entry's `allow_child_approval_override: true`; its default is false. This is delegated authority, independent of the configured omission default and native approval posture. `deny` is available as narrowing without that grant. Task selection overrides the target default map, never target admission, explicit denies or frozen ancestry. Nested calls permit exact frozen inheritance or deny narrowing; incomparable source switches refuse. Resume cannot change its frozen selector. See [repair contract and historical runtime matrix](docs/plans/2026-10-01-native-approval-modes/PER_TASK_REPAIR.md). Current source/validation status is in [STATE.md](STATE.md); running installations require separate readback.

Local-power-user override, not recommended for shared installs:

```bash
export PROFILE_DELEGATE_ALLOW_ALL_PROFILES=true
```

### Configuration reference

| Variable | Default | Purpose |
|---|---:|---|
| `PROFILE_DELEGATE_ALLOWED_PROFILES` | empty | Comma-separated target profile allowlist. Required unless `PROFILE_DELEGATE_ALLOW_ALL_PROFILES=true`. |
| `PROFILE_DELEGATE_ALLOW_ALL_PROFILES` | `false` | Explicitly allow delegation to any existing local profile. Use only for trusted local setups. |
| `PROFILE_DELEGATE_MAX_DEPTH` | `1` | Maximum nested delegation depth. `1` allows caller → target, but blocks target → another target. |
| `PROFILE_DELEGATE_DEPTH` | `0` | Internal depth counter passed to child Hermes processes. Do not set manually except for tests. |
| `PROFILE_DELEGATE_MAX_CONCURRENT` | `1` | Number of concurrent profile delegation subprocesses allowed per Hermes home. |
| `PROFILE_DELEGATE_DEFAULT_TIMEOUT_SECONDS` | `1200` | Default synchronous wait limit for `profile_delegate` calls that omit `timeout_seconds`. |
| `PROFILE_DELEGATE_MAX_TIMEOUT_SECONDS` | `1800` | Maximum allowed synchronous wait limit. Must be at least the default timeout. |
| `PROFILE_DELEGATE_MAX_ASYNC` | `2` | Number of background `profile_delegate` runs allowed in the current gateway/CLI process. |
| `PROFILE_DELEGATE_NOTIFY_MAX_SUMMARY_CHARS` | `4000` | Maximum summary size sent through notify-on-complete events. |
| `PROFILE_DELEGATE_MAX_STDOUT_CHARS` | `200000` | Maximum stdout characters stored and parsed from the delegated Hermes process. Extra output is truncated. |
| `PROFILE_DELEGATE_MAX_STDERR_CHARS` | `100000` | Maximum stderr characters stored from the delegated Hermes process. Extra output is truncated. |
| `PROFILE_DELEGATE_HERMES_BIN` | resolved from `PATH` | Absolute Hermes binary override. If unset, the plugin resolves `hermes` with `shutil.which()` and uses the absolute path. |
| `PROFILE_DELEGATE_ALLOWED_WORKDIRS` | empty | Comma-separated allowed roots for explicit `workdir`. If unset, explicit `workdir` is rejected. |
| `PROFILE_DELEGATE_ALLOWED_TOOLSETS` | empty | Explicit allowlist for per-call `toolsets`; unset/empty rejects any toolset override. |
| `PROFILE_DELEGATE_ALLOWED_SKILLS` | empty | Explicit allowlist for per-call `skills`; unset/empty rejects any skill override. |
| `PROFILE_DELEGATE_ENABLE_PREVIEW_PATCH` | `true` | Toggle the compatibility monkeypatch for one-line tool previews. Set `false` if a future Hermes preview API conflicts. |
| `PROFILE_DELEGATE_RUNS_ROOT` | `$HERMES_HOME/profile_delegate/runs` | Private run artifact directory. |
| `PROFILE_DELEGATE_LOCKS_ROOT` | `$HERMES_HOME/profile_delegate/locks` | Lock-file directory for concurrency slots. |

## Tools

### `profile_delegate`

Delegate a bounded task to another profile.

Input:

```json
{
  "profile": "reviewer",
  "task": "Review this plan and return the top risks.",
  "session_title": "review plan riesgos",
  "session_mode": "new",
  "session_id": "",
  "context": "Optional compact context, paths, artifacts, or summary.",
  "timeout_seconds": 1200,
  "output_mode": "auto",
  "output_contract": "Optional extra output instructions.",
  "workdir": "",
  "background": false,
  "notify_on_complete": true,
  "model": "openai/gpt-5",
  "provider": "openai",
  "reasoning_effort": "high",
  "max_turns": 50,
  "toolsets": ["file", "terminal"],
  "skills": ["test-driven-development"],
  "capability_preset": "build",
  "child_approval_mode": "deny"
}
```

Notes:

- `profile` must exist locally and pass the allowlist policy.
- `task` should be self-contained.
- `session_title` is required, truncated to 50 chars, and used to rename new sessions after the parent parses Hermes' `session_id:` footer. Short Spanish/broken-English shorthand is fine.
- `session_mode` defaults to `new`; use `resume` with `session_id` to continue a target-profile session. Find ids with `hermes -p <profile> sessions list`.
- `PROFILE_DELEGATE_MAX_TRANSIENT_RESUMES` controls automatic same-session transport recovery (`0..2`, default `2`). Recovery is limited to the plugin's anchored allowlist; timeout, policy/approval, validation, quota/auth, OOM/SIGKILL, and ambiguous failures are never retried.
- If the delegated profile invokes `profile_delegate`, the plugin propagates the parent task id into the nested child and appends bounded direct-child status/result summaries to the parent's `result.nested_delegations`. Controllers should inspect that field before launching a follow-up delegate for the same reviewer/research task. This is direct-child lineage, not a general message bus.
- `context` is caller-selected. Keep it compact; pass paths and summaries instead of dumping whole transcripts.
- `workdir` defaults to the current process working directory.
- Explicit `workdir` values require `PROFILE_DELEGATE_ALLOWED_WORKDIRS`.
- `timeout_seconds` is synchronous and bounded from 10 to `PROFILE_DELEGATE_MAX_TIMEOUT_SECONDS` seconds; default local config is 1200 seconds and max is 1800 seconds.
- `output_mode` is `auto`, `json`, `markdown`, or `text`. `auto` preserves exact legacy phrases such as `Full Markdown`, `Markdown only`, `JSON only`, and `Plain text only`; otherwise it defaults to JSON. Explicit modes are accepted only when compatible. Conflicting serialization instructions fail before a child is launched.
- Execution precedence is per-call override > target profile default; blank/omitted `model`, `provider`, and `reasoning_effort` inherit. These are requested controls: Hermes/provider still validates model/provider compatibility.
- TUI resume applies explicit selection before submitting the prompt. Provider-only TUI creation keeps the session model and applies the requested provider. Native model switching always includes `--session`; reasoning accepts only effort levels with a verified live session. Display commands such as `show` are refused before RPC because Hermes persists display YAML even with session scope. Profile configuration is not rewritten; native confirmations remain operator decisions.
- `toolsets` and `skills` are capability-bearing and fail closed unless every requested item is present in the corresponding plugin allowlist.
- Call `profile_delegate_policy` before using optional overrides. Deterministic preflight failures report all `unsupported_fields` together with a one-shot `retry_patch` and `run_created:false`.
- `capability_preset` defaults to `build`, which preserves the selected/inherited child capabilities and never bypasses approval policy. `review` selects Hermes' `web` and `file` toolsets, then removes `write_file`, `patch`, `terminal`, `process`, `execute_code`, and other mutating/delegating schemas inside the child before agent construction. It leaves `read_file` and `search_files`; it does not claim a read-only terminal. To avoid ambiguous widening, `review` cannot be combined with a per-call `toolsets` override.
- `reasoning_mode` defaults to `inherit`, which creates no overlay. `override` requires `reasoning_effort`; `none` is a real explicit override, never inheritance. For compatibility, an effort supplied without a mode still means override. Managed-scope/default-profile conflicts fail in preflight with a corrective patch before run allocation.
- Accepted reasoning requests are `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, and `max`. Runtime/provider support still decides whether a request executes successfully. `max` is retained for forward-compatible GPT-5.6 use; `ultra` is a separate multi-agent mode, not a reasoning effort.
- `request.json`, `status.json`, sync/async responses, and final `result.json` expose `requested_execution`, `effective_execution`, `effective_capabilities`, and `approval_policy`. `approval_events.jsonl` records bootstrap/policy outcomes with timestamp, effective policy, detector/reason, outcome, SHA-256, and input length where applicable.
- `background=true` returns immediately with `mode: "async"`, `task_id`, and run artifact paths; the delegated run continues in the configured thread or detached worker using persisted request data.
- Identical active requests from the same resolved caller origin are reused under a per-fingerprint file lock. `duplicate_policy:"new"` permits intentional duplicate work. Completed runs are not silently reused.
- Both synchronous and detached runs execute the same bootstrap path. If legacy/core output contains `Timeout — denying command`, the run is finalized as structured `approval_timeout` failure instead of being reported as successful or left active.
- `notify_on_complete=true` has the detached worker register a native Hermes `async_delegation` record before profile execution and persist its completion, routed by origin lane `session_key`. Durable records support inspection/recovery but notification remains best effort: expiry, retry budgets or runtime failure can prevent delivery across reset/restart. Task-id deduplication is not an exactly-once receipt.

Default result requested from the target profile:

```json
{
  "status": "ok|blocked|failed|unknown",
  "summary": "concise summary string",
  "artifacts": ["paths or URLs"],
  "errors": ["concise error strings"],
  "next_steps": ["concise next steps"]
}
```

The plugin normalizes non-list fields into arrays where appropriate and converts invalid statuses into a structured failure. `unknown` is a real non-success task result used for useful output that has no safe explicit verdict; it is never promoted to wrapper success.

For new Markdown/text requests, finish with exactly one terminal line
`PROFILE_DELEGATE_RESULT: ok|blocked|failed` outside code fences. Generic
PASS/OK/BLOCKED/FAILED verdict recovery remains conservative legacy compatibility,
not the new request contract. Conflicting or negated verdicts remain `unknown`. Async notification status follows execution
lifecycle: a completed run is announced as completed even when its task result is
blocked, failed, or unknown; the compact result preserves that distinction.

- `profile_delegate_cancel(task_id)` on a detached simple run is origin-authorized. Before an exact owned worker/child group identity is published, it refuses with `control_identity_pending` and creates no cancellation intent or ACK; retry after identity becomes verifiable. If that identity changes or the worker dies, `control_identity_unverifiable` likewise refuses without signalling any PID. Once verified, the worker terminates its owned group and reaps the direct child before ACK; `cancel_pending` is not a terminal cancellation claim.

- TUI `session.steer` ACK means queued, not delivered. A completed and settled turn can finish without a second turn when fresh native steering occurrences prove consumption of every accepted or RPC-timeout-ambiguous correction. This sets `steer_delivery_state=delivered`; old replayed corrections cannot establish delivery. Evidence is read without changing Hermes configuration. If proof is unavailable, an observed completed and settled follow-up can still finish with delivery `unknown`; an unfinished follow-up uses the task deadline. Without either receipt, the fallback event-polling window is 1.2 seconds and ends in `steer_outcome_uncertain` and wrapper `success=false`, preserving the last output. Native receipt reads are synchronous and can extend wall time; expired evidence cannot authorize success. Silence and `session.close` are not delivery receipts.
- Before steering, inspect public status for active execution and `event_metadata.turn_count > 0`, derived from native `message.start`. `phase=model_running` alone does not prove the native agent exists.

### Reconciliation and retention

`operator-reconcile` is an explicit **operator repair** command, not an ordinary
status read. Under the verified per-run `status.lock`, it repairs only a
nonterminal detached run whose worker PID is independently confirmed absent.
A valid terminal result takes authority: its exact execution outcome is
projected into status without rewriting the result, including after a crash
between result and status renames. If no result exists, a dead worker produces
a conservative task-`unknown` result and execution `failed/worker_died`;
an acknowledged cancellation instead produces execution `cancelled`. Live,
reused-PID, or unverifiable workers are not finalized. Conflicting, malformed,
oversized, symlinked, or otherwise unsafe evidence fails closed. An existing
terminal status remains immutable; repeated reconciliation is read-only.

Interactive session preparation and prompt submission share one initialization deadline. RPCs with an exhausted budget fail before dispatch.

Terminal worker, startup, and failure publishers share the verified lock
publication decision: a valid terminal result is written before terminal status,
and later failure paths cannot overwrite it. Paired operator/model status reads use
the lock and validate the same single result snapshot returned to the caller.
Legacy results remain unverified; notification enrichment cannot replace terminal-owned fields. A crash
between the two renames leaves a result-first intermediate that an operator can
repair once its detached worker is definitively dead. Ordinary status/list and
duplicate/capacity checks remain read-only. Retention remains separate,
approval-gated, dry-run by default, locked, age-based, and terminal-only.

Final results carry three orthogonal fields:

- `execution_status`: authoritative terminal run lifecycle: `completed`, `failed`, `cancelled`, or `timed_out`.
- `status`: target task outcome: `ok`, `blocked`, `failed`, or `unknown`.
- `contract_status`: output-contract state: `valid`, `recovered`, `drifted`, `empty`, or `not_evaluated` for manual transport/lifecycle failures.

A whole-document JSON object is `valid`; when it omits an explicit task status its task outcome is `unknown`, not success. A uniquely selected fenced or prose-embedded JSON object is `recovered` and retains `raw_output_path`. Narrow recovery from one explicit Markdown/text verdict is also `recovered`; ambiguous JSON, negated verdicts, and multiple/conflicting textual statuses are `drifted` and cannot become successful. Wrapper `success:true` requires a completed execution, task `status:"ok"`, contract `valid` or `recovered`, and no parse error. `blocked`, `failed`, `unknown`, cancellation, timeout, transport failure, and parsing ambiguity always produce `success:false`.

Child prompts use Hermes' native `--query-file <prompt.txt>` input; results are parsed from captured stdout/stderr. The model receives the task directly, without a tool call to read the prompt file.

### `profile_delegate_status`

Read a run by `task_id`.

Active detached background runs use one isolated TUI Gateway JSON-RPC stdio
child. Status includes bounded transport phase/activity metadata and omits raw
prompts, reasoning, tool payloads, and control text.

### `profile_delegate_steer`

`profile_delegate_steer(task_id, text)` sends a bounded correction to an active
TUI-backed run through native `session.steer`. It is available only to the exact
originating session; the private run-local inbox records delivery acknowledgements.

### `profile_delegate_cancel`

`profile_delegate_cancel(task_id)` requests native `session.interrupt`, waits a
short bounded grace period, then reaps/escalates the worker-owned TUI process if
needed. Cancellation is idempotent and is committed only after cleanup.

```json
{
  "task_id": "pd_20260613_083528_9hksdn",
  "tail_chars": 4000
}
```

Returns status, result, stdout/stderr tails, artifact paths, `session_title`, normalized
`origin`, worker metadata, notification status, and advisory `activity`. The
`belongs_to_current_session` is advisory provenance; model status access still
requires authorized origin, home and namespace. Native directional compression
continuity may extend exact identity only with verified evidence. Global inspection
is available to the trusted operator CLI, not model-facing status.

Example output fragment:

```json
{
  "session_title": "fix profile delegate listing",
  "origin": {"session_id": "20260717_...", "session_key": "discord:guild:channel:thread"},
  "belongs_to_current_session": true,
  "origin_match_by": "session_id",
  "worker_pid": 1234,
  "worker_alive": true,
  "activity": "active"
}
```

### `profile_delegate_list`

List recent runs. The default scope is `current_session`; it uses UI session id,
durable session id, then lane key in that precedence order and never falls back to
a weaker key after a stronger mismatch. Model calls permit only `current_session`;
legacy widening requests are refused. The trusted `operator-list` CLI permits
`current_lane` or `all` for lane/global inspection.

```json
{
  "limit": 20,
  "scope": "current_session",
  "status": ["running"],
  "profile": "builder"
}
```

`limit` applies after scope and optional status/profile filters. If caller origin
is unavailable, current scope returns an empty result with
`scope_effective: "unresolved"`; it never silently widens to global scope. Run
summaries include `session_title`, normalized `origin`, `worker_alive`, and
`activity`. Lifecycle filters accept the complete runtime set: `running`,
`cancelling`, `completed`, `failed`, `cancelled`, `timed_out`, and `corrupt`.

Liveness is advisory and read-only: terminal runs are `finished`; a running
detached worker with a live/dead PID is `active`/`stale`; legacy or uncheckable
runs are `unknown`. Inspection never rewrites canonical status. Older artifacts
remain readable without migration, but missing provenance or PID metadata can
produce `null` ownership and `unknown` activity.

### Retention (internal only)

No prune tool or public prune CLI is registered. The internal operator retention
helper and its terminal-only/lock/UID safety tests remain; this is not a public
invocable interface or authorization for automated deletion.

## Run artifacts

By default, run artifacts are stored at:

```text
$HERMES_HOME/profile_delegate/runs/<task_id>/
  request.json
  status.json
  prompt.txt
  stdout.txt
  stderr.txt
  result.json
  reasoning_config/  # config-only managed overlay when reasoning_effort is requested
```

Security posture:

- run directories are created as `0700`
- files are written as `0600`
- prompts, context, stdout, and stderr may contain private data
- stdout/stderr are capped by default to prevent local memory/disk blowups
- retention has no registered public prune interface; do not automate deletion through model tools

## Security model

Enabling this plugin lets the caller profile invoke configured target profiles. The target profile runs with its own Hermes context and tool configuration, but it still has the same operating-system permissions as the Hermes process. Profiles are context/state boundaries, not security sandboxes.

Treat delegated `task`, `context`, and `output_contract` as private. The plugin stores prompt and logs with restrictive local permissions and passes the prompt to Hermes via native `--query-file <prompt-path>` instead of putting the full prompt in process argv. Still, do not delegate secrets unless the target profile genuinely needs them.

For shared or untrusted installations:

- set `PROFILE_DELEGATE_ALLOWED_PROFILES`
- keep `PROFILE_DELEGATE_MAX_DEPTH=1`
- keep `PROFILE_DELEGATE_MAX_CONCURRENT=1`
- set `PROFILE_DELEGATE_ALLOWED_WORKDIRS`
- set `PROFILE_DELEGATE_HERMES_BIN` to a trusted absolute path
- prune run artifacts periodically

## Error codes

Common `error_code` values:

- `validation_error`
- `configuration_error`
- `profile_policy_required`
- `profile_not_allowed`
- `profile_not_found`
- `profile_validation_failed`
- `input_too_large`
- `workdir_policy_required`
- `workdir_not_allowed`
- `workdir_not_found`
- `hermes_missing`
- `hermes_not_executable`
- `recursion_limit`
- `concurrency_limit`
- `timeout`
- `parse_failed`
- `nonzero_exit`
- `run_not_found`
- `invalid_json`
- `internal_error`

## Tool preview

Hermes core does not currently expose a first-class plugin preview hook. This plugin patches Hermes' display preview at plugin registration time so `profile_delegate` previews show:

```text
to reviewer: Review this plan and return the top risks.
```

This is a local compatibility shim. If Hermes later adds an official preview API, this should move to that API.

## Development

Use the frozen lock, not an ad-hoc pip environment:

```bash
uv lock --check
uv sync --frozen
uv run --frozen python -m pytest -m 'not integration' -q -o 'addopts=' -W error
PROFILE_DELEGATE_TEST_RUNTIME=/opt/hermes PYTHONPATH=/opt/hermes \
  /opt/hermes/.venv/bin/python -m pytest -m integration -q -o 'addopts=' -W error
uv run --frozen ruff check .
uv run --frozen python scripts/validate_release.py
uv run --frozen python scripts/scan_secrets.py  # add explicit intended-new source paths
```

Both partitions are required. Runtime-coupled mixed modules are conservatively
classified integration; no tests were removed. The installed job uses immutable
Hermes `e8c97320ac8691d4de92af49f98459f9ef9ddb08` with its Python 3.14 runtime
and frozen lock with its explicit `--group dev` test tooling. Native pytest is
executed by that same `.venv/bin/python` (3.14), never the plugin 3.13 environment.
The hash-pinned native PyYAML helper is in `scripts/native-test-tooling.txt`;
`scripts/native_prerequisite.py` fails closed on interpreter/closure mismatch.
The portable matrix
remains 3.11/3.12/3.13. Missing runtime/imports fail integration rather than skip.
Exact-baseline GitHub CI passed all four jobs; see [STATE.md](STATE.md).
Historical local provisioning blockers remain in the audit, not current CI status.
Canonical compilation and behavioral gates: `.agents/validation.md`.

Operator runtime smokes require separate authorization; do not run the acceptance
harness from frozen delegated authority or treat registration's FakeContext as
installed discovery.


## Contributing and remaining work

See [CONTRIBUTING.md](CONTRIBUTING.md), [contribution opportunities](docs/contribution-opportunities.md)
and the reconciled [TODO.md](TODO.md). Cancellation already exists; unresolved
parser/RPC/UTF-8 findings require focused reproduction and maintainer coordination.
Tests live under `tests/`; runtime modules intentionally remain at root. Plans,
audits and archived provenance are indexed in [docs/README.md](docs/README.md).

## License

MIT
