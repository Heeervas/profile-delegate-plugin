"""Argparse registration and exit-code dispatch for the Profile Delegate spectator."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import NoReturn

try:
    from .spectator import SpectatorError, inspect_run, resolve_spectator_run, watch_run
except ImportError:  # direct plugin import / pytest
    from spectator import SpectatorError, inspect_run, resolve_spectator_run, watch_run

ROOT_DESCRIPTION = """Local, read-only spectator for Profile Delegate runs.

This command reads bounded sanitized run artifacts. It never attaches to or
controls the delegated child, and q or Ctrl+C only detaches the spectator.
Default privacy: no assistant text is persisted.

Task IDs look like pd_20260721_085059_dzk2o9. Run roots resolve in this order:
--runs-root, PROFILE_DELEGATE_RUNS_ROOT, --hermes-home, active HERMES_HOME.
The command never scans other profile homes.

Examples:
  hermes profile-delegate watch pd_20260721_085059_dzk2o9
  hermes -p work profile-delegate watch pd_20260721_085059_dzk2o9
  hermes profile-delegate watch pd_20260721_085059_dzk2o9 --jsonl
  hermes profile-delegate inspect pd_20260721_085059_dzk2o9 --json

Agents: use inspect --json for bounded machine-readable state and watch --jsonl
for streaming sanitized records.

Exit codes 0..4: 0 completed/detached; 1 failed/cancelled/timed out;
2 invalid/not found; 3 unauthorized/unsafe path; 4 corrupt/degraded artifacts.
"""

WATCH_DESCRIPTION = """Follow one run without attaching to or controlling it.

The default is an ANSI display on a TTY and stable incremental lines otherwise.
--jsonl emits sanitized journal records. q/Ctrl+C detach without affecting the
worker. Terminal status determines exit code 0 or 1; artifact errors use 2..4.
"""

INSPECT_DESCRIPTION = """Print one bounded snapshot and exit.

Reads status.json, events.jsonl, and result.json only. Legacy runs without an
event journal are labeled limited observability. --json is the stable
machine-readable output mode. Exit codes 2..4 report path/artifact errors.
"""


def _add_location_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--runs-root", default="", metavar="PATH",
        help="Exact runs root (highest precedence; no profile-home scan).",
    )
    parser.add_argument(
        "--hermes-home", default="", metavar="PATH",
        help="Caller's Hermes home; used only when --runs-root and PROFILE_DELEGATE_RUNS_ROOT are unset.",
    )


def register_cli(parser: argparse.ArgumentParser) -> None:
    """Build the ``hermes profile-delegate`` command tree."""
    parser.description = ROOT_DESCRIPTION
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    subs = parser.add_subparsers(dest="profile_delegate_command", metavar="{watch,inspect}")

    watch = subs.add_parser(
        "watch", help="Follow sanitized progress until terminal status or detach.",
        description=WATCH_DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    watch.add_argument("task_id", help="Task ID returned by profile_delegate (pd_YYYYMMDD_HHMMSS_suffix).")
    _add_location_options(watch)
    watch.add_argument("--jsonl", action="store_true", help="Stream sanitized events as newline-delimited JSON; no ANSI.")
    watch.add_argument(
        "--poll-interval", type=float, default=0.2, metavar="SECONDS",
        help="Artifact poll interval, clamped to 0.05..5.0 seconds (default: 0.2).",
    )

    inspect = subs.add_parser(
        "inspect", help="Print one bounded run snapshot and exit.",
        description=INSPECT_DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    inspect.add_argument("task_id", help="Task ID returned by profile_delegate (pd_YYYYMMDD_HHMMSS_suffix).")
    _add_location_options(inspect)
    inspect.add_argument("--json", action="store_true", help="Print bounded machine-readable JSON (recommended for agents).")

    for name in ("operator-status", "operator-list", "operator-reconcile"):
        op = subs.add_parser(name, help="Same-UID local operator recovery (not a model tool).")
        if name != "operator-list":
            op.add_argument("task_id")
        op.add_argument("--runs-root", required=True, help="Explicit local runs root; no implicit scan.")


def profile_delegate_cli(args: argparse.Namespace) -> NoReturn:
    """Dispatch a leaf command and always raise SystemExit with its code."""
    try:
        command = getattr(args, "profile_delegate_command", None)
        if command not in {"watch", "inspect", "operator-status", "operator-list", "operator-reconcile"}:
            print("error: choose watch or inspect; run 'hermes profile-delegate --help'", file=sys.stderr)
            raise SystemExit(2)
        if command.startswith("operator-"):
            try:
                from . import core
            except ImportError:
                import core
            raw_root = Path(args.runs_root).expanduser()
            if raw_root.is_symlink():
                raise SpectatorError("operator root must not be a symlink", 3)
            root = raw_root.resolve(strict=True)
            info = root.stat()
            if not root.is_dir() or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise SpectatorError("operator root must be owned by current UID and private", 3)
            os.environ["PROFILE_DELEGATE_RUNS_ROOT"] = str(root)
            if command == "operator-list":
                result = core._read_run_list(scope="all", operator=True)
            elif command == "operator-reconcile":
                resolve_spectator_run(args.task_id, runs_root=str(root))
                result = core._operator_reconcile(args.task_id)
            else:
                resolve_spectator_run(args.task_id, runs_root=str(root))
                result = core._read_run_status(args.task_id, operator=True)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(0)
        run_dir = resolve_spectator_run(
            args.task_id,
            runs_root=getattr(args, "runs_root", ""),
            hermes_home=getattr(args, "hermes_home", ""),
        )
        if command == "inspect":
            snapshot = inspect_run(run_dir)
            # JSON is intentionally also the default: inspect is a bounded snapshot surface.
            print(json.dumps(snapshot, ensure_ascii=False, indent=2))
            raise SystemExit(1 if snapshot.get("status") in {"failed", "cancelled", "timed_out"} else 0)
        code = watch_run(
            run_dir,
            output_mode="jsonl" if getattr(args, "jsonl", False) else "auto",
            poll_interval=getattr(args, "poll_interval", 0.2),
        )
        raise SystemExit(code)
    except SpectatorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(exc.exit_code) from None
    except (OSError, ValueError) as exc:
        print(f"error: operator path unavailable: {exc}", file=sys.stderr)
        raise SystemExit(3) from None
    except Exception as exc:
        if getattr(exc, "code", None) is None:
            raise
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(3 if getattr(exc, "code", None) == "unsafe_artifact" else 4) from None
