# 0002 — Temporary public-signature metric exception

- Status: accepted, bounded local quality decision; not release approval.
- Decision date: 2026-10-18.
- Expiry: 2026-11-17, with no implicit renewal.
- Authority: Adán, implementation controller, under the authorized local worktree plan and the existing independently reviewed exception mechanism. Alberto has not personally approved this exception; no such approval is claimed.

## Decision

Allow at most 29 parameters for exactly `core.py`, Python function `delegate_profile`, metric `python_ast_v1.parameter_count`. No other metric, symbol, file, safety check or release gate is waived. Keep the TOP floor, immutable baseline, thresholds, adapters and coverage unchanged.

## Reason and independent evidence

The approved `plans/worktree-integration-mvp.md` requires three explicit opt-in fields appended to the existing positional-compatible public API: `worktree`, `base_ref`, and `branch`. The existing interface has 26 parameters. Preserving it while adding those three names requires 29 at this boundary.

The candidate independently reviewed as `53db37d35b76660183cfab706e008782f7270451e77435d8adb9a9c9c8a3e8db` implements this function as a single adapter call. Its cyclomatic metric is 1, nesting is 0, and the normalized internal request does not propagate the flat 29-argument interface through the engine. Policy and state handling have separate existing owners. Independent Reviewer accepted these responsibility fixes and recommended this exact temporary exception in `.artifacts/worktree-mvp/fix-review/review.md`, section “Conflicto 29 parámetros / TOP”; measurable supporting evidence is in that directory's `identity-metrics.json` and `quality-summary.json`. Those private evidence files are local, not publication artifacts.

An options object or a new versioned API may be worthwhile in a future interface migration. Either changes the requested public contract or adds a second entry point and migration burden now. `**kwargs`, generated signatures, arbitrary grouping of old parameters, or another cosmetic extraction would hide the metric rather than reduce current responsibility. They are rejected for this fix.

## Conditions and remaining gates

Re-review before expiry, any public signature change, or growth of policy/state logic in the adapter. A parameter count above 29 is not allowed. The exception does not certify behavior and must not be extended to inherited vendor, bootstrap or test findings. Global TOP remains failed while those other blockers remain. Global lint, Python-support validation, real CLI/TUI and combined-work acceptance, and gateway activation are independent gates. No gateway restart, publication, push or unrelated debt repair is authorized by this decision.
