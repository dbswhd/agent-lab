#!/usr/bin/env python3
"""N8 QUICKSTART path verification — mock mission + smoke + fork_time report.

Runs the post-install path from docs/QUICKSTART.md §2–4 (does not run make install).

Usage:
    python scripts/verify_quickstart.py
    python scripts/verify_quickstart.py --json
    python scripts/verify_quickstart.py --max-minutes 15
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run_step(label: str, cmd: list[str], *, env: dict[str, str]) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    tail = (proc.stderr or proc.stdout or "")[-2000:]
    if proc.returncode != 0:
        print(f"FAIL [{label}]: exit {proc.returncode}\n{tail}", file=sys.stderr)
    return proc.returncode, tail


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--max-minutes",
        type=int,
        default=15,
        help="Fail if mission path exceeds this many minutes (default 15)",
    )
    parser.add_argument("--skip-mission", action="store_true", help="Only run smoke (static fixtures)")
    args = parser.parse_args()

    from agent_lab.subprocess_env import subprocess_env

    env = subprocess_env(AGENT_LAB_MOCK_AGENTS="1", AGENT_LAB_CLARIFIER="0")
    py = sys.executable
    started = time.monotonic()
    steps: list[dict[str, object]] = []

    if not args.skip_mission:
        code, _ = _run_step(
            "dogfood S1",
            [py, "scripts/run_dogfood_suite.py", "--mode", "mock", "--only", "S1"],
            env=env,
        )
        steps.append({"step": "dogfood_s1", "ok": code == 0})
        if code != 0:
            return code

    code, _ = _run_step("smoke", [py, "scripts/smoke_room.py"], env=env)
    steps.append({"step": "smoke", "ok": code == 0})
    if code != 0:
        return code

    elapsed = time.monotonic() - started
    fork_time_minutes = max(1, math.ceil(elapsed / 60))
    over_budget = fork_time_minutes > args.max_minutes

    report = {
        "ok": not over_budget,
        "fork_time_seconds": round(elapsed, 2),
        "fork_time_minutes": fork_time_minutes,
        "max_minutes": args.max_minutes,
        "steps": steps,
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"OK: quickstart mission path {report['fork_time_seconds']}s "
            f"(fork_time_minutes={fork_time_minutes}, budget={args.max_minutes})"
        )

    if over_budget:
        print(
            f"FAIL: fork_time_minutes {fork_time_minutes} > {args.max_minutes}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
