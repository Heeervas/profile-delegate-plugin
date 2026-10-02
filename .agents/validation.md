# Validation contract

Run from the repository root.

Dependency installation is lock-governed:

```bash
uv lock --check
uv sync --frozen
```

`pyproject.toml` and `uv.lock` retain the plugin Python 3.11–3.13 support window.
Portable tests use `-m 'not integration'`; native-coupled mixed modules are marked
integration conservatively in `conftest.py`. Both partitions are mandatory; no
missing-runtime skip is permitted. Installed CI provisions immutable Hermes
`e8c97320ac8691d4de92af49f98459f9ef9ddb08` on Python 3.14 with its own frozen
lock and explicit `--group dev` (pytest is not a default runtime dependency).
Run `PYTHONPATH="$PROFILE_DELEGATE_TEST_RUNTIME" "$PROFILE_DELEGATE_TEST_RUNTIME/.venv/bin/python" scripts/native_prerequisite.py`
before native tests. The session prerequisite checks the exact venv interpreter,
Python 3.14, real config/approval/SessionDB/display/contracts and Pydantic extension.
CI additionally installs the hash-pinned PyYAML helper from
`scripts/native-test-tooling.txt` under that same interpreter (Ubuntu x86_64 cp314
wheel, `--only-binary :all:`, hash from pinned Hermes lock). No
unlocked tooling resolver or plugin package install on 3.14 is used.
Never add another Python version's site-packages to PYTHONPATH. This does not
broaden the plugin interpreter contract. Local isolated
provisioning and truly Hermes-free container validation are pending (see audit).

```bash
uv run --frozen python -m pytest -m 'not integration' -q -o 'addopts=' -W error
PROFILE_DELEGATE_TEST_RUNTIME=/opt/hermes PYTHONPATH=/opt/hermes /opt/hermes/.venv/bin/python -m pytest -m integration -q -o 'addopts=' -W error
```

## Fast feedback

```bash
PYTHONPATH=/opt/hermes /opt/hermes/.venv/bin/python -m pytest -q -o 'addopts=' test_reliability_reset.py test_tui_rpc.py
```

## Release gate

```bash
PYTHONPATH=/opt/hermes /opt/hermes/.venv/bin/python -m pytest -q -o 'addopts=' -W error
uv run --frozen ruff check .
uv run --frozen python -m py_compile \
  __init__.py child_bootstrap.py cli.py cli_smoke.py core.py \
  event_journal.py event_schema.py spectator.py tui_rpc.py tui_runner.py \
  scripts/validate_release.py \
  test_event_journal.py test_profile_delegate.py test_reliability_reset.py \
  test_run_reconciliation.py test_spectator.py test_sync_lifecycle.py test_tui_rpc.py
git diff --check
```

## Plugin registration and handler smoke

```bash
uv run --frozen python scripts/validate_release.py
```

This calls `register(ctx)` through a fake plugin context, asserts every manifest tool is registered with OpenAI-format `parameters`, checks version alignment, and invokes a harmless validation-error handler path. For a live install, use a fresh Hermes process after code/schema changes and verify plugin discovery before claiming the gateway sees it.

## Security/release checks

- Secret-pattern scan across tracked and intended new files.
- Confirm no `.env`, run artifacts, caches, `.venv`, private prompts, or machine-specific sensitive data are tracked.
- Verify `plugin.yaml`, README version, and `CHANGELOG.md` agree.
- Inspect staged diff before commit; stage intentional paths explicitly.
- Verify the pushed commit and GitHub Actions run on that exact SHA.

## Behavioral evidence

When transport behavior changes, add real harmless smokes for the affected path:

- simple synchronous execution;
- detached background completion and notification/status recovery;
- interactive steer/cancel and process cleanup.

P3 transport work cannot ship from unit tests alone.

## Result reporting

Record the latest release-gate result in `STATE.md` and residual work in `.hermes/handoff.md`.