# Code landmarks

- `plugin.yaml` — plugin identity and provided tool names.
- `__init__.py` — model-facing schemas, handlers, registration, preview integration.
- `core.py` — policy, validation, run artifacts, CLI transport, parsing/normalization, lifecycle, async worker, status/list/prune.
- `tui_runner.py` / `tui_rpc.py` — persistent TUI Gateway transport and authoritative execution lifecycle.
- `spectator.py` / `event_journal.py` / `event_schema.py` — bounded read-only event stream and spectator projection.
- `child_bootstrap.py` — child approval/capability posture before agent construction.
- `cli.py` — terminal spectator/inspection command surface.
- `test_profile_delegate.py` — broad core and wrapper behavior.
- `test_reliability_reset.py` — output/result false-success regressions and sanitized fixtures.
- `test_tui_rpc.py` — TUI transport and lifecycle regressions.
- `tests/fixtures/profile_delegate/` — immutable sanitized historical outputs.
- `README.md` — operator contract and installation.
- `docs/plans/2026-07-22-plugin-only-reliability-reset-p0-p4.md` — accepted reliability direction.
- `decisions/0001-plugin-only-reliability-boundary.md` — durable rejected-alternative record.

Runtime artifacts are outside the repository under the configured Profile Delegate runs root.