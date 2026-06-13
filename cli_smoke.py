"""Profile Delegate smoke helper. Usage: python cli_smoke.py --profile reviewer --task 'Return JSON'."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from core import delegate_profile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--context", default="")
    parser.add_argument("--workdir", default="")
    parser.add_argument("--timeout-seconds", type=int, default=240)
    args = parser.parse_args()
    result = delegate_profile(
        profile=args.profile,
        task=args.task,
        context=args.context,
        timeout_seconds=args.timeout_seconds,
        workdir=args.workdir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
