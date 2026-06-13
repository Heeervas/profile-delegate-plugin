# Profile Delegate 🤝

Version: `0.2.0-alpha`

> Experimental/alpha Hermes Agent plugin. This is useful for local power users, but it is **not a sandbox** and should be configured deliberately before broad use.

A Hermes Agent plugin for bounded, model-callable delegation between Hermes profiles.

Instead of opening a Kanban board or running a second long-lived gateway, `profile_delegate` lets one profile ask another profile to perform a focused task and return a compact structured result.

Example uses:

- Ask a `reviewer` profile to critique a plan.
- Ask a `builder` profile to inspect implementation risk.
- Ask a `research` profile to check public sources.
- Ask a domain profile to produce a second opinion without mixing its memory into the caller.

## Features

- Model-callable `profile_delegate` tool.
- Runs the target profile with its normal Hermes context, memory, rules, tools, and model defaults.
- Uses Hermes one-shot mode with a prompt file reference: `hermes -p <profile> -z @file:<prompt.txt>`.
- Explicit target-profile allowlist by default.
- Recursion/depth guard via `PROFILE_DELEGATE_MAX_DEPTH`.
- Global concurrency guard via lock files and `PROFILE_DELEGATE_MAX_CONCURRENT`.
- Optional working-directory allowlist via `PROFILE_DELEGATE_ALLOWED_WORKDIRS`.
- Absolute/configurable Hermes binary path resolution.
- Defensive JSON extraction and schema normalization.
- Private local run artifacts: request, prompt, status, stdout, stderr, result.
- Stable error codes for common failures.
- Tool preview patch so users see the target profile and one-line task summary.
- Inspection tools: status, list, prune.

## What this is not

- Not a security sandbox. Profiles isolate context/state, not operating-system permissions.
- Not a durable profile message bus.
- Not resumable conversations.
- Not async/background delegation yet.
- Not approval brokering between parent and target profile.
- Not safe for untrusted users without explicit policy configuration.

## Requirements

- Hermes Agent installed and available as `hermes` on `PATH`, or configured with `PROFILE_DELEGATE_HERMES_BIN`.
- Hermes version with plugin support and `-z/--oneshot` mode.
- At least one named profile created with `hermes profile create <name>`.
- The plugin enabled in the caller profile.
- Python on a Unix-like platform for lock-file concurrency control.

## Installation

Clone or copy this plugin into your Hermes plugins directory.

Default profile:

```bash
mkdir -p ~/.hermes/plugins
git clone https://github.com/eve-ai-dev/profile-delegate-plugin.git ~/.hermes/plugins/profile-delegate
hermes plugins enable profile-delegate
```

Named profile:

```bash
mkdir -p ~/.hermes/profiles/<profile>/plugins
git clone https://github.com/eve-ai-dev/profile-delegate-plugin.git ~/.hermes/profiles/<profile>/plugins/profile-delegate
hermes -p <profile> plugins enable profile-delegate
```

Restart the CLI/gateway after enabling:

```bash
hermes gateway restart
# or start a fresh `hermes` CLI session
```

## Required security configuration

By default, delegation is disabled until you explicitly allow target profiles.

Recommended minimum:

```bash
export PROFILE_DELEGATE_ALLOWED_PROFILES=reviewer,builder,research
export PROFILE_DELEGATE_MAX_DEPTH=1
export PROFILE_DELEGATE_MAX_CONCURRENT=1
```

Optional hardening:

```bash
export PROFILE_DELEGATE_HERMES_BIN=/opt/hermes/.venv/bin/hermes
export PROFILE_DELEGATE_ALLOWED_WORKDIRS=/opt/data/repos,/workspace
export PROFILE_DELEGATE_RUNS_ROOT=/path/to/private/profile-delegate-runs
```

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
| `PROFILE_DELEGATE_HERMES_BIN` | resolved from `PATH` | Absolute Hermes binary override. If unset, the plugin resolves `hermes` with `shutil.which()` and uses the absolute path. |
| `PROFILE_DELEGATE_ALLOWED_WORKDIRS` | empty | Comma-separated allowed roots for explicit `workdir`. If unset, explicit `workdir` is rejected. |
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
  "context": "Optional compact context, paths, artifacts, or summary.",
  "timeout_seconds": 240,
  "output_contract": "Optional extra output instructions.",
  "workdir": ""
}
```

Notes:

- `profile` must exist locally and pass the allowlist policy.
- `task` should be self-contained.
- `context` is caller-selected. Keep it compact; pass paths and summaries instead of dumping whole transcripts.
- `workdir` defaults to the current process working directory.
- Explicit `workdir` values require `PROFILE_DELEGATE_ALLOWED_WORKDIRS`.
- `timeout_seconds` is synchronous and bounded from 10 to 900 seconds.

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

The plugin normalizes non-list fields into arrays where appropriate and converts invalid statuses into a structured failure.

### `profile_delegate_status`

Read a run by `task_id`.

```json
{
  "task_id": "pd_20260613_083528_9hksdn",
  "tail_chars": 4000
}
```

Returns status, result, stdout/stderr tails, and artifact paths.

### `profile_delegate_list`

List recent runs.

```json
{
  "limit": 20
}
```

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
```

Security posture:

- run directories are created as `0700`
- files are written as `0600`
- prompts, context, stdout, and stderr may contain private data
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
python cli_smoke.py --profile reviewer --task 'Return {"status":"ok","summary":"smoke","artifacts":[],"errors":[],"next_steps":[]}'
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

- Async mode with polling and cancellation.
- Optional no-prompt-storage mode or redacted prompt artifacts.
- Automatic retention/TTL cleanup.
- First-class Hermes plugin preview API support when available.
- Richer install packaging through the Hermes plugin registry.

## License

MIT
