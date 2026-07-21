# Profile Delegate 🤝

Version: `1.8.0`

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
- Launches Hermes in-process through a plugin-owned bootstrap before agent construction. The bootstrap installs deterministic child approvals and optional schema filtering, then runs quiet single-query mode with a prompt file reference. `--yolo` is added only when `child_approval_mode: approve_yolo` is explicit.
- Explicit target-profile allowlist by default.
- Recursion/depth guard via `PROFILE_DELEGATE_MAX_DEPTH`.
- Global concurrency guard via lock files and `PROFILE_DELEGATE_MAX_CONCURRENT`.
- Bounded streaming stdout/stderr capture via `PROFILE_DELEGATE_MAX_STDOUT_CHARS` and `PROFILE_DELEGATE_MAX_STDERR_CHARS`.
- Optional working-directory allowlist via `PROFILE_DELEGATE_ALLOWED_WORKDIRS`.
- Absolute/configurable Hermes binary path resolution.
- Defensive JSON extraction and schema normalization, including warning-prefixed stdout and nested JSON objects.
- Cheap local fallback for useful non-JSON child output; no automatic profile retry on parse failure.
- Strict automatic recovery for recognized terminal transport failures: resume the same child session up to twice, wait 10 seconds between attempts, and share one total timeout budget. Never restart in a fresh session.
- Private local run artifacts: request, prompt, status, stdout, stderr, result, and redacted/hash-only approval events.
- Async background mode with best-effort notify-on-complete through Hermes' native async-delegation completion queue.
- Stable error codes for common failures.
- Tool preview patch so users see the target profile and one-line task summary.
- Inspection tools: status, list, prune.
- Read-only terminal spectator: `hermes profile-delegate watch <task_id>` and bounded `inspect --json`.

## What this is not

- Not a security sandbox. Profiles isolate context/state, not operating-system permissions.
- Not a durable profile message bus.
- Supports explicit target-profile session resume via `session_mode: "resume"` and `session_id`.
- Automatic recovery requires the strict final `session_id:` footer; a recognized transient failure without one fails closed instead of repeating the task.
- Not a guaranteed delivery system; async notifications are best-effort and `profile_delegate_status` remains the durable source of truth.
- Not approval brokering between parent and target profile.
- Not safe for untrusted users without explicit policy configuration.

## Requirements

- Hermes Agent installed and available as `hermes` on `PATH`, or configured with `PROFILE_DELEGATE_HERMES_BIN`.
- Hermes version with plugin support and the TUI Gateway JSON-RPC stdio transport. Foreground and rollback execution retain quiet single-query chat compatibility.
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
      child_approval_mode: deny  # deny | approve_yolo
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

- `deny` (default): immediately deny dangerous terminal commands and host-access `execute_code` inside the child. Safe terminal commands still use normal Hermes guards. Decisions are recorded in `approval_events.jsonl` using hashes and character counts, never raw command/code text.
- `approve_yolo`: explicit trusted mode; adds `--yolo`, sets `HERMES_YOLO_MODE=1`, and auto-accepts hooks for the child. Hermes' hardline unconditional blocklist still applies.
- `strip_only` migration: new tool calls reject it. A legacy YAML value is read as `deny` so existing installations fail closed; update configuration to `deny` explicitly.

The `profile_delegate` tool also accepts `child_approval_mode` to override YAML for one call.

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
- `context` is caller-selected. Keep it compact; pass paths and summaries instead of dumping whole transcripts.
- `workdir` defaults to the current process working directory.
- Explicit `workdir` values require `PROFILE_DELEGATE_ALLOWED_WORKDIRS`.
- `timeout_seconds` is synchronous and bounded from 10 to `PROFILE_DELEGATE_MAX_TIMEOUT_SECONDS` seconds; default local config is 1200 seconds and max is 1800 seconds.
- Execution precedence is per-call override > target profile default; blank/omitted `model`, `provider`, and `reasoning_effort` inherit. These are requested controls: Hermes/provider still validates model/provider compatibility.
- `toolsets` and `skills` are capability-bearing and fail closed unless every requested item is present in the corresponding plugin allowlist.
- Call `profile_delegate_policy` before using optional overrides. Deterministic preflight failures report all `unsupported_fields` together with a one-shot `retry_patch` and `run_created:false`.
- `capability_preset` defaults to `build`, which preserves the selected/inherited child capabilities and never bypasses approval policy. `review` selects Hermes' `web` and `file` toolsets, then removes `write_file`, `patch`, `terminal`, `process`, `execute_code`, and other mutating/delegating schemas inside the child before agent construction. It leaves `read_file` and `search_files`; it does not claim a read-only terminal. To avoid ambiguous widening, `review` cannot be combined with a per-call `toolsets` override.
- `reasoning_mode` defaults to `inherit`, which creates no overlay. `override` requires `reasoning_effort`; `none` is a real explicit override, never inheritance. For compatibility, an effort supplied without a mode still means override. Managed-scope/default-profile conflicts fail in preflight with a corrective patch before run allocation.
- Accepted reasoning requests are `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, and `max`. Runtime/provider support still decides whether a request executes successfully. `max` is retained for forward-compatible GPT-5.6 use; `ultra` is a separate multi-agent mode, not a reasoning effort.
- `request.json`, `status.json`, sync/async responses, and final `result.json` expose `requested_execution`, `effective_execution`, `effective_capabilities`, and `approval_policy`. `approval_events.jsonl` records bootstrap/policy outcomes with timestamp, effective policy, detector/reason, outcome, SHA-256, and input length where applicable.
- `background=true` returns immediately with `mode: "async"`, `task_id`, and run artifact paths; the delegated run continues in the configured thread or detached worker using persisted request data.
- Identical active requests from the same resolved caller origin are reused under a per-fingerprint file lock. `duplicate_policy:"new"` permits intentional duplicate work. Completed runs are not silently reused.
- Both synchronous and detached runs execute the same bootstrap path. If legacy/core output contains `Timeout — denying command`, the run is finalized as structured `approval_timeout` failure instead of being reported as successful or left active.
- `notify_on_complete=true` queues a native Hermes `async_delegation` completion event back to the originating gateway session when the background run finishes. This requires a fresh gateway/CLI process after plugin upgrade so the new schema/code is loaded.

Default result requested from the target profile:

```json
{
  "status": "ok|blocked|failed",
  "summary": "concise summary string",
  "artifacts": ["paths or URLs"],
  "errors": ["concise error strings"],
  "next_steps": ["concise next steps"]
}
```

The plugin normalizes non-list fields into arrays where appropriate and converts invalid statuses into a structured failure. Child prompts are passed through `@file:<prompt.txt>` and results are parsed from captured stdout/stderr; this is not stdin transport.

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
`belongs_to_current_session` field is `true`, `false`, or `null` when caller/run
provenance cannot be compared. Lookup remains global by task id; provenance is
observability metadata, not access control.

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
a weaker key after a stronger mismatch. Use `current_lane` explicitly to include
the same gateway lane across session rotations, or `all` for global inspection.

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
`activity`.

Liveness is advisory and read-only: terminal runs are `finished`; a running
detached worker with a live/dead PID is `active`/`stale`; legacy or uncheckable
runs are `unknown`. Inspection never rewrites canonical status. Older artifacts
remain readable without migration, but missing provenance or PID metadata can
produce `null` ownership and `unknown` activity.

### `profile_delegate_prune`

Prune old run artifacts. Dry-run by default.

```json
{
  "max_age_days": 14,
  "dry_run": true
}
```

Set `dry_run` to `false` to delete matching run directories.

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
- prune old runs periodically with `profile_delegate_prune`

## Security model

Enabling this plugin lets the caller profile invoke configured target profiles. The target profile runs with its own Hermes context and tool configuration, but it still has the same operating-system permissions as the Hermes process. Profiles are context/state boundaries, not security sandboxes.

Treat delegated `task`, `context`, and `output_contract` as private. The plugin stores prompt and logs with restrictive local permissions and passes the prompt to Hermes via `@file:<prompt-path>` instead of putting the full prompt in process argv. Still, do not delegate secrets unless the target profile genuinely needs them.

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

Run tests:

```bash
python -m pip install pytest
python -m pytest . -q
python -m py_compile __init__.py core.py cli_smoke.py
```

Optional local smoke:

```bash
PROFILE_DELEGATE_ALLOWED_PROFILES=reviewer \
python cli_smoke.py --profile reviewer --session-title smoke --task 'Return {"status":"ok","summary":"smoke","artifacts":[],"errors":[],"next_steps":[]}'
```

Secret scan before publishing:

```bash
python - <<'PY'
import os, re
patterns=[r'github_pat_[A-Za-z0-9_]+', r'ghp_[A-Za-z0-9]{20,}', r'sk-[A-Za-z0-9]{20,}', r'AKIA[0-9A-Z]{16}', r'BEGIN (?:RSA|OPENSSH|EC|DSA)? ?PRIVATE KEY']
hits=[]
for dp, dns, fns in os.walk('.'):
    dns[:] = [d for d in dns if d not in {'.git','__pycache__','.pytest_cache'}]
    for fn in fns:
        p=os.path.join(dp, fn)
        try: data=open(p,'rb').read()
        except Exception: continue
        if b'\0' in data[:4096]: continue
        text=data.decode('utf-8','ignore')
        if any(re.search(x,text) for x in patterns): hits.append(p)
print('secret_hits=', len(hits))
for h in hits: print(h)
PY
```

CI runs pytest and py_compile on Python 3.10, 3.11, and 3.12.

## Roadmap

- Cancellation controls for active async runs.
- Optional no-prompt-storage mode or redacted prompt artifacts.
- Automatic retention/TTL cleanup.
- First-class Hermes plugin preview API support when available.
- Richer install packaging through the Hermes plugin registry.

## License

MIT
