# Profile Delegate plugin-only reliability reset — P0 to P4

**Status:** P0/P1 implemented and release-gated; P2–P4 deferred to `TODO.md`. Supersedes durable/outbox/lineage proposals for this remediation.

**Decision:** simplify. No Hermes-core changes. Do not build a durable message bus, compression-lineage router, manifest protocol, or gateway injection API inside this remediation.

## Product model

Profile Delegate has three independent outcomes:

1. **Execution:** did the child process/session finish?
2. **Task result:** did the child report `ok`, `blocked`, `failed`, or leave the outcome `unknown`?
3. **Contract quality:** was the result valid structured JSON, recoverable JSON, or useful prose/Markdown?

Contract drift must never rewrite a completed execution into a failed execution. Notification delivery is also separate from execution and result quality.

## Evidence behind the reset

- 700 historical run artifacts inspected since June 2026.
- 54 runs were marked `unstructured_output`; 41 detached runs recorded `detached_worker_completed_no_live_queue`.
- Useful outputs were routinely preserved despite those labels.
- Recent `contract_invalid` examples were valid JSON objects with custom fields requested by the caller. They failed only because the partial new validator required the five default-envelope fields.
- One caller explicitly requested “full Markdown plan only”; treating that as a JSON failure is the plugin contradicting its own caller.
- `BLOCKED_NEEDS_FIXES` Markdown was useful and semantically blocked, not corrupted.
- Notification loss clusters around detached execution and gateway/process restarts. The worker result remains on disk.
- Memory/OOM issues have now been addressed separately; do not redesign the plugin around that incident unless failures persist afterward.

# P0 — Restore reliable result handling

**Goal:** a completed useful delegate result is returned as useful output, even when formatting drifts.

1. Revert the unfinished strict V1-delimiter-only parser and delete the unintegrated outbox prototype from the dirty tree.
2. Keep tolerant parsing, but make candidate selection deterministic:
   - whole-output JSON wins;
   - otherwise collect top-level JSON objects and JSON-fence objects with exact source spans;
   - a valid explicit `status` plus `summary` is a terminal envelope; default-envelope arrays strengthen confidence but named profile-specific fields never do;
   - one terminal envelope wins; multiple equally valid terminal envelopes return `ambiguous_json_candidates`; nested objects never compete with their containing top-level object;
   - preserve extra/custom keys on the selected object.
3. Make normalization tolerant again:
   - any parsed JSON object is `structured=true`;
   - missing `status` becomes task status `unknown`; process completion proves execution only, not task success;
   - invalid explicit status becomes `failed` with `invalid_status`;
   - arrays are coerced as before;
   - custom output-contract fields are preserved.
4. Keep a conservative prose/Markdown fallback:
   - leading `BLOCKED*` → task status `blocked`;
   - leading `FAILED*` → task status `failed`;
   - leading `OK*` → task status `ok`;
   - otherwise useful non-empty prose → task status `unknown`, `structured=false`, `contract_status=drifted`;
   - empty output → `failed/parse_failed`.
5. Wrapper success is true only for execution completed + explicit/recovered task result `ok`. `blocked`, `failed`, and `unknown` all produce wrapper `success=false`; a valid `blocked` or useful `unknown` result may still have run lifecycle `completed`.
6. Add explicit orthogonal fields:
   - `execution_status` from run lifecycle;
   - `status=ok|blocked|failed|unknown` for task result;
   - `contract_status=valid|recovered|drifted|empty`;
   - `structured=true|false`;
   - `raw_output_path` whenever non-canonical output was used.
7. Fix the four current failing tests and run the full suite.

8. Record candidate count, selected source span and parse method for structured recovery; ambiguity is visible, never silently guessed.

**Acceptance:** JSON with caller-specific keys no longer becomes `contract_invalid`; explicit Markdown requests work; useful prose survives as `unknown`; blocked/unknown are not success; empty output still fails.

# P1 — Stop bad contracts at dispatch

**Goal:** callers cannot accidentally give the child mutually contradictory formatting instructions.

1. Add a lightweight `output_mode`:
   - `auto` compatibility default when omitted;
   - `json` default;
   - `markdown`;
   - `text`.
2. Keep `output_contract` for content/schema guidance. Explicit `json|markdown|text` is authoritative; `auto` resolves legacy intent conservatively and persists both `requested_output_mode` and `resolved_output_mode`.
3. Prompt rules:
   - JSON mode asks for one object and shows the default envelope as a recommendation, not an exact closed schema.
   - Markdown/text mode does not demand JSON.
   - Caller contract is inserted as data; one final mode reminder appears after it.
4. Detect obvious contradictions before launch only for an explicitly selected mode:
   - JSON mode + “Markdown only”;
   - Markdown mode + “JSON only”.
   Return `contract_conflict` with a corrective example instead of wasting a run. In `auto`, narrowly infer legacy Markdown/text intent from exact phrases such as “Markdown only”, “full Markdown”, “plain text”, or “one exact line”; otherwise resolve to JSON.
5. Expose short literal examples in the tool schema.
6. Preserve backward compatibility: omitted mode is `auto`, old custom JSON keys remain accepted, and the historical “full Markdown plan only” contract launches successfully in Markdown mode.

**Acceptance:** the plugin never simultaneously orders JSON and Markdown; explicit contradictions fail before child execution; omitted legacy contracts continue to work.

# P2 — Make notification semantics honest and robust enough

**Goal:** no completed work is described as lost or failed because a best-effort notification missed its window.

Hard boundary: plugin-only; no Hermes patch.

1. Keep run artifacts/status as the durable source of truth.
2. Notification failure never changes execution/task status.
3. Project legacy and new states through this honest state model:
   - `best_effort_queued`;
   - `best_effort_unavailable_parent_gone`;
   - `disabled`;
   - `failed`.
4. Define producer ownership and transitions:
   - dispatcher initializes `disabled` or `pending_best_effort`;
   - detached worker commits task artifacts only;
   - live parent watcher alone moves `pending_best_effort → best_effort_queued|failed` using locked merge/readback;
   - detached worker may record `best_effort_unavailable_parent_gone` only when parent PID **and process-start identity** no longer match;
   - missing origin key becomes `failed_unroutable`, never queued;
   - legacy `queued` and `detached_worker_completed_no_live_queue` are projected as aliases without rewriting old files;
   - queue acceptance is explicitly not platform delivery.
5. Improve the current parent watcher without inventing a message bus:
   - persist completion first;
   - watcher reads back result/status before queueing;
   - bounded retry while the parent/gateway process is alive;
   - no claim of delivery, only queue acceptance.
6. On `best_effort_unavailable_parent_gone`, status output must lead with: “work completed; notification unavailable; result preserved at …”.
7. Do **not** add a delayed next-turn reminder in this remediation: lane keys survive `/new`, while exact logical-session delivery cannot be guaranteed plugin-only.
8. Document that guaranteed zero-turn delivery across gateway restart is unsupported in plugin-only scope.

**Acceptance:** missed notifications are visible but never masquerade as lost execution; polling always recovers the result; no cross-session routing code.

# P3 — Reduce failure surface in background execution

**Goal:** preserve the useful TUI controls without making every ordinary delegation depend on the heaviest path.

1. Measure failure rate by transport after P0/P1, now that OOM is fixed.
2. Add `transport_mode=auto|simple|interactive` and persist it in request/status/fingerprint:
   - compatibility default `auto`: synchronous calls use `simple`; existing background calls remain `interactive` for this release unless the caller explicitly selects otherwise;
   - `simple`: CLI child, allowed for sync/background/resume; status/cancel may terminate the owned worker process, but steer returns `control_unavailable_simple_transport` without mutation;
   - `interactive`: TUI stdio, allowed for background new/resume and required for steer/native interrupt/live events;
   - invalid combinations fail before artifact creation with `transport_conflict`.
3. Keep two execution paths:
   - `simple`: CLI child, fewer moving pieces, default for ordinary bounded delegation;
   - `interactive`: TUI stdio, only when steer/cancel/live event visibility is requested.
4. After one compatibility release, do not silently select TUI merely because `background=true`; change `auto` background to `simple` only if measured smokes and real-run evidence support it.
5. Keep detached workers for long-running work, but add one explicit locked `reconcile_run(task_id)` core operation used by dispatch capacity/duplicate checks and an operator reconciliation command—not ordinary status/list reads:
   - dead worker + no terminal result → `failed/worker_died`;
   - terminal result exists → project terminal truth;
   - validate worker PID plus process-start identity to avoid PID reuse;
   - if a valid terminal `result.json` exists while status is stale, result authority determines the terminal projection under the run lock;
   - dead worker + no valid terminal result → `failed/worker_died`;
   - ordinary status/list remain read-only and show a derived `stale` warning;
   - duplicate guard, capacity and prune consume reconciled truth only through the explicit operation.
6. Remove or quarantine stale duplicate/concurrency records so dead workers do not block new work.
7. Test process death, timeout, resume, simple-process cancellation, interactive native cancellation, interactive steer refusal/acceptance, and result preservation.

**Acceptance:** ordinary delegation uses the simpler path; interactive complexity is opt-in; stale runs stop poisoning capacity and operator trust.

# P4 — Cleanup, observability, and release discipline

**Goal:** keep reliability understandable instead of accreting another subsystem.

1. Bump artifact schema and add read-only compatibility projectors for legacy request/status/result files. New fields are additive; old artifacts are classified without rewriting them. Align public lifecycle filters with every core lifecycle value, including cancelled and timed out.
2. Add a compact local run-health command/report:
   - totals by execution status;
   - task status;
   - contract status;
   - notification status;
   - transport.
3. Add regression fixtures from real runs:
   - custom valid JSON without the default arrays;
   - warning-prefixed JSON;
   - fenced JSON;
   - Markdown-only requested output;
   - `BLOCKED_NEEDS_FIXES`;
   - useful plain text;
   - empty output;
   - detached completion with dead parent.
   - ambiguous progress/final JSON candidates;
   - TUI `gateway.ready` startup timeout before any event.
4. Remove dead parser helpers, abandoned outbox files and superseded durable-delivery plan from release scope. Historical plans may remain archived, clearly marked rejected.
5. Update README/schema/error codes to match actual behavior.
6. Record the exact baseline before implementation: `PYTHONPATH=/opt/hermes .venv/bin/python -m pytest -q -o 'addopts='` currently gives `235 passed, 4 failed`; enumerate those four fixture/security failures before changing them.
7. Run:
   - focused parser/normalizer tests;
   - full plugin suite;
   - Ruff and compile;
   - one simple sync smoke;
   - one simple detached background smoke;
   - one interactive steer/cancel smoke;
   - Reviewer focused on regression and scope control.
   - paired CLI/TUI normalization parity assertions;
   - wrapper success assertions for every task state;
   - omitted/explicit output-mode tests;
   - transport-mode persistence/fingerprint/conflict tests;
   - explicit reconciliation/dead-worker/prune tests.
8. Observe real runs for several days before considering stronger delivery machinery.

**Acceptance:** docs and status labels match reality; real-run fixtures prevent recurrence; no unproved distributed-system machinery remains.

## Explicitly rejected for this remediation

- Hermes-core patches.
- Plugin-owned durable cross-process notification bus.
- Compression-lineage routing.
- Completion manifests and transactional multi-file commit protocols.
- Exactly-once or guaranteed post-restart notification delivery.
- Closed-schema validation that rejects useful custom JSON.

These may be reconsidered only with fresh evidence after P0–P3, not because they are architecturally entertaining.

## Recommended implementation order

1. **P0 immediately** — this addresses the observed user pain and removes current dirty regressions.
2. **P1 next** — prevents contradictory contracts at source.
3. **P2 narrowly** — honest best-effort notification, optional safe next-turn reminder only.
4. **P3 after measurement** — choose simple vs interactive defaults from evidence.
5. **P4 release and observe** — only then decide whether anything stronger is justified.
