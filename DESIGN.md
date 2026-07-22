# Profile Delegate design contract

**Applicability:** no end-user visual interface. This plugin exposes model-callable tools and terminal spectator output; a decorative UI design system would be cargo cult.

## Interaction principles

- Tool schemas must be concise, explicit, provider-compatible, and corrective on invalid calls.
- Status output leads with execution truth and result location; notification state must not masquerade as execution failure.
- Terminal spectator output must remain bounded, readable, safe to detach, and free of raw reasoning, secrets, prompt bodies, or control payloads.
- Error codes are stable machine-facing contracts; summaries are concise operator-facing explanations.
- New controls must fail before run allocation when combinations are contradictory or unauthorized.

## Compatibility

- Preserve established tool names and additive schemas by default.
- Keep JSON outputs stable and bounded; retain custom caller-requested fields when safe.
- Treat `README.md` examples and `.agents/validation.md` as release surfaces.

## Accessibility and responsive behavior

Not applicable beyond normal terminal readability: avoid color-only meaning, preserve plain-text labels, and keep output useful without ANSI support.
