# Public repository housekeeping — 2026-10-04

## Scope and identity

Classification: governance repair/organization; complete-target housekeeping authority, not audit implementation. Entry was clean detached HEAD `9089f86d24346791aba01bdfe0f28779212dac45`, origin `https://github.com/Heeervas/profile-delegate-plugin.git`. No main-checkout inspection/copy/staging, product logic, child_reasoning, Hermes/core/profile/config changes, provisioning, restart, version/tag/push.

All runtime/support Python at root and scripts remains byte-identical to entry (`git diff --exit-code 9089f86 -- '*.py' ':!test_*.py' ':!conftest.py' ':!tests/**'`). Root cli_smoke.py stays because it is an executable operator helper, not a test module. Every root test module and conftest moved into tests/. Only 16 test path-reference substitutions were needed; shared helpers remain in their original test modules and imports retain pytest's existing sibling loading. pytest.ini adds testpaths and root pythonpath. No assertions, test definitions, parametrizations or scenario logic changed. CI compilation targets tests/*.py; quality exception only rebases its selector, preserving thresholds/baseline/approval/expiry.

## Recoverable organization

- PLAN.md → docs/plans/duplicate-call-prevention.md (unchanged).
- plans/2026-09-09-herald-comparison-and-roadmap.md → docs/plans/ (unchanged).
- .hermes/plans/2026-07-21_090037-profile-delegate-spectator-tui.md → docs/plans/ (unchanged).
- Historical STATE/handoff bodies → docs/archive/*-through-9089f86.md, with historical headers and navigable links; no substantive history deleted.
- Concise current STATE/TODO, contribution entry/opportunities, docs status map, AGENTS/BRIEF/README/changelog/landmarks and thin handoff reconciled. Old plan command snippets/source names remain historical rather than masquerading as current gates; docs/README gives the test path mapping and event_schema replacement.

Contribution claims were checked against current score/max-selection, blocking write/flush/deadline placement and decode calls. Prior reproduction assertions are labeled prior reported audit evidence, not freshly exercised fixes; issue/PR counts omitted. Baseline CI green is exact-SHA controller-provided evidence, not this child's GitHub readback. No new ticket/version or product fix introduced.

## Execution evidence

Ignored logs: `.artifacts/housekeeping/` in this worktree (parent may inspect; no prompts/secrets committed).

- Installed prerequisite passed: Hermes Python 3.14.7 and real import closure; equality with pinned CI source is not proven.
- Baseline full native: **716 passed / 128.62s**.
- Default candidate collection: **716**, normalized ordered node IDs exactly equal baseline after removing only tests/ prefix. Both SHA-256: `0954c5b6fd577ef38d7e9e974b0b19eb90d0b1873f8017cbe32000bd2351930b`.
- Explicit tests/ collection also completes; both commands exercise relocated conftest/discovery.
- Portable frozen partition: **234 passed / 482 deselected / 8.06s**.
- First full candidate: **715 passed / 1 failed / 128.76s**. Existing stubborn-cancel cleanup wall-time assertion observed 0.864747s against unchanged <0.8s; cancellation, ACK and SIGKILL/reaping preceding assertions passed. This failure is retained, not hidden or relaxed.
- Isolated same case: **1 passed / 3.30s**. Serial full repeat: **716 passed / 137.74s**.
- Explicit native integration: **482 passed / 234 deselected / 125.48s**. Native plus portable union retains 716 cases.
- Frozen lock/sync, Ruff, compilation of all root/scripts/tests Python, six-tool/one-CLI registration/validation-error FakeContext smoke, secret scan (0), diff checks pass. No installed-discovery claim: root runtime/manifest/schema unchanged; real discovery smoke was not newly needed or run.
- No provider/Discord/browser/activation acceptance is inferred or applicable to relocation.

## Quality and remaining gates

Same immutable canonical quality baseline `e46c84910ea00e0f4b8795cd2bfcc35378ce1cee`, STANDARD policy, installed builder-assurance scripts. Pre-edit report: **QUALITY_PASS_WITH_EXCEPTION**. Initial rename-aware staged/all candidate reports: **QUALITY_FAIL**: the collector treats edited renamed tests as additions in composed scope, unlike git diff -M which maps them at 94–99% similarity. Index scope also failed. No adapter/policy/baseline weakening or new exception; failure evidence retained. A committed-scope final report will distinguish the composed-snapshot limitation from actual new/worsened metrics.

Tool execute_code was denied by frozen child policy; not retried or bypassed. Normal permitted terminal/file/validation tools were used. A mistakenly supplied quality scope `staged` was rejected by argparse; corrected documented `index` invocation ran. No denied installation/execution was substituted.

## Independent review

Nested profile review initially refused non-deny selection; explicit deny narrowed
authority correctly, but `pd_20261004_140132_jqfl55` timed out/interrupted without
a verdict. This is not review approval. Independent local nested delegate then
reviewed the stable staged rename-aware diff and sources; transcript handle
`deleg_690e9b89/task-0.log`. Verdict: acceptable for local commit, no production or
test-behavior blocker; not quality/publication certification. Findings: stage this
receipt (resolved) and stale sync-lifecycle usage docstring (path-only corrected).
Reviewer confirmed unchanged production/test behavior, coherent conftest/CI paths,
preserved quality policy/exception and historical-vs-current documentation.

Committed-scope quality outcome is recorded after verification. Parent owns
exact-candidate CI, push and final announcement; historical audit findings remain
unresolved product work.
