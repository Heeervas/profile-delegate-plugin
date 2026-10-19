# Validation contract

Run from the repository root.

Dependency installation is lock-governed:

```bash
uv lock --check
uv sync --frozen
```

`pyproject.toml` and `uv.lock` declare the plugin Python 3.11–3.14 support window.
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
Never add another Python version's site-packages to PYTHONPATH. Python 3.14 is included in the plugin interpreter contract. Local isolated
provisioning and truly Hermes-free container validation are pending (see audit).

```bash
uv run --frozen python -m pytest -m 'not integration' -q -o 'addopts=' -W error
PROFILE_DELEGATE_TEST_RUNTIME=/opt/hermes PYTHONPATH=/opt/hermes /opt/hermes/.venv/bin/python -m pytest -m integration -q -o 'addopts=' -W error
```

## Deterministic changed-code quality (TOP)

The immutable repair baseline is `e46c84910ea00e0f4b8795cd2bfcc35378ce1cee`.
Validate policy before implementation; measure the integrated candidate after covered edits.
The installed Hermes interpreter provides jsonschema/PyYAML; the plugin uv environment does not provide jsonschema. Skills are read-only tooling, not repository write surfaces.

```bash
/opt/data/cache/scratch/quality-locked-env/bin/python .agents/quality-tooling/vendor/scripts/validate_quality_policy.py .agents/quality.yaml
/opt/data/cache/scratch/quality-locked-env/bin/python .agents/quality-tooling/vendor/scripts/quality_report.py --repo . --base e46c84910ea00e0f4b8795cd2bfcc35378ce1cee --scope all --level top --config .agents/quality.yaml --format json --output .agents/quality-report.json
```

Canonical JSON is local generated evidence, not proof of behavioral or release acceptance. Strong findings require repair or exact independently reviewed exceptions. Do not equate physical lines, Radon, Crapper and python_ast_v1.

## Release preparation automation (local acceptance; remote execution not claimed)

Acceptance owner: Adán/Alberto. Upcoming release is **1.12.0**, from existing
remote **1.11.0** plus explicit `minor`; never derive it from stale local 1.10.0.
Optional worktrees lead the release. Batch was already released in 1.11.0.

`Prepare release` is workflow_dispatch-only on the default branch. Native GitHub
CLI plus a stdlib script synchronize metadata, create/reuse a draft PR and call
reusable CI/quality workflows for the exact output SHA. No new third-party
release dependency, automatic test-run bump, tag, publication, force push or
trusted-quality bypass. GitHub's bot-created PR event may not trigger Actions,
so explicit reusable calls retain both required gates. The repository must allow
Actions to create PRs and have independently adopted trusted governance.

```bash
uv run --frozen python -m pytest tests/test_release_version.py tests/test_release_workflow.py -q -o 'addopts=' -W error --basetemp=/opt/data/profiles/builder/cache/scratch/release-focused13
UV_PROJECT_ENVIRONMENT=/opt/data/profiles/builder/cache/scratch/release-env314 uv sync --frozen --python 3.14
UV_PROJECT_ENVIRONMENT=/opt/data/profiles/builder/cache/scratch/release-env314 uv run --frozen python -m pytest -m 'not integration' -q -o 'addopts=' -W error --basetemp=/opt/data/profiles/builder/cache/scratch/release-portable14
```

Version tests use disposable file fixtures (real 1.11.0 → 1.12.0, patch/major,
byte-identical retry, stale/mixed/partial metadata, missing notes, malformed input).
Workflow tests execute the actual shell step against disposable Git remotes,
checking same-source retry, latest-tag refusal and conflicting-branch refusal.
Only gh and uv are mocked in those shell tests; live GitHub permissions/events
and remote CI remain untested locally. Real uv lock, registration, suites and
quality checks remain separate mandatory gates below. Partial writes fail closed;
recover by a fresh disposable checkout, never by re-bumping mixed metadata.

## Senior-review correction acceptance

Authority and acceptance ownership: `plans/senior-review-corrections.md`.
Run focused regressions after the owning writer has finished; then run the full
release gate and both mandatory partitions on the integrated candidate. Save
command output and candidate/ownership identity under `.artifacts/senior-corrections/`.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/opt/hermes /opt/hermes/.venv/bin/python -B -m pytest -p no:cacheprovider -q -o addopts= -W error --basetemp=/opt/data/profiles/builder/cache/scratch/senior-integrated-focused test_worktree_fixes.py test_worktrees.py test_multidelegate.py test_tui_runner.py test_tui_rpc.py test_event_journal.py test_prose_verdict.py
```

Required observations: foreign generic resume denied before frozen-authority
reuse; positive same-origin/compression continuity retained; worktree dedup and
preparation share one resolved SHA; malformed booleans refuse before allocation;
concurrency remains occupied during teardown; real local subprocess pipe bursts
exit without artificial termination and continuous output respects its deadline;
prose verdicts inside either Markdown fence type refuse; journal multi-writer
recovery preserves integrity/caps while cumulative read/parse cost scales linearly.
Do not substitute subprocess simulations for actual-provider completion or gateway
activation. A harmless fresh-process native transport completion/cancel smoke
must report its exact run IDs, native outcome and cleanup; active gateway reload
remains separately authorized.

## Fast feedback

```bash
PYTHONPATH=/opt/hermes /opt/hermes/.venv/bin/python -m pytest -q -o 'addopts=' test_reliability_reset.py test_tui_rpc.py
```

## Release gate

```bash
PYTHONPATH=/opt/hermes /opt/hermes/.venv/bin/python -m pytest -q -o 'addopts=' -W error
uv run --frozen ruff check .
uv run --frozen python -m py_compile \
  __init__.py child_bootstrap.py child_reasoning.py execution.py admission.py native.py native_approval.py cli.py cli_smoke.py core.py contracts.py worktrees.py batch.py \
  event_journal.py spectator.py tui_rpc.py tui_runner.py \
  scripts/validate_release.py scripts/release_version.py tests/test_release_version.py tests/test_release_workflow.py \
  test_child_reasoning.py test_multidelegate.py test_worktrees.py test_worktree_fixes.py test_event_journal.py test_profile_delegate.py test_reliability_reset.py \
  test_run_reconciliation.py test_spectator.py test_sync_lifecycle.py test_tui_rpc.py test_tui_runner.py scripts/verify_analyzer_equivalence.py
git diff --check
```

## Plugin registration and handler smoke

```bash
uv run --frozen python scripts/validate_release.py
```

This calls `register(ctx)` through a fake plugin context, asserts every manifest tool is registered with OpenAI-format `parameters`, checks version alignment, and invokes a harmless validation-error handler path. For a live install, use a fresh Hermes process after code/schema changes and verify plugin discovery before claiming the gateway sees it.

## Host-independent CI regression

Run the native partition without installed user personas or a global Hermes CLI:

```bash
HERMES_HOME=/opt/data/profiles/builder/cache/scratch/ci-empty-home PATH=/usr/bin:/bin PROFILE_DELEGATE_TEST_RUNTIME=/opt/hermes PYTHONPATH=/opt/hermes /opt/hermes/.venv/bin/python -B -m pytest -m integration -q -o addopts= -W error --basetemp=/opt/data/profiles/builder/cache/scratch/ci-repair-native
```

The first push creating a branch has an all-zero GitHub `before` and intentionally
cannot supply a trusted predecessor. A subsequent push must retain unchanged
reviewed governance from its real published predecessor; never substitute the
candidate as its own trusted base or disable governance verification.

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

## Analyzer and trusted enforcement acceptance

Provision a disposable isolated environment with `uv venv /opt/data/cache/scratch/quality-locked-env --python 3.13`, then
`uv pip install --python /opt/data/cache/scratch/quality-locked-env/bin/python --require-hashes -r .agents/quality-tooling/requirements.txt`.
The path is an operator-selected disposable environment, not a production dependency.

```bash
QUALITY_GATE_PYTHON=/opt/data/cache/scratch/quality-locked-env/bin/python /opt/data/cache/scratch/quality-locked-env/bin/python -I -B -m unittest discover -s .agents/quality-tooling/tests -v
/opt/data/cache/scratch/quality-locked-env/bin/python scripts/verify_analyzer_equivalence.py /opt/data/cache/scratch/quality-original-reference/scripts/quality_report.py .artifacts/quality-readiness/equivalence.json
/opt/hermes/.venv/bin/python /opt/data/skills/software-development/builder-assurance/scripts/quality_report.py --repo . --base e46c84910ea00e0f4b8795cd2bfcc35378ce1cee --scope all --level top --config .agents/quality.yaml --output .artifacts/quality-readiness/canonical-quality.json
```

The independent reference must match provenance.original_files, extracted from the preserved intake snapshot; never substitute the derived reporter. The shared canonical installation is read-only. Record exact canonical/vendor facts, gaps and exception. Trusted gate tests exercise real positive/negative disposable repositories. The current branch lacks committed governance, so direct first adoption intentionally refuses; review and controller adoption are separate, not bypassable local gates. Remote CI adoption remains unclaimed.

Use external `--basetemp=/opt/data/cache/scratch/<unique-run>` for local pytest so special filesystem fixtures cannot block runtime stamping. Scan secrets with `scripts/scan_secrets.py` and every nonignored intended-new path explicitly. Compile the CI list as well as the list above; CI no longer references removed event_schema.py.

## Reasoning adapter regression gate

Run `test_child_reasoning.py` with the installed native interpreter, then the complete native and portable partitions. Native helper compatibility is an admission check, not proof of behavior: upgrades must preserve explicit reasoning through CLI saved-route restoration and deferred TUI construction/recovery. Real affected acceptance must cover fresh and resumed CLI/TUI children, actual outgoing reasoning, unchanged profile/managed settings and retained managed browser enforcement. Never substitute an eager-resume-only or parser-only check for that gate.
