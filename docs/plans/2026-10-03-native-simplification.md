# Native simplification of Profile Delegate

Status: accepted for complete local implementation and commit batches. Preserve current capabilities and artifact/tool contracts. No Hermes-core/profile/global-configuration edits, push, publication or gateway restart.

## Architecture and priority

Keep independent detached workers and Hermes-owned durable delivery. Herald's HTTP gateway and in-process subagent executors do not replace the installed profile/context, isolation and silent-notification contracts. Installed public single and batch async dispatchers accept a runner and finalize on a daemon executor. Single dispatch allocates an ID; batch dispatch accepts a caller-provided ID but uses batch result/completion formatting. The returned handle does not expose an executor join. Replacement must prove plugin result compatibility, completion persistence before dispatcher exit and silent-notification behavior; callback or ID support alone is insufficient. Native process completion waiting covers registered processes, not these async records. Optimization/integration and net reduction take precedence over complementary goal integration.

Use one preflight, one execution supervisor and one terminal-result decision/publication path, with distinct CLI and TUI evidence adapters. Keep execution, task, contract, transport and notification separate. Retain profile/model/provider/reasoning choice and frozen resume authority. No new orchestrator, bus, database, polling monitor or simulator.

## Dependency sequence

A. Verify clean baseline, consumers and reproducible metrics; reuse relevant previous evidence.
B. Consolidate terminal result construction, enrichment, publication and artifact/event validation. Keep transport-specific evidence and fail-closed publication races.
C. Share child preparation and preserve exact selection. Cover ignored TUI resume overrides with a focused regression; apply supported native session-scoped config.set before prompt.submit, respecting policy and native confirmation/error semantics, with no profile/global YAML writes.
D. Make detached worker the only durable completion producer; parent watcher only offers coherent published completion. Keep thread mode, notify=false, compatibility circuit breaker and recovery.
E. Remove proven redundant test families; measure net product and support reduction. Add only native GoalManager waiting for exact active caller/verified worker where supported; do not broaden architecture for silent/multiple/compression/new limitations.
F. Full canonical validation, independent final code/coverage review, then operator-controlled restart and affected real Discord/provider acceptance.

## Native reasoning limits

The installed CLI exposes an explicit reasoning option, but restoring a saved model/provider can subsequently replace that selection. A session-scoped TUI setter avoids YAML writes yet can run before the agent exists; deferred construction with a routable saved provider does not consume the pending reasoning override. Native eager resume builds before the setter, but can fail on an invalid saved route before an explicit replacement model/provider is applied. The attempted substitutions were rejected and existing reasoning preparation retained. Do not remove it based on parser/setter tests alone, introduce a core patch, or treat conditional adapters as the accepted simplification. Prove effective selection and route recovery together through supported native interfaces.

## Module ownership

core: stable APIs, preflight and authorization. execution: supervision and launch. contracts: result/artifact/event definitions. native: Hermes session and delivery seams. CLI/TUI adapters retain their native transport differences. Merge child_launch, native_resolution and event_schema into their owners only when dependency/test evidence supports the slice; movement does not count as reduction. Keep imports acyclic and compatibility entrypoints where actual consumers need them.

## Acceptance

Preserve six tools, CLI, new/resume, sync/detached, status/list, steering/cancel/timeout/recovery, output formats, explicit selection and frozen authority. Verify allowed/default and rejected selections, actual child identity, false-success rejection, publication races, detached launcher exit, native delivery and failure independence. Run focused tests per block and all gates from .agents/validation.md on the final candidate. No mock/harness acceptance substitutes for real affected runtime behavior.

Historical scope includes cli_smoke.py. Targets: production <=7253 physical lines, tests <=6908, cases <=654; count helpers/fixtures/scripts and report nonblank/noncomment too. No coverage weakening, case hiding, format compression or reclassification. If unsafe, provide evidence and leave that criterion pending. Measure comparable startup/async acceptance/memory/process cleanup; no unapproved material regressions.

## Worktree and evidence

One implementation writer; scoped verified commits, clean checkout between batches. STATE.md is current truth; .hermes/handoff.md points there. Preserve private incoming artifacts. Keep validation commands canonical; no forced template retrofit. Final delivery distinguishes committed, fresh-process tested and gateway-loaded code. Real activation/restart belongs to the operator.
