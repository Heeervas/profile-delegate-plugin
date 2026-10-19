# Profile Delegate — v1.12.0 source candidate

## Senior corrections integration into main

Alberto explicitly authorized merging `review/senior-corrections-20261019`
(`243521e3813f82866d31f080833562377c719d06`) into main. Integration preserves
published main `13c23a54407c7845b7145f9d73cb450ead709b05`, including tests/ layout,
public documentation, trusted governance (both existing exceptions), and the
inherited-managed-scope security fix in core.py. No force push or activation.

The reviewed resume authorization, strict booleans, admitted worktree SHA,
fenced verdict, incremental journal and TUI teardown/reaping fixes are retained.
Integrated local suite: 932 passed (includes main's extra managed-scope case).
Lint, lock, registration, secret scan and TOP quality gate passed with existing
exceptions. Exact-head GitHub checks must pass before claiming remote completion.
Exceptional process.wait failure can retain a stale slot/status: documented
conservative residual risk, not false success; see TODO.md.


## Authority and identity

Alberto authorized committing and pushing the complete accepted worktree candidate
and release automation. Integration starts from published main
`a5488e0d705ae5347858c2ae8b9079347bb0e0e6` (v1.11.0), preserving its relocated
tests, public governance/docs, multi-dispatch and inherited-managed-scope security
fix. The different dirty local candidate was privately snapshotted first.
No force push, tag movement, gateway restart, Hermes-core or profile/global change.
A new tag/GitHub Release requires separate authorization; this is source delivery.

## Changes

- Optional Git worktrees with explicit base/new branch and CLI/TUI continuation
  in the assigned checkout. No sandbox, dirty/ignored-file copying, auto-merge or cleanup.
- Batch was released in1.11.0; composition now retains workspace handles.
- Python >=3.11,<3.15; portable3.11–3.14 and pinned installed-Hermes3.14 test scope.
- Opt-in semver release preparation synchronizes five metadata files and calls
  reusable full CI and trusted quality. Ordinary tests never bump versions.
- Accepted bootstrap/reasoning/TUI repairs included, retaining remote security fixes.

## Verification / remaining gate

Canonical commands: [.agents/validation.md](.agents/validation.md).
Prior private independent acceptance covered real CLI/TUI new/resume, same-base
isolated edits and single-writer integration. Publication is not activation.
The actual integrated automated gates and independent integration review must
pass before push; exact-head Actions readback is required before a green claim.

Immutable quality baseline remains `e46c84910ea00e0f4b8795cd2bfcc35378ce1cee`.
TOP retains both bounded independently approved exceptions: public signature and
remote managed-scope regression module. No baseline advance or weakened thresholds.
First governance adoption needs separate independent review and an established
trusted commit; no self-approval switch is permitted.

Initial integration failures in fixture paths, workspace projection and synthetic
imports were corrected without dropping assertions/cases. The first repaired full
run had a stubborn-process timing failure (0.918s versus0.8s), retained privately.
The unchanged timing assertion then passed focused and serial full release runs:
**835 passed**, warnings as errors,148.46s. Python3.14 portable: **253 passed,
582 deselected**. Ruff, compile, frozen lock, registration/handler smoke, native
prerequisite, secret scan and independent gate regression suite passed locally.
Fresh TOP full-scope report is QUALITY_PASS_WITH_EXCEPTION with no evidence gaps.
Independent integration review PASS_WITH_NOTES approved exact governance bytes.
Governance-only adoption `5a13610c33144b1ac58f917cbe7addb9b031e375` was pushed
normally and its remote SHA and all approved blobs read back. Its quality run
39227444924 failed closed as expected because the previous remote lacked trusted
tooling; this bootstrap failure is not a green. The separate source push uses the
adopted governance unchanged. Exact-head source CI results belong in the final
operator receipt; no tag, GitHub Release or gateway activation is implied. Local installed
runtime equality with the immutable CI pin is not claimed. Existing TODO remains.
