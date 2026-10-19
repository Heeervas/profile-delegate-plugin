# Validation contract

Run from the repository root.

Dependency installation is lock-governed:

```bash
uv lock --check
uv sync --frozen
```

`pyproject.toml` and `uv.lock` retain the plugin Python 3.11–3.14 support window.
Portable tests use `-m 'not integration'`; native-coupled mixed modules are marked
integration conservatively in `tests/conftest.py`. Both partitions are mandatory; no
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
Never add another Python version's site-packages to PYTHONPATH. Python 3.14 is part of the plugin support contract. Exact-baseline GitHub CI passed both
partitions; local runtime equality with the CI pin is not established. Historical
provisioning blockers in the audit are not current CI status.

```bash
uv run --frozen python -m pytest -m 'not integration' -q -o 'addopts=' -W error
PROFILE_DELEGATE_TEST_RUNTIME=/opt/hermes PYTHONPATH=/opt/hermes /opt/hermes/.venv/bin/python -m pytest -m integration -q -o 'addopts=' -W error
```

## Fast feedback

```bash
PYTHONPATH=/opt/hermes /opt/hermes/.venv/bin/python -m pytest -q -o 'addopts=' tests/test_reliability_reset.py tests/test_tui_rpc.py
```

## Release gate

```bash
PYTHONPATH=/opt/hermes /opt/hermes/.venv/bin/python -m pytest -q -o 'addopts=' -W error
uv run --frozen ruff check .
uv run --frozen python -m py_compile *.py scripts/*.py tests/*.py
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

## Changed-code quality

Policy: `.agents/quality.yaml`; schema: `.agents/schemas/quality-policy-v1.schema.json`.
Immutable CI-repair baseline: `e46c84910ea00e0f4b8795cd2bfcc35378ce1cee`.
Stock STANDARD thresholds with the existing independently approved, expiring
managed-scope test-module-size exception (now `tests/test_profile_delegate.py`).
The installed builder-assurance tools
require PyYAML/jsonschema (available in the selected local Hermes venv).
This local prerequisite is not a new GitHub job or plugin dependency.

```bash
mkdir -p .artifacts/quality
# Set BUILDER_ASSURANCE_SCRIPTS to your installed builder-assurance scripts directory.
/opt/hermes/.venv/bin/python "$BUILDER_ASSURANCE_SCRIPTS/validate_quality_policy.py" .agents/quality.yaml --schema .agents/schemas/quality-policy-v1.schema.json
/opt/hermes/.venv/bin/python "$BUILDER_ASSURANCE_SCRIPTS/quality_report.py" --repo . --base e46c84910ea00e0f4b8795cd2bfcc35378ce1cee --scope all --level standard --config .agents/quality.yaml --format json > .artifacts/quality/quality-final.json
```

Other operators substitute installed tool paths, preserving baseline/policy/scope.

## Relocation checks

```bash
PYTHONPATH=/opt/hermes /opt/hermes/.venv/bin/python -m pytest --collect-only -q -o 'addopts='
PYTHONPATH=/opt/hermes /opt/hermes/.venv/bin/python -m pytest tests --collect-only -q -o 'addopts='
uv run --frozen python scripts/scan_secrets.py
```

Compare node IDs to the immutable pre-move collection after removing only the
`tests/` prefix. All scenarios, parametrizations, assertions and marker partitions
must survive. Stage intentional relocations before rename-aware quality reporting.
Housekeeping receipt records the command/tool paths actually used. No browser,
frontend build or provider smoke is applicable to documentation/test relocation;
operator runtime harnesses remain separately authorized, never approval bypasses.

## Trusted quality enforcement and release automation

Effective quality floor: TOP. Policy and immutable baseline remain canonical;
repository-vendored analyzer is derived from builder-assurance with documented
provenance. Preserve both independently approved expiring exceptions. Governance
adoption requires separate independent review; candidate changes cannot approve
themselves. See `.agents/quality-tooling/README.md` and the review receipt.

```bash
uv venv .artifacts/quality-env --python 3.13
uv pip install --python .artifacts/quality-env/bin/python --require-hashes --only-binary :all: -r .agents/quality-tooling/requirements.txt
.artifacts/quality-env/bin/python .agents/quality-tooling/vendor/scripts/validate_quality_policy.py .agents/quality.yaml
.artifacts/quality-env/bin/python .agents/quality-tooling/vendor/scripts/quality_report.py --repo . --base e46c84910ea00e0f4b8795cd2bfcc35378ce1cee --scope all --level top --config .agents/quality.yaml --format json --output .artifacts/quality-final.json
QUALITY_GATE_PYTHON="$PWD/.artifacts/quality-env/bin/python" .artifacts/quality-env/bin/python -I -B -m unittest discover -s .agents/quality-tooling/tests -v
uv run --frozen python -m pytest tests/test_release_version.py tests/test_release_workflow.py -q -o 'addopts=' -W error
```

Release fixtures prove existing1.11.0 -> minor1.12.0, patch/major, same-input
byte-identical retry, malformed/stale/mixed/partial metadata and missing notes.
Workflow shell executes against disposable Git remotes; gh/uv alone are mocked
there. Real dependency, registration, full suites and quality remain mandatory.
`Prepare release` calls reusable CI/quality for exact SHA because bot-created PR
events need not trigger Actions. No automatic version increment during test runs,
force push, tag or publication. Remote Actions PR permissions are prerequisites.

Use an external disposable `--basetemp` for local pytest; all scenarios and native
prerequisites remain mandatory. Secret-scan staged intended source, not private
artifacts. A release tag still requires explicit operator authorization after
exact-head CI, per AGENTS.md; pushing a candidate alone does not create a release.
