# Profile Delegate Per-Call Execution Overrides Implementation Plan

> **For Hermes:** Implement this plan using strict TDD. This file is the recovery source after context compaction.

**Goal:** Let each `profile_delegate` call temporarily override the delegated profile’s model, provider, reasoning effort, maximum turns, toolsets, and preloaded skills without mutating that profile’s persistent configuration.

**Architecture:** Extend the plugin schema with flat, backwards-compatible optional execution inputs and persist them under one normalized `requested_execution` object in request/status/result artifacts. Translate native `hermes chat` controls directly into argv. Because the installed CLI has no reasoning flag, a reasoning override uses a config-only temporary Hermes managed scope under `<run_dir>/reasoning_config` only when no managed scope already exists. If inherited `HERMES_MANAGED_DIR` resolves to a directory, or `/etc/hermes` exists, fail before subprocess execution with `reasoning_managed_scope_conflict`; never copy, compose, or replace administrator-managed files. The worker keeps `HERMES_HOME` pointed at the canonical named profile, so sessions, resume, rename, credentials, and profile resources remain canonical. Default-profile reasoning overrides are rejected because `-p default` resolves specially. Never edit-and-restore the real target config. Toolset/skill overrides require explicit plugin policy allowlists so a caller cannot silently broaden target capabilities.

**Tech Stack:** Python 3.10+, Hermes plugin API, subprocess, JSON/YAML through Hermes’ own config loader/writer where practical, pytest, Ruff.

## Scope and acceptance criteria

New optional tool fields:

- `model: string` → `hermes chat --model VALUE`
- `provider: string` → `hermes chat --provider VALUE`
- `reasoning_effort: none|minimal|low|medium|high|xhigh` → temporary child-only `agent.reasoning_effort`
- `max_turns: integer (1..10000)` → `hermes chat --max-turns VALUE`
- `toolsets: string[]` → `hermes chat --toolsets comma,separated`
- `skills: string[]` → repeat `hermes chat --skills VALUE` or one comma-separated flag, matching current CLI semantics

Security policy for capability-bearing fields:

- `toolsets` is accepted only when every requested name appears in `PROFILE_DELEGATE_ALLOWED_TOOLSETS`; unset/empty policy means the override is rejected.
- `skills` is accepted only when every requested name appears in `PROFILE_DELEGATE_ALLOWED_SKILLS`; unset/empty policy means the override is rejected.
- These are explicit caller-controlled capability overrides, not claims that target-profile permissions remain unchanged. Hermes and the target profile still apply their own hard restrictions.

Acceptance:

1. Omitting every new field produces the current command and behavior byte-for-byte apart from additive metadata.
2. Overrides work in synchronous and both background execution modes because they are persisted in `request.json` before execution.
3. The target profile’s persistent `config.yaml` remains byte-identical on success, failure, timeout, and malformed input. Normal Hermes writes to target sessions/state/logs are allowed and tested separately.
4. Invalid/blank model/provider entries, unsupported reasoning levels, invalid max turns, and malformed toolset/skill lists fail before creating a subprocess.
5. User-controlled values are passed as argv elements, never shell-expanded.
6. Request/status/final result surfaces report one `requested_execution` object without exposing credentials or claiming provider acceptance.
7. Existing approval, depth, workdir, concurrency, session-resume, output-capture, and notification behavior remains intact.
8. README/schema/plugin version document the feature and precedence.
9. Unit suite, Ruff, compile checks, CLI smoke, and one real delegated profile smoke pass.

## Security-limited reasoning design

The clean upstream interface would be `hermes chat --reasoning-effort`. It does not exist in the installed CLI. The plugin therefore creates a private config-only `HERMES_MANAGED_DIR` for managed-scope-free installs while preserving canonical `HERMES_HOME`. It deliberately refuses the override whenever any administrator-managed scope exists because replacing that scope with a user-writable copy would weaken filesystem-enforced policy. Native Hermes CLI support is required to remove this limitation safely.

## Task 1: Lock schema and validation contracts with failing tests

**Files:**
- Modify: `test_profile_delegate.py`
- Later modify: `__init__.py`, `core.py`

**Steps:**
1. Extend `test_plugin_registers_tools` to assert all six optional properties, reasoning enum, array item types, and max-turn bounds.
2. Add parameterized validation tests for valid and invalid reasoning levels, `max_turns`, model/provider normalization, and toolset/skill arrays.
3. Assert blank optional strings normalize to no override while blank list entries are rejected or normalized according to the final documented rule.
4. Add policy tests proving toolset/skill overrides fail closed without their allowlists and reject any unlisted member.
5. Run targeted tests and verify RED because fields/helpers do not exist.

Run:
```bash
.venv/bin/python -m pytest test_profile_delegate.py -k 'execution_override or plugin_registers' -q
```
Expected: failures for absent schema fields/helpers.

## Task 2: Add minimal validation and schema plumbing

**Files:**
- Modify: `__init__.py`
- Modify: `core.py`
- Test: `test_profile_delegate.py`

**Steps:**
1. Add constants for accepted reasoning efforts and safe list/count/string bounds.
2. Add small coercion helpers returning normalized values or stable `validation_error` failures.
3. Extend `_schema()` with optional fields and explicit precedence descriptions: per-call value > target profile default; omitted means inherit.
4. Pass values through `_handler()` into `delegate_profile()`.
5. Extend `delegate_profile()` signature and persist normalized values under `requested_execution` in `request.json` and non-sensitive status metadata.
6. Run targeted tests GREEN, then full tests.

## Task 3: Verify and implement CLI-backed overrides with TDD

**Files:**
- Modify: `test_profile_delegate.py`
- Modify: `core.py`

**Steps:**
1. First add a failing command-construction test proving exact argv ordering and separate argument boundaries for model, provider, max turns, toolsets, and skills.
2. Add a regression test proving omitted overrides preserve the old argv.
3. Implement a dedicated pure helper such as `build_child_command(request, run_dir)` rather than growing `_execute_delegate_run` inline.
4. Pass:
   - `--model`, normalized model
   - `--provider`, normalized provider
   - `--max-turns`, decimal value
   - `--toolsets`, comma-joined normalized values
   - `--skills`, comma-joined normalized values
5. Preserve `--yolo`, resume, session footer, source, and quiet behavior.
6. Run RED then GREEN tests and full suite.

## Task 4: Implement isolated reasoning override after source verification

**Files:**
- Modify: `test_profile_delegate.py`
- Modify: `core.py`
- Possibly create: no new production file unless isolation is materially cleaner

**Steps:**
1. Inspect installed Hermes profile/config resolution (`hermes_constants.get_hermes_home`, profile CLI bootstrap, config loader) and record the chosen verified mechanism in code comments and README.
2. Add a failing test using a fake profile home with sentinel files. Assert the child sees an isolated config with requested reasoning while the original bytes remain identical.
3. Add original-config checksum tests for success, nonzero exit, timeout, and overlay setup failure; normal session/state writes are not treated as immutability failures.
4. Implement the smallest safe isolation helper. Requirements:
   - no writes to real target profile;
   - no copying runtime-heavy directories such as sessions/logs/cache when links or selective materialization suffice;
   - no symlink path that lets writing the ephemeral config mutate the original;
   - restrictive permissions;
   - deterministic behavior for background workers after parent exit.
5. Add integration-shaped tests for early profile resolution with fake root + `-p`, root/profile `.env` and auth resolution without printing values, resume, and post-run session rename using the same ephemeral root.
6. Ensure command/environment use the isolated home only when reasoning override is supplied.
7. Add a test proving omission does not create/use an isolated home.
8. Run targeted RED/GREEN and complete suite.

## Task 5: Surface effective request metadata and preserve async behavior

**Files:**
- Modify: `test_profile_delegate.py`
- Modify: `core.py`

**Steps:**
1. Add failing tests showing `request.json`, `status.json`, sync result, and async status preserve normalized `requested_execution`.
2. Avoid claiming the model/provider/reasoning was accepted by the remote API; label fields `requested_*` unless verified from child session metadata.
3. Implement additive result metadata.
4. Verify thread and detached background paths consume only persisted request data, including a detached-worker reconstruction test with no parent in-memory state.
5. Run targeted and full tests.

## Task 6: Documentation and versioning

**Files:**
- Modify: `README.md`
- Modify: `plugin.yaml`

**Steps:**
1. Bump plugin version consistently (recommended minor bump to `1.2.0`; README currently says `1.1.0` while manifest says `1.1.2`, fix drift).
2. Update Features, command shape, tool JSON example, notes, precedence, artifacts, and security sections.
3. Explicitly state overrides are temporary and target profile config is untouched.
4. Document that provider/model compatibility is validated by Hermes/provider, not by this plugin.
5. Document reasoning isolation implementation and any artifact lifecycle.

## Task 7: Verification matrix

Run from `/opt/data/plugins/profile-delegate`:

```bash
uv sync --dev  # if the repo venv lacks pytest/ruff; pin dev dependencies in pyproject/lock first
uv run pytest test_profile_delegate.py -q
uv run ruff check __init__.py core.py test_profile_delegate.py cli_smoke.py
uv run python -m py_compile __init__.py core.py cli_smoke.py
uv run python cli_smoke.py --help
```

Then run an isolated CLI smoke with temporary run roots and an allowed lightweight profile. Verify:

1. Default call succeeds with no overrides.
2. A call with explicit model/provider/max-turns succeeds or fails honestly at provider compatibility, while argv/request artifacts prove propagation.
3. A reasoning override call returns the requested reasoning in target session metadata or another trustworthy child-side signal.
4. `git diff -- <real target config>` is empty and checksum before/after matches.
5. Run artifacts contain requested override metadata but no credential values.

## Task 8: Independent review and commit

1. Default profile independently inspects diff and tests; do not trust builder summary.
2. If implementation touches more than `__init__.py`, `core.py`, `test_profile_delegate.py`, `README.md`, `plugin.yaml`, and this plan, explain why.
3. Run final `git diff --check`, status, full tests, Ruff, and compile.
4. Commit once verified:

```bash
git add __init__.py core.py test_profile_delegate.py README.md plugin.yaml docs/plans/2026-07-11-per-call-execution-overrides.md
git commit -m "feat: add per-call profile execution overrides"
```

Do not push unless explicitly requested.
