# Independent design reviews and synthesis

## Final implementation closure

Focused safety `deleg_96275bb8/task-0`: PASS strict historical observation evidence, deny containment and source extraction. Final differential review `deleg_44a4026d/task-0`: PASS argv/config-helper safety and model override refusal. Interrupted `deleg_0084765a` ended with upstream HTTP 503, not approval; its inspection was reused. Full final gate 599 passed; TOP feature quality PASS relative immutable incoming snapshot. Exact matrix/evidence: ACCEPTANCE.md. Earlier failing reviews below are historical inputs, superseded only for findings explicitly closed in final receipts. No activation authorized.

Three leaf agents reviewed the proposal and actual source from distinct scopes. They did not receive the complete final draft before finishing. Findings informed PLAN.md; no final code approval or runtime verification is claimed.

## Security/authority
Verdict: direction supported; authority contract required fixes. Accepted: profile/inherit are policy sources, not privilege ladder; target and ancestor explicit denies preserved; nested target switching cannot launder authority; headless context explicitly bound; arbitrary Python is not shell-enforced isolation; production bootstrap cannot silently execute unguarded; yolo does not inherently authorize hooks.

## Implementation/minimalism
Verdict: four modes supported at existing bootstrap seam. Accepted: single-query/unattended policy is separate from manual/smart/off; smart does not assess recognized unattended path; TUI can register unanswered approvals if callback-only design used; immutable narrow envelope and exact approval replacement prevent target allowlist leakage; migration preserves explicit deny and legacy broad alias. No core/parser/broker/framework expansion.

## UX/management control
Verdict: approve direction, profile alone not broad Builder autonomy. Accepted: meaningful source/provenance reporting, explicit Builder unattended deployment choice, recoverable approval_required vs policy_denied, no repeated bypass attempts, allowed scoped cleanup, task permission distinct from capability.

## Controller decisions
New-install selector default profile; inherit operator-configurable. Existing explicit deny unchanged. Legacy persisted omission stays deny. Model elevation remains rejected. Frozen effective snapshots exclude transient consent. Production posture selection remains a separate activation decision.

Design review transcripts (private local, not tracked): /opt/data/cache/delegation/live/deleg_f0075147/task-0.log, task-1.log, task-2.log. Research consulted first-party Claude Code, Codex, OpenCode and Hermes docs plus installed runtime code; portable research retained alongside this package.
