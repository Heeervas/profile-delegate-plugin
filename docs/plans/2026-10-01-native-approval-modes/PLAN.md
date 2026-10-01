# Native approval modes — complete local implementation plan

## Authority and outcome

Authority: **complete-target local implementation**, explicitly requested by Alberto: prepare this plan inside the plugin, then delegate to Builder to fix. The earlier plan-only restriction is superseded for this feature only. Builder owns implementation and verification; controller owns acceptance and user-facing activation approval.

Deliver one functional internal milestone: operators can select `deny`, `profile`, `inherit`, or `yolo` for Profile Delegate, with `profile` the new-install default and `inherit` a configurable alternative. Native profile/caller policies govern normal execution without a second command parser. Scoped deletion is permitted when native policy permits it; no plugin-mandated recursive-deletion ban.

Authorized: plugin-local code/tests/docs, reversible local changes, isolated disposable integration probes using existing runtime/provider access, scoped project metadata, and an independent final review. Not authorized: Hermes-core writes, production config/policy edits, gateway restart/deployment, production-run mutations, credentials, commit/push/tag/publication, destructive cleanup of existing files, or unrelated continuity work. Disposable fixtures may be created/updated/deleted in the isolated probe lifecycle; never use valuable user data as a deletion test.

## Repository structure and ownership

This mature repo's `.agents/skill-routing.md` makes `docs/plans/` canonical. Preserve it; do not migrate historic plans or create duplicate root `plans/` governance.

Package:
- `PLAN.md`: normative product and implementation contract.
- `STATE.md`: this feature's state, authority, cursor and blockers.
- `REVIEWS.md`: scoped review conclusions and resulting decisions.
- `evidence/`: sanitized reports/test receipts only; no private prompts, provider tokens, production transcripts or runtime databases.

Repo `STATE.md` links here without erasing continuity status. `.agents/validation.md` remains sole command authority. Existing runtime artifacts remain outside the repo in private configured run directories. Builder is sole implementation writer once dispatched; controller must not edit its owned code concurrently.

## Current evidence

Source inspected: `core.py`, `child_bootstrap.py`, `tui_runner.py`, `__init__.py`, existing tests; installed read-only `/opt/hermes/tools/{approval,approval_context,approval_floors,delegate_tool_config,delegate_tool_toolsets}.py`.

Current modes: `deny`, `approve_yolo`; model per-call elevation rejected. Caller plugin policy determines approval; no target-specific selector. Deny rejects dangerous command categories before native preapprovals and rejects local execute_code. Yolo invokes native guards but ordinary approval scans are bypassed. Native `approvals.deny` terminal rules still apply on normal terminal paths, not arbitrary Python. Native unattended policy is distinct from manual/smart/off. Smart assessment is not invoked by the recognized unattended approve/deny path.

Existing dirty files on handoff: STATE.md, __init__.py, core.py, test_profile_delegate.py, test_tui_rpc.py, tui_rpc.py, tui_runner.py; untracked continuity plans/test. These are existing work, not permission to reset/reimplement it. Inspect current git state and active ownership before editing. Snapshot incoming changes outside tracked product files; preserve exact incoming content. Missing administrative certification is not a reason to replay old continuity work. If another live writer owns overlapping files, transfer ownership or block; dirty state alone does not block this task.

Isolated guard probe already proved approve_yolo composition allowed build/test/commit command strings while explicit rm/git-push deny rules blocked supplied strings. It executed no supplied command and is NOT live delegated acceptance.

## Chosen architecture

Extend existing resolution → request artifact → bootstrap seam. Do not build a permission service, new parser/classifier, approval broker, policy-containment engine, general config-overlay framework, or transport rewrite. Target-specific operator selection is needed for current consumers, not future abstraction.

Alternatives rejected: global yolo widens unrelated targets; giant allowlists do not repair early deny; custom development mode duplicates native behavior; immediate OS sandbox project exceeds goal.

### Configuration contract

Retain `plugins.entries.profile-delegate.child_approval_mode` as operator default; extend accepted values to deny/profile/inherit/yolo. Accept `approve_yolo` as backward-compatible alias for yolo. Add one operator target map `child_approval_modes_by_profile: {builder: profile, reviewer: profile}` in the same plugin entry. Validate map keys against valid configured target profiles, values strictly against mode vocabulary, malformed entries fail before artifact/run creation.

Precedence: existing explicitly supported operator environment global override, then operator per-target map, then operator global YAML value, then default. Preserve current env names/meaning; do not invent unsupported env behavior without a current consumer. Expose source provenance; contradictory inputs resolve through documented precedence, malformed values do not broaden.

Default migration: omitted mode on a new configuration resolves profile. Existing explicit deny remains deny; approve_yolo retains broad behavior. Existing stored requests/results without new envelope fields keep their historical meaning (legacy omission was deny). Do not silently reinterpret old resumed artifacts under the new default. Documentation must distinguish new configuration omission from old persisted-run omission. No production config migration in this task.

Model-facing `child_approval_mode` remains rejected for elevation; avoid introducing a new model selector. Explain operator config and exact remediation in preflight. Capability preset remains separate.

### Mode definitions

- deny: preserve existing strict behavior and immediate no-prompt refusal, including its distinction from ordinary native preapproval handling.
- profile: resolve target native approval settings; do not import caller session YOLO/preapprovals. Remove plugin early blanket rejection on this path and use native terminal/execute_code decisions in deterministic unattended context.
- inherit: snapshot caller effective native approval settings and native permanent preapprovals. Exclude credentials, whole config/environment, callbacks/queues, requester identity and transient session grants. Operator-enabled caller YOLO is captured only when this delegation source is inherit and operator target admission allows it. Target explicit native deny rules remain applicable; ordinary target-only grants must not leak into caller snapshot.
- yolo: operator-chosen ordinary approval bypass. Preserve native guard behavior where applicable; do not silently consent to shell hooks because approvals were bypassed.

Profile/inherit are **policy sources**, not ordered privilege levels. Off/approve can make profile broader than inherited manual/deny. Report resolved native settings and unattended behavior.

### Policy envelope and lifecycle

Resolve once before launch into a bounded non-secret versioned approval envelope in existing request artifacts: schema version, source selector, operator provenance, caller/target identifiers, native approval subset, permanent preapproval list, effective bypass, unattended policy, relevant inherited deny constraints, and lineage admission. Reuse existing artifact/private-mode discipline and fingerprints; no separate durable store.

Transfer only fields needed by installed native guards, including approvals.mode, deny and native single_query/unattended behavior plus permanent command_allowlist. Inspect actual config keys/readers first; do not copy all security/config fields. Native defaults must be explicit in evidence. Preserve pertinent target guard settings rather than accidentally replacing unrelated native security configuration.

Exact replacement is required for ordinary inherited approvals/preapprovals: deep-merge overlays can accidentally retain target allowances. Use the smallest child-only native config-reader/config-overlay seam proven against actual startup/import/cache order. Do not mutate target profile files or parent process global config. If unsupported, return actionable compatibility blocker, not fallback to yolo.

Resume/recovery reuse frozen envelope. Legacy missing envelopes resolve by legacy semantics; malformed present envelope blocks. Explicit operator authority refresh requires a new snapshot/admission, not mutable mid-run widening. No new model-callable consent refresh needed.

### Unattended and transport behavior

Simple and TUI must observe equivalent native no-human semantics, despite native TUI setting interactive/gateway flags. Bind actual recognized unattended context, install policy before agent construction/cache initialization, and verify no unanswered pending queue/input() fallback.

Manual with unattended deny honors applicable native preapprovals; fresh consent returns structured approval_required promptly. Unattended approve/off allow according to native behavior; smart plus unattended approve/deny does not promise LLM screening. Whole-script execute_code follows native backend/host-access rules. Isolated backend and Docker bind-mounted host access must be distinct.

Production bootstrap failure must fail closed. Preserve legitimate test shims explicitly as test-only; missing-module/direct-exec fallback must not launch a real delegated process without installed policy. Audit current automatic HERMES_ACCEPT_HOOKS behavior; remove implicit coupling for new selectors, preserve explicitly operator-authorized hooks and document any legacy compatibility impact rather than granting extra consent.

No approval broker in this feature. Classify approval_required vs policy_denied in existing error/result surfaces; provide source, partial-progress inspection and operator recovery guidance. Do not bypass denial through another interpreter/tool/profile.

### Nested authority

Keep existing depth/origin/target admission contracts. Deny ancestry stays deny. Carry ancestor explicit native prohibitions and apply alongside target prohibitions. A nested call cannot obtain a new broader bypass/unattended posture or switch to an incomparable profile source unless operator configuration explicitly admits that lineage edge. Use a minimal explicit admission mechanism only if existing authorized-target semantics cannot express it; implement/document the exact requirement, not a general permission lattice. Reject unsupported transitions before spawn rather than infer glob containment.

Review and integration must prove target hopping cannot erase applicable constraints. Do not claim arbitrary-code isolation: native shell denial does not police arbitrary subprocess/Python/MCP/API actions. Written task boundaries remain necessary and not mechanically enforced by this selector.

## Functional milestone

Internal milestone: native approval-source selection (not public version bump).
Promise: a trusted Builder can use its configured native unattended posture; other profiles can keep theirs; inherited execution is explicit, reproducible, inspectable and non-hanging.
Workflows: new/resume, sync/TUI, four modes, per-target override, existing legacy artifacts, structured blocking, scoped disposable deletion.
Exclusions: production activation, human approval relay, arbitrary-code sandbox, live session-grant copying, unrelated continuity repairs, public release.
Upgrade: preserve explicit prior modes and historical artifacts; new omission profile. Rollback: restore only feature-owned changes/config selection, preserve baseline unrelated edits and run evidence. No destructive git reset/clean.

## Execution DAG and tasks

T0 baseline/ownership → T1 smallest real native-boundary probe → T2 resolution/envelope → T3 bootstrap+transport application → T4 tests/docs → T5 real delegated validation → T6 independent review/fix → T7 handoff. One Builder owns shared code; review is read-only. No parallel writers or redundant review branches.

### T0 — establish baseline
Objective: preserve existing changes and identify exact native seam. Writes: package STATE/evidence only plus private incoming-change snapshot. Inspect repo contracts and active ownership. Produce baseline diff/untracked inventory and function-level change budget. Acceptance: incoming edits retained; scoped plan linked; no core/prod changes. Recovery: original snapshot, never reset all dirty work.

### T1 — integration reality gate
Objective: prove native policies can be bound deterministically before expensive implementation. Read `/opt/hermes` only; use disposable private child context with plugin bootstrap and real native guard entrypoints. Probe profile/caller config lookup, manual/smart/off × unattended behavior, execute_code, target deny preservation, TUI-startup context. Produce actual results and proposed smallest seam. Stop for concrete incompatibility/authority blocker, not admin metadata. Mock schema tests alone do not satisfy this gate.

### T2 — resolution and snapshots
Depends T1. Provisional writes core.py, __init__.py, existing or focused approval-mode tests. Implement config precedence, validation, aliases/default migration, envelope/provenance, persisted fingerprint/reuse/resume semantics, and model no-elevation checks. Produce tests asserting source and exact policy fields. No leak of transient consent/target ordinary grants.

### T3 — enforcement adapter
Depends T2. Provisional writes child_bootstrap.py, tui_runner.py, core.py environment/launch seam and narrowly needed tests. Apply native profile/inherit policies before construction; normalize unattended transport; preserve deny and legacy broad behavior; decouple hook consent; fail closed on uninstalled production policy. No unrelated tui_rpc/continuity rewrite. If design expands into new state service/parser or broad host changes, reconsider against the native seam rather than patch incrementally.

### T4 — verification and operator docs
Depends T3. Writes README.md, CHANGELOG.md (unreleased, no version manufacturing), policy/schema descriptions, tests, package evidence, scoped STATE/TODO/handoff updates. Explain defaults, per-target settings, inheritance exclusions, smart limitation, deletion and sandbox distinctions, no-broker blocking/recovery, migration. Validation commands stay `.agents/validation.md`; add a focused command there only if needed and verified.

### T5 — real end-to-end probes
Depends T4. Use disposable profile/home/workspace and existing allowed credentials via approved runtime mechanisms; never copy secrets into repo/evidence. Exercise real provider-backed delegated project write/read, code execution and build/test; explicitly create/delete disposable fixture for authorized cleanup. Run simple and detached TUI using local evidence/no unsolicited external messages. Test forbidden operation refusal without executing valuable destructive commands, unaffected profile policy, resume snapshot, nested escalation denial, and steer/cancel where adapter startup impacts them. Verify exact file/guard/result/process state, not worker assertions. Mark unavailable paths unvalidated and block full completion if named criteria remain unmet.

### T6 — independent review and fixes
Depends T5. Reviewer inspects exact diff, baseline provenance and acceptance matrix. Builder fixes concrete findings and reruns affected tests/real gates. Existing three design reviews are input, not substitute for final code review. Reuse nested reviewer result; controller must not commission duplicate review blindly. No need for three more reviewers.

### T7 — complete handoff
Depends T6. Update feature/repo state with implemented behavior, exact validation output, gaps, changed files and activation instructions. No production restart/config activation. Controller independently verifies artifacts/diff/test claims before reporting done.

## Acceptance matrix

A1 four modes and per-target precedence: parsed source and preflight evidence; invalid mode/map fails before run/artifact creation.
A2 compatibility/default: new omission profile, explicit deny unchanged, approve_yolo alias broad, legacy missing envelope deny; deterministic resume.
A3 profile isolation: caller yolo/grants absent; target actual settings govern.
A4 inherit: caller snapshot exact; no target-only ordinary grants; target/ancestor denies preserved; no transient consent/secret transfer.
A5 native behavior: manual/smart/off × single-query/unattended approve/deny documented from actual installed runtime; terminal and execute_code separately tested.
A6 no hangs: sync/TUI request fresh consent yields immediate actionable blocking and no orphan approval waits.
A7 scope/deletion: permitted disposable cleanup succeeds; plugin does not impose blanket deletion prohibition; native refused operation not retried through bypass.
A8 authority: model override, unauthorized target and nested widening fail before execution; authorized lineage transition works if supported contract declares it.
A9 lifecycle: envelope fixed on recovery/resume, no broader duplicate reuse, controls/completion retain current contracts.
A10 safety: applicable native terminal floors survive yolo; hooks not newly auto-consented; production bootstrap failures fail closed; no sandbox claims.
A11 release contract: full repo gates, registration and handler smoke, secret scan/diff inspection; unrelated incoming edits preserved; no activation/publication.

## Canonical validation

Run repository `.agents/validation.md` exactly from repo root: frozen lock/sync, full `-W error` pytest, Ruff, compilation, diff check, registration/handler smoke and security checks. Include all new Python files in syntax validation. Use narrow tests for development, full gate at handoff. Record commands, exit codes, summaries and real probe IDs/private evidence pointers. Do not paste secrets/private transcripts into tracked reports. No invented budgets/timeouts; preserve measured existing limits and explain any necessary adjustment.

## Risks and recovery

- Policy source confusion → explicit provenance and cases A3/A4; never infer permissiveness from enum order.
- Silent widening on upgrade/resume → A2/A9 and unchanged explicit old config.
- TUI unanswered prompts → T1/T3/A6; no broker fallback.
- Nested target laundering → A8 + preserved prohibits; unsupported transition fail-closed.
- Arbitrary code exceeds shell controls → truthful limitation and task boundary; not solved by this plan.
- Shared dirty continuity files → T0 incoming snapshot and surgical edits; no historical gate replay merely for bookkeeping.
- Runtime native API drift → T1 compatibility gate and actionable unsupported result.

## Builder deployment guidance (prepared, not applied)

Recommended selector default is profile, inherit optional. To make Builder broad while direct interactive manual behavior remains available, operator may separately choose native `approvals.single_query_mode: approve` and `approvals.unattended_mode: approve`; this is unattended approval, not smart screening. Alternative native off bypasses ordinary checks more broadly. Do not choose/apply production posture during implementation. Provide exact candidate config and consequences in final handoff for Alberto's activation decision.
