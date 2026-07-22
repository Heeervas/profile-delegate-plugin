# Skill routing

Reviewed: 2026-07-22

Select one execution-primary skill and at most two supporting skills unless a concrete need justifies more.

## Routes

### Plugin implementation or schema changes

- Primary: `hermes-plugin-tool-authoring`
- Supporting: `test-driven-development`
- Validator: `requesting-code-review`

Use for model-callable tool schemas, handlers, plugin discovery, child-process behavior, artifact security, or public release hardening.

### Hermes runtime compatibility or configuration

- Primary: `hermes-agent`
- Supporting: `alberto-hermes-docs`

Read local `/opt/hermes` docs/code before public docs. Runtime inspection does not authorize Hermes-core writes.

### Bug investigation

- Primary: `systematic-debugging`
- Supporting: `test-driven-development`

Reproduce the failure, add a stable regression when practical, and keep fixes plugin-local.

### Non-trivial planning

- Primary: `writing-plans`
- Supporting: `hermes-plugin-tool-authoring`

Plans belong under `docs/plans/` in this existing repository. Do not move historical plans merely to mimic a generic template.

### Release and push

- Primary: `github-pr-workflow`
- Supporting: `hermes-plugin-tool-authoring` public-release hardening reference
- Validator: `requesting-code-review`

Verify the exact commit SHA and CI before announcing a release.

## Exclusions

- Do not use Codex CLI or OpenCode unless Alberto explicitly requests them.
- Do not route plugin work into Hermes-core contribution workflows unless a plugin-only path is proven impossible and explicitly approved.
- Do not revive durable outbox or compression-lineage designs rejected by the accepted plan.
- Do not install or claim unavailable skills silently; use the nearest verified local workflow and record the fallback.

## Refresh trigger

Refresh when plugin architecture, validation commands, release process, or installed skill names materially change.