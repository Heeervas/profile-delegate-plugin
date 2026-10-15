# Profile Delegate — v1.11.0 candidate

## Authority and publication

Authorized: additive `profile_multidelegate`, bounded prompt/recovery improvements, normal push to main and new annotated v1.11.0 tag after exact-commit CI. No force push, tag movement, GitHub Release, gateway restart or runtime activation.

Publication baseline: `0315b839217861124e591d728f279e6545e6a2a1` (public v1.10.1). Candidate is isolated from the original dirty checkout. The initial push failed because Git had no credential helper in this session. Existing authentication was subsequently verified using `XDG_CONFIG_HOME=/opt/data/.config`: account `eve-ai-dev` has push permission on the exact repository. Publication uses the existing gh credential helper per command only; no credentials or persistent configuration changed. Exact-head CI and remote tag readback are required before reporting publication.

## Implementation and review

The new facade validates the entire array before dispatch and preserves ordered per-index receipts. Individual execution, task, contract, transport and notification outcomes remain independent. Existing singular admission, dedupe and controls are reused. See [contract](docs/multidelegate.md).

Independent focal review `pd_20261015_135628_r5owb6`: PASS_WITH_NOTES for code; F1/F2 CLOSED_STATIC, no new code blocker. F3 requested state/handoff/link reconciliation, now supplied. Reviewer did not execute tests or certify live-provider behavior. No code changed after this review.

Port identity: owned deltas from the captured incoming snapshot reverse-apply cleanly for entrypoint/core/test/fixtures; new batch and regression modules are byte-identical to the implementation checkout. Private receipt `.artifacts/port-identity.json` includes hashes. Published baseline provides the tests/ layout. No bulk transfer of reasoning, UTF-8, TUI fixes or private quality tooling.

## Validation

Canonical commands: [.agents/validation.md](.agents/validation.md).

- Full installed suite: **743 passed**, warnings-as-errors, 126.77 s.
- Portable suite: **234 passed, 509 deselected**, 7.61 s.
- Fresh candidate batch + detached fixture probe: **31 passed**, 11.36 s; includes actual native subprocess fixture execution, not a real-provider multi-child claim.
- Global Ruff, compilation, frozen lock/sync, secret scan (zero hits), diff checks pass.
- Fresh-process registration/handler smoke: version 1.11.0, seven tools, success.
- Immutable-baseline quality at STANDARD and diagnostic TOP still reports QUALITY_FAIL from prior test relocation classified as additions. No thresholds, exceptions or immutable baseline changed. Supplement against exact publication base 0315b83 reports **QUALITY_PASS_WITH_EXCEPTION**, no new/worsened strong finding. This isolates this release's delta, not a claim that the raw immutable-baseline report passes. Existing housekeeping disposition remains in [receipt](docs/reviews/2026-10-04-housekeeping.md).

Native runtime equality with CI pin is not established locally; exact-head GitHub CI remains mandatory before tag creation. Controller-observed two real overlapping child completions/notifications occurred on the dirty runtime, not this clean candidate. Gateway activation, real-provider worktree isolation and individual live control uptake are not claimed.

## Remaining work and limits

Normal main push succeeded using the existing authorized per-command helper. Release completion requires exact-head CI and remote annotated-tag verification; the final operator receipt supplies those immutable URLs/SHAs. Do not infer activation from publication.

Profiles are context boundaries, not security sandboxes. Native notifications are best effort, not exactly-once or restart durable. Multi-dispatch is not a scheduler, transaction, DAG executor or worktree manager. Existing backlog remains: contradictory JSON statuses with unequal candidate scores; RPC write/flush deadline accounting; per-chunk UTF-8 decoding. See [TODO](TODO.md).
