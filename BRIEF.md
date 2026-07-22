# Profile Delegate brief

## Purpose

Provide bounded, model-callable delegation between Hermes profiles without the ceremony and persistence overhead of Kanban or another gateway.

## Users

- Hermes operators who maintain multiple profiles with distinct context, memory, policy, and domain expertise.
- Parent agents that need a focused builder, reviewer, research, or domain-profile result.
- Operators who need durable local inspection, steering, cancellation, and recovery evidence for delegated runs.

## Core outcomes

1. A caller can start or resume a target-profile session with explicit scope and authority.
2. Delegated execution remains bounded, inspectable, and origin-authorized.
3. Execution, task, contract, notification, and transport outcomes remain distinct and honest.
4. Useful prose/Markdown or custom JSON is preserved without claiming false success.
5. Background work remains recoverable through durable run artifacts even when best-effort notification is unavailable.

## In scope

- Sync and background delegation.
- New and explicit resume sessions with short titles.
- Per-call execution overrides subject to effective policy.
- Deterministic result parsing and conservative recovery.
- TUI spectator, steering, cancellation, status/list/policy/prune surfaces.
- Private bounded local artifacts, duplicate protection, concurrency limits, and lifecycle-safe inspection.

## Out of scope

- OS-level sandboxing between profiles.
- Parent approval brokering.
- Hermes-core modifications for plugin behavior.
- A plugin-owned durable message bus/outbox.
- Compression-lineage routing.
- Exactly-once or guaranteed post-restart notification delivery.
- Binding authority beyond the parent caller's authorization.

## Critical constraints

- Fail closed on malformed, ambiguous, contradictory, unauthorized, or unverifiable success claims.
- Never expose raw delegated prompt content through process argv.
- Keep run directories/files private and payloads bounded.
- Maintain backward compatibility for historical artifacts and caller contracts where practical.
- Runtime state belongs under the configured Hermes home/run root, never inside the repository.

## Acceptance criteria

- Model-facing schemas register through Hermes plugin discovery and use OpenAI-format `parameters`.
- `blocked`, `failed`, `unknown`, timeout, cancellation, transport failure, and contract drift cannot return wrapper success.
- Sync and TUI paths apply the same result semantics.
- Full tests, Ruff, Python compilation, diff check, secret scan, and registration/handler smokes pass.
- README, manifest, changelog, state, and release version agree.
- Repository contains no private run artifacts, credentials, caches, or machine-specific sensitive data.

## Current accepted direction

P0/P1 reliability remediation is complete. P2–P4 remain deferred in `TODO.md`; P3 transport changes require real post-fix evidence before implementation.
