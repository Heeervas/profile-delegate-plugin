# Profile Delegate agent operating guide

Profile Delegate is a standalone Hermes user-plugin repository. Keep runtime implementation plugin-only: `/opt/hermes` is a dependency and inspection surface, never this project's write surface.

## Read first

1. `README.md` — product and operator contract.
2. `BRIEF.md` — scope, users, constraints, and acceptance criteria.
3. `STATE.md` — current release state, blockers, and next action.
4. `TODO.md` — prioritized deferred work.
5. `docs/plans/2026-07-22-plugin-only-reliability-reset-p0-p4.md` — accepted reliability direction.
6. `docs/README.md` — plan/audit/archive status and relocation navigation; `CONTRIBUTING.md` — contributor entry.
7. `decisions/` — durable architectural decisions.
8. `.agents/validation.md` and `.agents/skill-routing.md` — canonical validation and workflow routes.
9. `.hermes/` — Hermes-specific navigation and handoff context.

## Durable rules

- Keep execution status, task status, contract status, notification status, and transport status independent.
- Wrapper success requires trustworthy completed execution plus task status `ok`; format drift, ambiguity, malformed output, cancellation, timeout, or transport failure must never become false success.
- Profiles are context/state boundaries, not OS security sandboxes.
- Preserve private bounded run artifacts and strict origin authorization.
- No Hermes-core patches, plugin-owned durable message bus/outbox, compression-lineage router, or exactly-once/post-restart delivery claim.
- Prefer the standalone core plus thin Hermes wrapper shape; keep model-facing schemas under `parameters` and handlers JSON-safe.
- Preserve backward compatibility unless a versioned breaking change is explicitly approved.
- Update `STATE.md` after meaningful implementation or release work, `TODO.md` when priorities change, `CHANGELOG.md` for release-facing changes, and `.hermes/handoff.md` when work remains.
- Historical plans may remain only when clearly marked rejected or superseded.

## Scope and approval

Proceed autonomously for local code, tests, documentation, and reversible refactors within the accepted plan. Ask before destructive history changes, credentials, repository visibility changes, deployment, or other externally visible actions not already requested.

## Validation

Canonical commands live in `.agents/validation.md`. Before claiming completion, run the relevant focused tests and the complete release gate. Plugin discovery/registration must also be smoked after schema or wrapper changes.

## Git and release

- Commit only reviewed intentional files; never commit `.venv`, caches, run artifacts, or secrets.
- Use conventional commit messages.
- Every release must align `plugin.yaml`, `pyproject.toml`, README version and `CHANGELOG.md`, pass CI on the exact release commit, and receive an annotated `vX.Y.Z` tag.
- A gateway or fresh-session restart is required before loaded plugin code/schema changes are considered live.
- Do not tag, publish, or change repository visibility unless explicitly requested.

## Runtime adaptation

`.agents/` is the portable project contract. `.hermes/` is the minimal Hermes adapter and must point back to `.agents/` rather than duplicating policy. Add an `outputs/` surface only if the plugin later produces repository-worthy durable reports; runtime run artifacts never belong there.
