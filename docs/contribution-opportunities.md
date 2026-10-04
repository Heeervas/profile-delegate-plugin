# Profile Delegate: contribution opportunities

Repository: https://github.com/Heeervas/profile-delegate-plugin

## Status and scope

This is an issue/PR proposal document, not a list of tickets already opened. Check the live tracker and coordinate with the maintainer before starting work.

Public checkpoint: `9089f86d24346791aba01bdfe0f28779212dac45`. All four jobs passed: portable Python 3.11/3.12/3.13 and installed integration with pinned Hermes on Python 3.14.

CI: https://github.com/Heeervas/profile-delegate-plugin/actions/runs/37204513835

Green CI proves those checks passed; it does not establish universal runtime reliability. Some audit/reasoning changes exist in a separate local candidate and are not in public main. Before implementing a proposal, reproduce it against current main and check with the maintainer for overlapping work. Do not copy a private candidate or assume it has shipped.

The audited baseline was `e46c84910ea00e0f4b8795cd2bfcc35378ce1cee`. Subsequent public repairs changed CI fixtures and a managed-scope guard; the parser, RPC dispatch and UTF-8 findings below were not addressed by those repairs. Contributors should confirm each against their checkout before claiming a current reproduction.

## 1. Reject contradictory JSON task verdicts

**Suggested issue title:** Reject conflicting task statuses before scoring JSON candidates

**Type:** Bug; first correctness priority.

**Owner surfaces:** `contracts.py`; existing parser regressions in `tests/test_profile_delegate.py` / `tests/test_reliability_reset.py`.

The contribution source reports an audit reproduction when one recognized object says failed and a richer object says ok. Current-checkout inspection confirms list fields increase the candidate score and selection chooses the maximum score before equal-best ambiguity checks. Optional envelope fields must not establish authority over a conflicting verdict. Reproduce before implementing; this housekeeping pass did not execute the parser reproduction.

Reproduction input:

```text
{"status":"failed","summary":"validation failed"}
{"status":"ok","summary":"done","artifacts":[],"errors":[],"next_steps":[]}
```

Reported on the audited baseline: selected ok, two candidates, no parse error, wrapper success true; this is prior audit evidence, not a fresh execution claim.

**PR direction:** Detect contradictory recognized task statuses before scoring. Use the existing ambiguity outcome, preserve raw output, and prevent prose fallback from turning rejection into success. Do not treat arbitrary custom objects or execution statuses as task verdicts.

**Acceptance:**
- Both object orders reject the contradiction, including unequal scores.
- The public parse → normalization → wrapper path stays non-successful.
- A single valid ok envelope, custom output and documented fenced/prose recovery still work.
- Historical result artifacts are not rewritten.

## 2. Include RPC writes in the deadline

**Suggested issue title:** Bound TUI RPC dispatch under stdin backpressure

**Type:** Transport hardening; high-value bounded reproduction needed.

**Owner surfaces:** `tui_rpc.py`, `tests/test_tui_rpc.py`; runner only if propagation of an existing deadline requires it.

Code inspection found blocking write/flush before the response deadline. A gateway that keeps stdin open but stops reading can stall dispatch. The audit did not demonstrate a real installed Hermes hang; keep that distinction in the issue.

**PR direction:** First reproduce with a disposable subprocess that holds stdin open without reading. Measure pipe capacity, send a larger frame, and use an external watchdog to reap the baseline safely. Then make partial writes nonblocking and cover dispatch plus response with one monotonic budget, preferably using existing selectors and standard-library primitives.

**Acceptance:**
- Non-reading peer produces a bounded dispatch-specific error rather than an indefinite wait.
- A slow reader receives the complete frame without corruption.
- Time spent writing reduces the response budget.
- Partial-frame timeout makes the transport non-reusable and closes/reaps owned resources.
- Existing request correlation, late-response, cancellation and close behavior remains intact.

Do not introduce a durable queue, transport framework or production gateway stall to test this.

## 3. Preserve split UTF-8 in captured output

**Suggested issue title:** Decode CLI output and TUI diagnostic tails incrementally

**Type:** Bug; relatively contained entry point.

**Owner surfaces:** CLI capture in `core.py`; diagnostic streams in `tui_rpc.py`; their existing lifecycle/transport tests.

The contribution source reports `é` split into two byte chunks becoming replacement characters. Current-checkout inspection confirms independent `decode("utf-8", "replace")` in CLI capture (`core.py`) and diagnostic chunks (`tui_rpc.py`). JSON framing already assembles bytes before decoding; it is not the target of this repair. This pass did not inject runtime fragments.

**PR direction:** Use a separate standard-library incremental decoder per stdout/stderr stream. Flush incomplete sequences at EOF with the current replacement policy. Preserve capture limits, tail limits and truncation semantics.

**Acceptance:**
- Split two-byte and four-byte characters survive unchanged.
- Invalid and incomplete sequences retain explicit replacement behavior.
- Streams do not share decoder state.
- Bounded capture and truncation remain correct.
- Deterministic injected fragments detect the baseline defect; retain a real-subprocess control without relying on sleeps to force fragmentation.

## 4. Reproduce runtime behavior on independent installations

**Suggested issue title:** Add an independent Hermes compatibility and lifecycle smoke recipe

**Type:** Testing/documentation; useful without changing production code.

**Owner surfaces:** Development documentation and existing opt-in runtime harnesses.

The pinned CI job exercises real runtime dependencies, but its integration label does not mean every test runs an agent or contacts a provider. Independent installations can expose configuration assumptions that local tests miss, as the managed-scope CI failure demonstrated.

**Contribution direction:** Publish a compact reproducible recipe and sanitized results for CLI/TUI completion, explicit resume, transient recovery, active cancellation, steering and background notification. Record the exact Hermes/plugin revisions, interpreter, transport, OS and configuration shape. Declare provider use/cost; default to disposable homes and conservative approvals.

**Acceptance:**
- Completion separates execution, task, contract and notification outcomes.
- Resume/recovery proves the same session is reused, not silently restarted.
- Steering proves observed consumption/follow-up, not only an accepted queue ACK.
- Cancellation checks terminal state and owned-process cleanup.
- Notifications distinguish persisted, queued and delivered state; restart testing states at-least-once limitations.
- Reports include failures and uncertainty, with secrets/prompts/private data removed.

Profiles are context boundaries, not OS sandboxes. Never weaken approval policy or use production configuration as a fixture.

## 5. Make the TUI runner easier to review

**Suggested issue title:** Extract focused TUI lifecycle seams without moving state ownership

**Type:** Design proposal; agree on scope before a broad PR.

**Owner surfaces:** `tui_runner.py` and existing runner tests.

The audit identified concentrated lifecycle complexity. Complexity scores are inspection aids, not proof of a bug or a reason to split everything into classes.

**PR direction:** After correctness fixes, propose a small decomposition along real boundaries: preparation, event/control handling and terminal cleanup. Keep one clear owner of mutable run state, deadlines and terminal publication. Prefer existing helpers to new abstraction layers.

**Acceptance:**
- Name the duplicated/mixed responsibility removed and the change-surface budget.
- Preserve cancellation authority, steering uncertainty, timeout accounting, result publication and process ownership.
- Validate affected behavior with existing adversarial tests and a relevant real-runtime probe.
- Count added helpers in net complexity; do not move complexity into another monolith.
- No test deletion or line-count quota as the success criterion.

## 6. Improve executable quality checks without replacing behavioral evidence

**Suggested issue title:** Exercise repository quality policy in a reproducible changed-code gate

**Type:** Tooling proposal; coordinate with the maintainer because local work overlaps.

Public main now contains a quality policy/schema; a policy file alone is not an executable quality pipeline. A separate local quality-workflow candidate must not be described as published.

**Contribution direction:** Inspect the current policy and validation contract, establish immutable baseline/tool revisions, and wire a reproducible changed-code measurement path. Explain measured limits and existing approved exceptions. Do not silently lower thresholds or turn legacy debt into a blanket block on unrelated fixes.

**Acceptance:**
- Missing/invalid policy or unavailable measurements cannot produce a pass.
- Reports identify baseline, candidate, scope, tool versions and evidence gaps.
- Exceptions are narrow, reasoned, approved and expire.
- Gate behavior has positive and negative checks.
- Tests and real boundary evidence remain required; static scores are not a safety certification.

## Already addressed; do not open duplicate bugs

- Preflight fixture dependency on operator allowlists: the public CI repair isolated admission policy. Preserve negative refusal coverage rather than relaxing production policy.
- Obsolete compilation target and native approval fixture homes: repaired in `6cd0434`.
- Inherited managed scope disappearing from the reasoning guard's inspected environment: repaired in `9089f86`, with canonical scope present/absent coverage.
- Python 3.14 integration coverage: already supplied by `installed-integration`; its job name does not display the Python version.

## What to include in an issue or PR

- Exact plugin and Hermes revision, OS/Python version and transport.
- Minimal sanitized reproduction; expected versus observed behavior.
- Evidence classification: deterministic fixture, real subprocess, installed Hermes or real provider.
- Smallest proposed fix and regressions that fail before it.
- Actual validation commands/results, known gaps and cleanup evidence.

Start with a reproduction, focused test, documentation correction or small reviewed patch. Coordinate the parser/RPC/UTF-8 proposals with the maintainer before coding because an unpublished candidate overlaps. Keep Hermes-core changes separate, and do not add guaranteed-delivery or sandbox claims.
