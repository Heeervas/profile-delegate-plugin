# Per-task approval drift — source-backed reconstruction

Status: historical diagnosis complete within the bounded sources below; implementation and independent acceptance are tracked separately. No production permission changes authorized by this document.

## Conclusion

Per-call selection existed and was deliberately removed during September reliability/security work. October's four-mode implementation expanded operator-configurable sources while preserving that removal. Reviews and acceptance then proved the substituted operator-only contract, not task-level selection. This is a requirements/authority distinction failure, not merely an unconnected schema field.

The legitimate security concern was that a model request is not itself an authority grant. The unjustified leap was treating **every explicit selection** as elevation, including deny or a mode already authorized for the caller. A configured omission default, admission authority, and task selection must be separate concepts.

## Timeline and evidence

### July 4: user explicitly requests YAML or tool-call selection

Source: default session `20260704_234059_8a7b9adf`, messages 127094, 127191, 127193, 127196–127197.

- User reported interactive approval prompts leaking from delegated children.
- Assistant initially coupled noninteractive operation with unconditional YOLO and hook acceptance.
- User requested independent review; assistant acknowledged that bypass was too broad and proposed an explicit policy.
- User's exact instruction, message 127197: **“Make it a config in the yaml or in the tool call, not required on the env by default.”**
- This explicitly supports tool-level selection; it does not authorize arbitrary requests to override genuine prohibitions.

### July 19: conditional per-call admission is present in code

Source: commit `29b1f0c`, `core.py`.

- Line 425 defaults `allow_child_approval_override` to true.
- Line 442 reads that operator-owned boolean.
- Lines 640–642 reject explicit selection only when the boolean is false.
- Lines 1912–1915 resolve explicit per-call mode before configured default.

This establishes a preexisting distinction between selectable task mode and operator permission to override. Commit dates establish repository history, not necessarily live deployment dates.

### September 27–28: security review turns selection into a forbidden override

Sources: default session `20260927_084119_7c1373fd`; user messages 255993, 256195, 256353; assistant message 256389. Reviewer run `pd_20260927_094839_mjau90`, `stdout.txt`, finding at lines 51–56. Plan `docs/plans/2026-09-27-reliability-and-steer-first-implementation.md`, lines 18–19. Commit `97d06f7` (September 28).

- User requested a multi-POV reliability review, emphasized steering, and authorized refining the plan with Reviewer then implementing it.
- Reviewer identified a real authority gap: a request field or caller-origin string cannot prove operator consent for elevation. It recommended default model-callable elevation off, operator policy remaining available, and a separately approved grant if true per-run elevation was required.
- Controller reported adopting “no model-supplied approval escalation.” The revised plan made previously permitted model-supplied elevation a compatibility exception.
- The implementation went further: schema changed from “Optional per-call child approval policy” to “Deprecated model-supplied approval override: rejected”; `validate_preflight` rejects every explicit mode. Operator override authorization no longer enables selection.

**Authority classification:** the overall reliability implementation was user-authorized. The restriction rationale and exact blanket rejection were agent/reviewer-added. No separate user instruction explicitly removing task selection was found in this inspected session. General implementation authorization is not evidence that the user knowingly selected that precise contract trade-off.

### October 1: four modes are added to the substituted operator contract

Sources: default session `20261001_081744_fea72391`, user messages 262608, 262700, 262767; review batch 262759; current historical PLAN/REVIEWS/ACCEPTANCE/OPERATOR files. Commits `6b5d02f` and `17fdf80`.

- User initially asked for broader Builder native permissions, then preferred **“deny / per-profile / inherit from delegator / yolo”**, with profile or inherit defaults and useful deletion allowed.
- User requested plan reviews and then explicitly requested detailed plan placement inside the plugin and Builder implementation.
- The controller framed review tasks as operator-configurable with no model-authored elevation. Reviewers evaluated that framing; one explicitly recommended keeping per-call source changes rejected as a cheaper initial approach.
- PLAN line 47 retained model rejection and said to avoid a new model selector. REVIEWS controller decisions retained it. ACCEPTANCE A8 treated rejection as a success criterion; OPERATOR recommended native Builder posture changes.
- Thus four underlying sources were implemented, but never restored as task-level public choices. Passing gates were evidence for another contract.

**Important nuance:** the October user message did not by itself explicitly spell out per-call versus operator selection. The earlier July instruction did; the current repair request resolves any remaining ambiguity explicitly. Do not claim the October implementation ignored an exact phrase that was not present.

### October 1 temporary test authority was narrow, not permanent configuration consent

Source: same October session, assistant 262793 and user 262794.

The controller asked to use an isolated temporary `approve_yolo` launch for Builder, restricted to this implementation and disposable tests, with production configuration unchanged. User answered **“Yes”**. That is affirmative authority for the described temporary run, not a permanent widening, not universal model authority, and not automatic authority for unrelated future runs.

### Post-restart smoke did not establish four-mode permissions

Source: default continuation `20261001_212056_2c4685`, assistant 263904–263908 and subsequent correction context.

Assistant acknowledged the successful Builder `printf` ran under deny and was already allowlisted. It then sought permanent Builder posture activation rather than exercising per-task selection. That smoke established basic launch, not the requested approval distinctions.

## Current repair starting point

Incoming HEAD: `17fdf80`; dirty package/import and runtime-dependency fixes preserved separately in `.artifacts/per-task-incoming/`. These fixes are not the historical cause of selection drift.

Observed current call path before repair:

`__init__._handler` → `core.delegate_profile` → `validate_preflight` unconditional explicit-field rejection → `resolve_request_approval` without requested selector → `native_resolution.resolve_native_approval` operator target/default choice → frozen `native_approval.snapshot` → request artifact → `child_launch` / TUI → `child_bootstrap.install_policy` → installed Hermes native guards.

## Unknowns / limits

- Bounded session and Git inspection cannot prove no separate private conversation ever authorized a restriction.
- Commit dates do not prove exact production activation timing.
- Historical acceptance/reviewer PASS claims are recorded as contract history, not independently rerun as evidence for the new repair.
- Native terminal floors are not arbitrary-Python/MCP/OS sandboxing.

## Repair principle

Allow explicit deny/profile/inherit/yolo through the public task API **within actual caller authority**. Reject precise unauthorized transitions, not the existence of a task selector. Keep omission compatibility, legacy alias, frozen resume/nesting, target admission, explicit prohibitions and hook separation independently testable. No production profile/config migration is part of this repair.
