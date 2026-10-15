# Multi-dispatch contract

`profile_multidelegate(tasks: [...], preflight: false)` is an additive facade over the singular execution engine. Each item requires `profile`, `task`, `session_title` and accepts the singular override fields except `background`, `notify_on_complete`, `transport_mode`, `preflight`, `session_mode`, and `session_id`. It forces new interactive background sessions and native per-run notifications. Resume remains on `profile_delegate`.

Root/items reject unknown fields and wrong types. Full validation of every item precedes run creation. A trusted routable origin and compatible native ledger are prerequisites. The array limit is min(max_concurrent,max_async), not a reservation or RAM guarantee. Sequential local launches allow child execution to overlap; no scheduler, queue, hidden waves or durable batch ledger exists.

## Receipts and recovery

- `validated`: preflight only, zero runs and no capacity reservation.
- `accepted`: all indices started/reused; not execution or task success.
- `partial`: some started/reused and some failed/not_started.
- `rejected`: no accepted dispatch or global validation failure; a failed created run may still have a handle.

Receipts preserve input order, index, profile, dispatch status, run_created/deduplicated and task_id/paths/watch hints when available. Initial-write and launch failures retain created-run handles even when terminal publication fails. Invalid items are failed and valid siblings not_started on global validation rejection. An observed dispatch failure stops later indices without cancelling siblings. Later worker rejection, including slot contention, remains an individual result.

Duplicate identical active requests can reuse a run within the existing window; indices can share task_id and do not generate extra notifications. `duplicate_policy=new` intentionally creates independent runs but bypasses no policy. Fingerprints remain singular, so interactive need not match auto. A retry after completion or expiry can repeat work. After a lost reply consult list/status before retrying side effects. Parent interruption can lose index correlation while children remain alive.

Existing status/steer/cancel work individually by task_id and exact origin. Notifications are native, per unique run, best effort; no aggregate-return, exactly-once or guaranteed post-restart claim. Profiles are context boundaries, not OS sandboxes. Review preset excludes both delegating tools.

## Work ownership

Same-profile requests are supported. The orchestrator prepares worktrees, assigns write ownership and integrates changes. Two Builders can edit the same relative filenames in separate worktrees with per-item workdir. Different directories do not isolate shared ports, services or databases. Read-only shared directories are valid; this tool is not a DAG executor.

## Evidence boundaries

Local tests cover batch validation, actual singular admission/artifacts with controlled launch faults, effective bootstrap schema filtering, per-item overrides/workdirs, dedupe and late rejection. These do not establish heavy-load capacity or worktree isolation. A controller-observed live invocation produced two distinct same-profile sessions, overlapping execution, completed/ok markers and both return notifications on the installed dirty runtime; that observation does not prove every byte of this clean release candidate or individual control uptake. Existing control regressions remain mandatory. Release CI must be checked on the exact published commit; no gateway restart is performed by release packaging.
