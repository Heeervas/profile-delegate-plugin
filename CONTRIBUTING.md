# Contributing to Profile Delegate

Start with [README](README.md) for the operator/security contract and [STATE](STATE.md) for public-checkout truth. Read [AGENTS](AGENTS.md), [backlog](TODO.md) and [contribution opportunities](docs/contribution-opportunities.md) before choosing work. Opportunities are proposals, not tickets already opened; coordinate with the maintainer, especially parser/RPC/UTF-8 work that may overlap unpublished changes.

## Layout

Runtime modules intentionally stay at root for Hermes plugin discovery. Tests and their conftest live under `tests/`; helpers remain beside their current scenarios. Sanitized historical fixtures are under `tests/fixtures/profile_delegate/`. Scripts hold validation and separately authorized runtime harnesses. Plans/audits/reviews are indexed in [docs](docs/README.md); portable governance lives in `.agents/`, with `.hermes/` only a thin adapter.

## Validate a focused change

Use the exact commands in [.agents/validation.md](.agents/validation.md). Portable tests use the frozen plugin lock on Python 3.11–3.13. Native tests require the selected Hermes runtime's own Python 3.14 interpreter and real dependency closure; missing prerequisites fail rather than skip. Both partitions are required before merge. Do not install the plugin environment into the native runtime or mix another ABI's site-packages.

For a bug, supply a sanitized minimal reproduction and regression that fails before the fix. Preserve distinct safety/lifecycle scenarios; no case-count or line-count quota. Keep changes plugin-only and avoid unrelated refactors. Changes to plugin schemas/wrappers additionally require fresh installed discovery, not merely the FakeContext registration smoke.

## Issue/PR evidence

Include exact plugin/Hermes revisions, OS/Python, transport, expected versus observed output, actual commands/results and evidence class (fixture, real subprocess, installed runtime, real provider). Separate execution, task, contract, notification and transport outcomes. Steering ACK is queued, not proof of consumption. Cancellation evidence includes terminal state and owned-process cleanup. State failures and unvalidated boundaries plainly.

Never include secrets, private prompts/run artifacts or machine-specific sensitive paths. Use disposable homes for authorized runtime probes; profiles are not OS sandboxes. Do not bypass approval or use production configuration as a fixture. Operator harnesses refuse frozen delegated authority; that refusal is a boundary, not an invitation to clear environment variables.

No Hermes-core edits, plugin-owned outbox, exactly-once notification claim, production restart, tag, publication or configuration widening without separate scope. Keep version metadata aligned only for an explicitly approved release. Commit intentional reviewed files with conventional messages and verify exact-SHA CI before describing a published result.
