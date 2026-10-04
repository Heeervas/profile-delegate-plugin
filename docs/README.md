# Documentation map

Current truth: [STATE](../STATE.md). Unresolved work: [TODO](../TODO.md).
Contributor entry: [CONTRIBUTING](../CONTRIBUTING.md) and [opportunities](contribution-opportunities.md).
Commands are owned by [.agents/validation.md](../.agents/validation.md), not historical plan snippets.

## Canonical surfaces

- `plans/`: retained design/implementation plans, including the native approval package and its co-located evidence. No generic template migration is needed.
- `audits/`: dated audit findings and independent review receipts. `independent-current/` is a historical package name, **not** a current-state authority; its intermediate CI/runtime blockers are superseded where STATE records newer evidence.
- `reviews/`: scoped review/evidence receipts, including managed-scope and housekeeping.
- `archive/`: verbatim older STATE/handoff bodies. Paths, counts, permissions and acceptance statements there refer to their original repository/date; do not execute them as current commands.
- `../decisions/`: accepted architectural boundaries.

## Plan status

The [plugin-only reliability reset](plans/2026-07-22-plugin-only-reliability-reset-p0-p4.md) supplies the durable direction, interpreted through [decision 0001](../decisions/0001-plugin-only-reliability-boundary.md). P0/P1 and native-ledger notification work have implementation; remaining work is reconciled in TODO rather than obsolete checkboxes.

[Later reliability/steer-first design](plans/2026-09-27-reliability-and-steer-first-implementation.md), [compression continuity](plans/2026-09-30-compression-session-continuity.md), and [native approval package](plans/2026-10-01-native-approval-modes/PLAN.md) preserve design and bounded acceptance history. They do not independently grant new implementation/activation authority.

[Native simplification](plans/2026-10-03-native-simplification.md), its [validation](plans/2026-10-03-validation.md), [test-retirement map](plans/2026-10-03-test-retirement.md), [goal boundary](plans/2026-10-03-native-goal-boundary.md) and [finish plan](plans/2026-10-04-finish-simplification-and-reduce-tests.md) are historical refactor provenance, not a current numerical test-reduction mandate.

The [duplicate-call plan](plans/duplicate-call-prevention.md) moved from root PLAN.md; [Herald comparison](plans/2026-09-09-herald-comparison-and-roadmap.md) moved from root plans/; [spectator plan](plans/2026-07-21_090037-profile-delegate-spectator-tui.md) moved from .hermes/plans/. Their content remains recoverable. Older rejected outbox/durable-delivery proposals retain their rejection banners; source/reference names in old receipts describe historical revisions.

Current test names map to `tests/<original basename>`; runtime modules remain at root. Historical `event_schema.py` references are not current compilation targets (shared constants now live in `contracts.py`). See the housekeeping receipt for relocation verification.
