# Native goal integration boundary

## Decision

Keep independent plugin workers and Hermes-owned durable completion delivery. Do not enable automatic goal parking through an API that loses ownership, suppresses the wake when notifications are disabled, or lets agent teardown kill the detached worker. No Hermes patch, private active-delegation registry injection, process poller or replacement goal manager was added.

This leaves automatic `/goal` wait/continuation pending. Optimization and integration of the plugin proceed independently, as requested. A fully supported public dependency lifecycle in Hermes is the prerequisite for this remaining contract; a core extension is outside this plugin-only implementation authority.

## Concrete counterexample already measured

The existing disposable installed-runtime probe, `workspace/projects/profile-delegate-refactor/tui-block/probe_native_dependency.py`, exercises actual `process_registry.adopt_local`, `GoalManager.wait_on_session`, migration and agent release. Its `native-dependency-receipt.json` reports:

- Before compression: explicit barrier waits; old owner discovery counts one worker.
- After goal migration: explicit barrier survives, but new owner discovery counts zero and old owner still counts one.
- Silent worker completion: explicit `is_waiting()` recheck clears the barrier, but the gateway completion queue is empty. Rechecking is not automatic wake/continuation.
- Agent release: adopted worker has `persist_on_release=false`; lifecycle cleanup kills it with exit -15.

These are prior installed source/runtime evidence, not changed-candidate Discord or provider acceptance. Reusing this decisive counterexample avoids building another simulator. Public async dispatch also creates its own notification/finalizer and does not preserve the plugin's silent independent completion contract. Native PID parking can describe one process but does not supply the missing silent wake and multiple-child ownership lifecycle.

## Current integration

`native.py` owns the compatibility checks and native durable persistence seam. The worker persists terminal completion; the parent watcher only offers a coherent already-persisted pending event. Recovery is explicit. Internal Hermes ledger APIs remain a version-checked dependency; their use is not a public goal dependency API.

The selected architecture was compared with [Hermes Herald](https://github.com/bennybuoy/hermes-herald): its gateway/in-process subagent executors do not replace isolated named-profile execution with frozen authority and the current notification controls. Existing code and the installed Hermes runtime are the behavior authority. No HTTP gateway or second execution service was introduced.
