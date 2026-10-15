# Hermes handoff

Current candidate, review, gates, publication authority and blocker: [STATE.md](../STATE.md).
Contract and limits: [multi-dispatch](../docs/multidelegate.md).
Canonical checks: [.agents/validation.md](../.agents/validation.md).

v1.11.0 additive implementation is isolated atop public v1.10.1. Focal independent code review closed F1/F2 without a new code blocker; documentary F3 is reconciled. Full candidate suite 743 passes, portable 234 passes; native detached/batch fresh-process probe 31 passes. No activation claim.

Existing authorized gh authentication is available with `XDG_CONFIG_HOME=/opt/data/.config`; use its Git credential helper per command, without persistent config or credential changes. Normal main push succeeded. Verify exact-head CI before creating and reading back a new annotated v1.11.0 if unused. Never force push/move tags; no GitHub Release, gateway restart or external announcement is authorized.

Immutable-baseline quality relocation limitation and exact-public-base supplemental pass are explicitly retained in STATE. Do not claim the raw immutable-baseline collector passed. Do not merge the original dirty checkout or attribute its live-provider smoke to this candidate. Historical handoffs remain provenance only.
