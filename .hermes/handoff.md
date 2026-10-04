# Profile Delegate handoff

Managed-scope follow-up fixes the real parent-authority lookup bug; local absent/
present canonical regression and full 716-case gate pass. Focal safety review and
bounded quality exception recorded in docs/reviews/2026-10-04-managed-scope.md.
Parent must publish and verify exact-head GitHub jobs; no local Hermes provisioning.

Publication CI repair is locally tested and focal-reviewed; see STATE.md and
.agents/validation.md. Parent must run clean native integration against the
workflow-pinned Hermes revision through normal approval, then publish if green.
Do not retry/bypass frozen-policy PYTHONPATH rejection. All assertions/cases retained.

Current authority, implementation and validation: [STATE.md](../STATE.md).
Accepted implementation: [native simplification plan](../docs/plans/2026-10-03-native-simplification.md).
Canonical checks: [.agents/validation.md](../.agents/validation.md).

Policy resolution now shares one field registry, with ordered values/sources and error priority verified. Runtime metrics and final gates are recorded in STATE.md.

The latest CLI/TUI reasoning candidates were rejected; runtime files were restored. See STATE.md and the accepted plan for native restore/build limits before retrying overlay removal. Candidate-only gates are not release acceptance.

Codex is the single implementation writer. Work proceeds in verified, scoped local commit batches with a clean checkout at boundaries. Preserve artifacts and unrelated changes. No Hermes-core/profile/global-config edits, push, publication or gateway restart. Optimization/integration and real net reduction take priority over complementary goal work.

Fresh-process provider and public-handler subcases now pass; they do not establish gateway activation or Discord delivery. Independent review is recorded; operator-controlled activation remains separate. Current evidence also includes native query-file input eliminating an observed tool/API roundtrip, the minimal CLI owner repair and a public persistent-spawn counterexample; see validation and goal boundary. Do not follow old paused-goal/restart checkpoints as current instructions: earlier handoffs are historical Git provenance.

Notification/operator fixture consolidation removes another 40 net test lines with identical test contracts and setup evidence. Native gate: 719 passed; portable: 238 passed. The initial detached-fixture timing failure and subsequent cleanup/isolated/serial passes remain recorded. That fixture batch preserves production from `61e138a`.

Status snapshot correction atop `50e8867` now returns/projects one bounded result read under the lock. The existing race case fails before and passes after; native CLI current/legacy/absent/invalid samples pass. Full native gate: 719 passed; portable: 238 passed. Production is -392 lines versus historical; test minima lack 1229 lines and 65 cases.

Latest steering repair atop `be6a1a2` recognizes fresh native same-turn consumption, including concatenation/compression. Independent re-review approves raw read-only occurrence evidence; projected-history stale-row proof was rejected and repaired. Six necessary regression cases added. Native gate: 725 passed / 120.44 s; portable: 238 passed / 487 deselected / 6.54 s. Actual fresh CLI parent sends one steer and observes completed/ok/valid with one turn, native delivery to its exact parent, both owned processes gone and unchanged caller/target YAML. Discord/gateway activation remains unperformed. Native DB calls remain noninterruptible; expiry checks prevent false dispatch/completion.

Approval snapshot consolidation atop `8a40208` removes six physical/substantive production lines: one ancestor copy and one final deny normalization replace duplicated branches. Independent review reproduces 22,680 exact envelope/fingerprint/error comparisons plus 360 malformed-input/error-precedence comparisons; inputs and output isolation remain intact. Existing focused approval/native-guard coverage passes before/after (70 cases each); no test code or collected case changes. No YAML/core writes, activation or performance claim. Native full gate: 725 / 120.80 s; portable: 238 / 487 deselected / 6.98 s.

Repair/publication fixtures now share the existing explicit run builder. Four redundant cases were retired: three manual CLI phase positives already exercised through real producer/spectator paths, and one duplicated scope-enum assertion. Retained tests reject all four in-memory boundary mutations. Baseline/candidate focus: 252/248 passed; 28 retained definitions/decorators and 100 assertions are identical, and four fixture variants preserve paths, fields and permissions. This removes 32 physical / 22 substantive test lines; production remains exactly `b456407`. Native full: 721 / 121.10 s; portable: 234 / 487 deselected / 6.63 s. Private receipt: `repair-fixture-retirement/receipt.json`.

Journal recovery now retains only event types while decoding and checking sequence order, instead of keeping every decoded record and a separate sequence list. The unused private truncate wrapper is removed: 13 physical / 12 substantive production lines, with tests and cases unchanged. All 168 baseline/candidate comparisons preserve recovered state, append results, bytes and modes; 160 focused tests pass before/after and independent review approves. For 4,000 records on installed Python 3.14.7, seven alternating samples show median recovery time 29.77 -> 24.09 ms and a separately measured Python allocation peak 8.15 -> 2.28 MB. This covers journal recovery only; each cooperative append still rereads the file under its lock. Private evidence: `.artifacts/refactor-20261003/journal-recovery-pass/receipt.json`. Native full: 721 / 121.58 s; portable: 234 / 487 deselected / 6.46 s.

The native guard matrix retains all six profile postures and the maximally permissive deny/off/approve source. Five other deny variants produce exactly the same envelope and fingerprint; their repeated child guard checks and the duplicated root deny assertion are retired. The retained real-child case rejects omissions of mode, single-query or unattended normalization and the deny bypass guard. All 18 retained function bodies/arguments and production bytes are unchanged. Focus: 52 passed / 26.68 s before, 46 / 16.69 s after; independent AST, byte, snapshot and collection review approves. Six cases and four physical / two substantive test lines are removed; no scenario is hidden in a loop. Private evidence: `.artifacts/refactor-20261003/deny-matrix-retirement/receipt.json`. Native full: 715 / 110.56 s; portable: 234 / 481 deselected / 6.80 s.

Embedded JSON parsing now passes each candidate start index to the standard decoder, retaining the original input instead of copying its remaining suffix for every object. Absolute spans, candidate counts, malformed/ambiguity handling and output normalization are unchanged: 59,040 comparisons across 7,380 inputs agree; independent review reproduces another 168 comparisons across 21 boundary inputs. The exact baseline and candidate focused groups both pass 245 cases. An isolated seven-pair measurement on installed Python 3.14.7, 2,000 objects / 172,008 characters, shows median parser time 28.04 -> 19.42 ms; peak Python allocations remain about 2.20 MB. This is a bounded multi-object parsing measurement, not provider/workload/RSS acceptance. No lines or cases are removed. Initial overlapping focus and benchmark runs are excluded from comparisons. Private evidence: `.artifacts/refactor-20261003/json-decoder-index/receipt.json`. Native full: 715 / 109.64 s; portable: 234 / 481 deselected / 6.63 s.

Current metrics supersede the prior production minimum: production 7277 (-366 historical), tests 8139, support 969, cases 715. Required gaps: 24 production lines, 1231 test lines and 61 cases. All tracked Python is +96 versus historical / -248 versus incoming. Prior batch paragraphs above are provenance, not latest acceptance. Continue actual optimization and coverage-preserving reduction; keep complementary native goal work secondary.

Latest exact candidate evidence and pending acceptance: [validation receipt](../docs/plans/2026-10-03-validation.md). The current Codex goal remains active; do not mark it complete or pause it based on historical Hermes checkpoints.
