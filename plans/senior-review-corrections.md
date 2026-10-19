# Senior-review corrective implementation

## Authority and candidate

**Later authority (2026-10-19):** Alberto requested committing and pushing the
complete verified candidate, including reviewed inherited changes, to send to a
reviewer. This supersedes earlier no-commit/no-push and corrective-only packaging
constraints below. Preserve divergent remote main; use a review branch, no force
push/rebase, release, merge, gateway restart or external configuration mutation.

Alberto authorized all seven findings locally in the Builder Discord thread, with Builder responsible for checks before the final independent Reviewer. No push, publication, deployment, gateway restart or external configuration changes are authorized. Preserve inherited dirty/untracked work at intake HEAD `60f93e200b328bcf82bf34e809c2945d7323b084`.

Immutable intake bytes and ownership manifest: `.artifacts/senior-corrections/intake.tar.gz`, `intake-manifest.json`. Existing baseline `e46c84910ea00e0f4b8795cd2bfcc35378ce1cee`, TOP policy and exception remain unchanged. Intake executable policy validation and quality measurement passed before implementation. Do not sweep inherited changes into a corrective commit.

## Outcome and acceptance

Acceptance owner: Alberto; Builder owns implementation/integration checks; Reviewer owns final independent assessment only after those checks.

1. Generic resume authorizes originating session before reusing approval/workspace evidence. Reject foreign origins including frozen yolo; preserve same-origin and proven compression continuity.
2. Concurrency permits cover actual native execution through bounded teardown/reaping, including cancellation/errors. Publication does not consume execution capacity.
3. Shutdown drains both pipes without unbounded capture; large output does not cause artificial termination; continuous output and stubborn processes obey fixed deadlines and are reaped.
4. Worktree request identity and preparation consume one resolved commit SHA. Unchanged SHA reuses; moved ref does not silently reuse old work.
5. Singular boolean inputs are validated, not truthiness-coerced. Malformed input refuses before allocation; valid booleans and native canonical coercion remain compatible.
6. Prose terminal verdicts inside backtick or tilde fences cannot claim success; matching fence closure permits real final verdict. Preserve existing ambiguity/contradiction and legacy protections.
7. Journal append recovery is incremental across cooperative writers with measured approximately linear read/parse work; retain locks, partial-tail repair, corruption detection, byte/event caps and terminal reserve.

Commands and executable acceptance procedures belong only in `.agents/validation.md`. Each correction receives focused red/green behavioral evidence where feasible, followed by integrated full/release, partitions, static/registration/security and unchanged TOP quality gates. Real harmless transport smokes cover affected boundaries without changing profiles or restarting the gateway. Explicitly disclose any native-provider or activation gap.

## Ownership and sequence

- Admission worker: admission/worktrees/wrapper and related worktree/batch tests only.
- Lifecycle worker: TUI runner/RPC and their tests only.
- Journal worker: journal and journal tests only.
- Builder: contracts/prose tests, canonical docs, integration verification, ownership diff, lessons and final reviewer packet. Core changes are serialized through Builder if needed.

No worktree is currently created: shared disjoint paths avoid copying broad dirty state and disk use. Existing unrelated worktrees are not cleanup targets. If a task worktree becomes necessary, inventory and remove only that owned worktree after preserving deliverables.

After verified corrections, extract general behavior/validation rules into profile-local Builder skill surfaces, not shared symlink targets or a second global ruleset. Record deterministic checks only where an invariant can actually be observed; avoid pretend universal lint rules for semantic properties.
