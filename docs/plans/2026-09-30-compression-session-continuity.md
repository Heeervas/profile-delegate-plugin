# Compression session continuity — implementation plan

Status: approved for scoped implementation by Reviewer pd_20260930_113540_r3ct87; all initial blockers closed. Approval covers the implementation contract, not implemented behavior or production activation.
Authority: complete-target local implementation and verification authorized by Alberto. No gateway restart, profile policy/config changes, core writes, DB migration, commit, push, publication, or production-run mutation. Preserve all incoming dirty changes.
Classification: focused runtime compatibility repair in existing agent-managed repository. Canonical commands: `.agents/validation.md`; keep existing docs/plans layout and portable .agents authority.

## User outcome / functional milestone

Internal functional milestone (not a public release): ongoing delegations remain inspectable, steerable, cancellable and resumable through parent/child compression, with trustworthy results and existing security boundaries preserved. New/reset/branched/unrelated sessions do not inherit model control merely by sharing a lane.

Supported: status/list/control after verified parent compression; child persistent identity refresh and subsequent explicit resume; existing native completion notification behavior. Exclusions: new delivery bus, lineage database/router, exactly-once claims, transport redesign, LCM configuration/engine repair, and broad reliability backlog.
Upgrade: additive plugin-local behavior; old artifacts remain usable only where host evidence suffices. No persisted-state migration. Recovery: revert only this task's scoped diff, preserving baseline edits; fresh processes required for activation. Loaded production gateway is not proof of changed code.

## Evidence and uncertainty

- core.py authorize_run requires exact ui_session_id/session_id/session_key precedence. Real read-only state.db observation links consecutive same-lane sessions with parent_session_id and end_reason=compression; logs then show status/steer origin_mismatch. Direct function probe reproduces changed durable ID refusal.
- tui_rpc.start_session captures persistent child_session_id once. tui_runner.persist_event does not refresh it from session.info; host exposes stored_session_id. This is a source-level defect hypothesis, not a proven live child failure.
- Native notification ledger already owns delivery; inspect existing watcher/ledger binding to verify compression does not accidentally inherit an obsolete parent authority or suppress delivery. Do not recreate that machinery.
- Host-native compression resolver semantics, DB authority, UI identity precedence, reset/fork boundaries, and real event updates must be verified before selecting the exact implementation seam.

## Choice and change-surface budget

Compare: (1) disable LCM/compaction (reject: defeats objective, not shown LCM-specific); (2) authorize same lane (reject: reset/session isolation breach); (3) custom lineage store/router (reject: coupling and explicit project prohibition); (4) narrow adapter using authoritative host compression identity/evidence plus host child events (preferred).
Trace the actual Hermes resolver and mutation path first. Reuse a native read-only resolver where its contract proves compression-only ancestry; otherwise use the smallest read-only proof over native session records, without plugin-owned graph/state. If this conflicts with the no-router project rule, Reviewer must resolve whether the minimal native-authority check is acceptable before build.
Provisional production surface: core.py, __init__.py only if contextual home must be passed safely, tui_runner.py; tui_rpc.py only if the actual host resume contract requires it. Tests in one focused continuity file plus existing owner tests where necessary. No unrelated cleanup. New state ownership, core patch, DB schema change, or a substantially larger surface triggers redesign/re-review, not patch accumulation.

## Execution graph and ownership

T1 native boundary inspection + plan review -> T2 incorporate blocking findings -> T3 implement coherent plugin slice -> T4 focused/full gates + real integration -> T5 independent acceptance review -> T6 fixes/revalidate and report.
Sequential: same mutable repository; one implementation owner. Reviewer is read-only; controller owns plan/state. Builder may own implementation only after explicit controller transfer; no concurrent controller code writes.

### T1 — native seams and independent plan review
Objective: prove authoritative compression continuation and child event identity contracts. Read core.py authorization/list/control/notification paths, tui_runner.py/tui_rpc.py; inspect /opt/hermes compression/session store/TUI paths read-only and profile-specific state authorities. Reviewer identifies blocking security, feasibility, coverage issues with exact source pointers.
Produces: independent verdict and smallest complete implementation recommendation. No code writes or live production mutations.
Acceptance: verified native resolver semantics distinguish compression from reset/branch and cross-profile/lane; child's UI vs stored IDs traced; actionable safe integration recipe.

### T2 — plan correction
Controller fixes every substantiated blocking finding without expanding scope. Rerun plan review if architecture/security gates materially change. Record accepted scoped authority/current next action in STATE.md; do not rewrite unrelated historical state.

### T3 — implementation
Production write surface as budget above, plus focused regression tests and minimal README/CHANGELOG/state/handoff updates required by project contract.
Parent: exact match remains fast path. A differing persistent session may gain existing action rights only from authoritative compression-only continuation evidence in the correct profile home and same lane/profile, respecting UI identity precedence. No fallback from conflicting unrelated UI identity. Missing, malformed, deleted, cyclic, forked or unverifiable lineage fails closed; refuse with actionable existing-compatible errors. Cover status/list/steer/cancel/duplicate admission where they use the affected authorization seam, without broadening global operator access.
Child: keep UI RPC handle distinct and stable; accept persistent identity changes only from trusted current-session host event/response, and native continuation evidence if needed. Publish latest valid child ID consistently to status/result/resume paths, preserving initial provenance as needed without new durable state ownership. Malformed/unrelated identity must not cause success or control another session. Preserve timeout/cancel/nonzero-exit and task/contract/notification semantics.
Acceptance: red regressions for both defects, green focused suite, no unrelated baseline regressions; no approval bypass.

### T4 — decisive validation
Commands are `.agents/validation.md` plus newly documented focused continuity command. Run complete frozen -W error suite, Ruff, compilation, registration handler smoke, lock alignment, diff and scoped secret scan. No fictional QUALITY_PASS; determine existing quality contract before claiming one.
Real integration reality gate: exercise fresh actual Hermes runtime/TUI/native compression in disposable isolated homes/session/run roots, no user-visible messages and notify disabled where needed; reuse existing safe scripts/helpers after checking script index. Prove parent compaction control continuity, child rotation and latest-ID resume, combined rotation result handling, and native notification route via strongest safe isolated path. Separate successful-completion and cancellation cases. Verify exact stored identities and reaped owned processes. Do not use synthetic event fixtures alone as live proof. If real forcing is unavailable without core/config/production mutations, stop expensive hardening, name the blocker and obtain the safe route; no compatibility claim from mocks.
Negative acceptance: /new/reset, branch, unrelated thread/profile/UI, missing/cyclic/ambiguous evidence denied; same ID behavior and legacy operator recovery preserved. Numeric budgets need host existing bounds or measured legitimate workload, not arbitrary new limits.

### T5/T6 — acceptance and corrections
Read-only independent Reviewer checks exact scoped diff, incoming-baseline preservation, evidence and all promised workflows. Fix substantiated blockers and rerun impacted/full required gates. Controller verifies returned artifacts and claims. Update STATE.md and .hermes/handoff.md with implemented behavior, exact validation and residual activation boundary. No release version bump unless independently required; no production activation inferred.

## Reviewer corrections — normative implementation contract

These requirements override less-specific wording above. All five findings from the initial review are accepted within the same user outcome; no unrelated remediation is authorized.

### Permission proof and host authority

Native resolve_resume_session_id/get_compression_tip equality is NOT permission evidence: they can select generic/preferred descendants and return partial chains. Implement one ephemeral, directional, read-only pair predicate from stored origin to candidate. Within one consistent native-database read snapshot, verify exact existing rows, immediate parent links and compression-ended predecessors at every edge. Exclude markers bound to the immediate parent (_branched_from, _delegate_from, _reset_from), source=tool, and native legacy-reset edges. Inherited markers referencing earlier ancestors must not reject legitimate subsequent compression. Require a unique eligible continuation at each predecessor; missing rows, malformed marker metadata, competing continuations, cycles, backward/unrelated paths or unfinished traversal deny. Use no new arbitrary depth cap: prove termination by visited records and the finite read snapshot; any safety budget must have an observed/source receipt and explicit incomplete-proof denial.

An ephemeral native-record predicate is compatible with AGENTS' no-router rule. No lineage persistence, redirects, canonical-origin rewrite, background discovery or notification rerouter. Parent proof reads only the trusted caller home captured from hermes_constants native context-local authority, never the target home/model arguments/run-root location or cross-database search. Child proof uses the already trusted target home from launch context. Persisted home may corroborate but cannot select authority. Open explicit existing state.db read-only (no SessionDB default writer/schema adoption), close deterministically. Namespace fields present in runtime, artifact and records must agree; contradictory profile/source/lane refuses. Legacy missing identity metadata allows exact existing behavior, but changed-ID continuity requires sufficient independent native namespace/UI evidence; absent proof denies actionably. Messaging lanes remain equal across compression; TUI stored/session keys may legitimately rotate when the exact UI handle and proven native chain remain valid. Conflicting UI handles must never fall through to a lane match. Test identical IDs in distinct databases and concurrent context-local homes.

### All affected consumers and duplicate admission

Use the same proof contract for authorization and continuity-aware status/list ownership metadata (belongs_to_current_session/origin_match_by); origin remains immutable. Define semantic request equivalence excluding only the proven rotating caller durable ID; all task/target/execution/options remain equal. Duplicate reuse must positively authorize the existing origin as a compression predecessor, including incoming artifact fingerprints. Serialize admission in a derived lock namespace scoped to trusted caller home and immutable conversation identity (UI handle when present; messaging lane otherwise), in addition to preserved exact-request locking as necessary. Sharing that admission lock does not grant control, and a reset must create its own run. Recheck matching under lock before creation. Do not persist a new canonical origin or silently merge unrelated requests. Test concurrent old/new-origin dispatch, legacy fingerprint compatibility and reset/foreign-run refusal.

### Child TUI and simple/CLI

TUI: process raw exactly-UI-correlated session.info before journal sanitization. Validate identifier types/format without stringifying malformed values; accept only current/equal or forward compression-proven target-home identities, never backward/unrelated changes. Publish accepted stored child ID immediately and consistently in existing status, result and terminal journal; retain initial request provenance. Cover callbacks during start/submit/control RPC, multiple rotations and completion/cancellation ordering. Native resume already returns resolved identity: do not add an unnecessary RPC. Check requested ancestor -> native resumed ID using the same target proof when different.

Simple/CLI: repair _execute_delegate_run's stable_session_id/footer comparison at core.py:2619–2654. A changed footer is acceptable only with target-home forward compression proof. Cover new-session rotation, resume compressed ancestor, rotation during resumed execution, changed ID in bounded transient recovery, unrelated/malformed footer. Preserve recovery limit/deadline, no fresh-session retry, nonzero-exit/timeout/cancel authority. New runs lacking a prior observed ID can publish the valid native footer as today; do not pretend that alone proves a chain.

### Notification separation

Keep existing native lane-routed completion and reset delivery semantics: receiving a notification after reset never grants status/steer/cancel rights. Do not retarget stored origins or couple delivery to the permission predicate. Inspect watcher home propagation as a scoped integration risk, not a presumed defect; change only if the narrow notification probe demonstrates wrong-home behavior.

### Executable isolated real-runtime gate

Disposable test homes/configuration and synthetic negative-test records inside a private temporary root are explicitly authorized; existing profile/config/credentials remain untouched. Use fresh native Hermes processes, real plugin registration/TUI RPC and compression/session persistence. A deterministic loopback model fixture is allowed for timing, clearly reported as fixture-backed real-runtime evidence, not vendor-provider evidence. No production credentials/connectors or platform messages. Assert launch/caller/target homes, OS HOME, run/lock/evidence roots resolve inside the scratch root. Inspect script indexes and reuse safe helpers first. Never run evals/desktop_bug_campaign/persistence_live.py unchanged.

Parent: invoke registered tools through real parent turn, hold child at a response barrier, accumulate history then manual native session.compress while parent idle; require changed stored ID, stable UI handle and actual DB compression edge. Exercise status/list/duplicate reuse and steer with observed child uptake. Child: native automatic compaction inside active turn via disposable settings and controlled multi-step model replies; manual compress on busy session is not a valid forcing path. Require actual rotation, immediate latest identity publication, completion and explicit resume recovering post-rotation history. Repeat combined rotation; cancellation separately. Exercise actual simple/CLI rotation/resume/recovery paths where practical, distinguish injected transient model failure from vendor outage evidence. Test actual reset/new/branch negatives and positive compression after an already branched/reset conversation; corrupted/ambiguous/cyclic records stay disposable and are labelled fixtures.

Notifications: isolated native parent poller alive, notification enabled only for isolated run, observe ledger completion AND consumed notification event, then read caller/target ledgers to prove home ownership. Queue acceptance is not delivery. Verify reset notification delivery without control access. Close/reap all owned processes, preserve redacted native events/DB/artifact evidence outside repo. If this narrow gate cannot run safely, report the precise boundary and do not claim compatibility or substitute mocks.

### Ownership and review closure

Controller owns plan/security decisions; implementation remains gated until revised plan review PASS. This is a coherent cross-cutting authorization+transport slice: after PASS, assign one Builder ownership of budgeted source/tests and project-required docs, with no nested delegation unless explicitly requested. Builder must preserve the incoming dirty tree, run T4, return exact evidence, and request no production activation. Controller commissions one independent acceptance review and owns corrections/final verification. Minimal authoritative state/handoff updates, not historical cleanup.

## Risks and containment

Primary risk: confusing channel continuity or generic parentage with authorized compression continuation. Mitigation: authoritative compression-only proof, profile-specific read-only authority, exact UI mismatch refusal and negative tests. Missing proof denies rather than transfers control.
Child risk: event identity drift could expose a stale resume target or mislabel result. Mitigation: current UI-correlated host identity, native proof where needed, consistent persisted latest identity and real rotation/resume exercise.
Incoming dirty tree: baseline __init__.py/tui_rpc.py/tests/STATE.md edits and unrelated untracked notification plan must remain intact. Record original diff and avoid wholesale revert/staging.
Residual: currently loaded gateway may keep old code; isolated fresh-process proof and live deployment are separate. LCM deepcopy disk-I/O fallback warnings are separate evidence and not scope for this fix unless they block the narrow probe.
