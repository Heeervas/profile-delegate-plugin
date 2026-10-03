# Profile Delegate handoff

Current authority, implementation and validation: [STATE.md](../STATE.md).
Accepted implementation: [native simplification plan](../docs/plans/2026-10-03-native-simplification.md).
Canonical checks: [.agents/validation.md](../.agents/validation.md).

Codex is the single implementation writer. Work proceeds in verified, scoped local commit batches with a clean checkout at boundaries. Preserve artifacts and unrelated changes. No Hermes-core/profile/global-config edits, push, publication or gateway restart. Optimization/integration and real net reduction take priority over complementary goal work.

Fresh-process provider and public-handler subcases now pass; they do not establish gateway activation or Discord delivery. Independent review is recorded; operator-controlled activation remains separate. Current evidence also includes native query-file input eliminating an observed tool/API roundtrip, the minimal CLI owner repair and a public persistent-spawn counterexample; see validation and goal boundary. Do not follow old paused-goal/restart checkpoints as current instructions: earlier handoffs are historical Git provenance.

Notification/operator fixture consolidation removes another 40 net test lines with identical test contracts and setup evidence. Native gate: 719 passed; portable: 238 passed. The initial detached-fixture timing failure and subsequent cleanup/isolated/serial passes remain recorded. That fixture batch preserves production from `61e138a`.

Status snapshot correction atop `50e8867` now returns/projects one bounded result read under the lock. The existing race case fails before and passes after; native CLI current/legacy/absent/invalid samples pass. Full native gate: 719 passed; portable: 238 passed. Production is -392 lines versus historical; test minima lack 1229 lines and 65 cases.

Latest exact candidate evidence and pending acceptance: [validation receipt](../docs/plans/2026-10-03-validation.md). The current Codex goal remains active; do not mark it complete or pause it based on historical Hermes checkpoints.
