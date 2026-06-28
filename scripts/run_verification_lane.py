#!/usr/bin/env python3
"""Run a verification lane and write the latest local verification report."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from agent_lab.session.paths import sessions_dir  # noqa: E402
from agent_lab.subprocess_env import subprocess_env  # noqa: E402
from agent_lab.verification_report import (  # noqa: E402
    LANE_MARKER_EXPRESSIONS,
    VerificationLaneId,
    parse_collect_counts,
    update_verification_report,
)

MAX_FAILURE_LINES: Final = 80


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def collect_counts(marker_expression: str | None) -> tuple[int | None, int | None]:
    if not marker_expression:
        return None, None
    proc = subprocess.run(
        [
            str(ROOT / ".venv" / "bin" / "pytest"),
            "tests/",
            "--collect-only",
            "-q",
            "-m",
            marker_expression,
        ],
        cwd=ROOT,
        env=subprocess_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    return parse_collect_counts(f"{proc.stdout}\n{proc.stderr}")


def summarize_failure(lines: list[str]) -> str | None:
    for line in reversed(lines):
        text = line.strip()
        lower = text.lower()
        if text and (" failed" in lower or " error" in lower or text.startswith("FAILED ")):
            return text[:500]
    for line in reversed(lines):
        text = line.strip()
        if text:
            return text[:500]
    return None


def run_command(command: list[str]) -> tuple[int, list[str]]:
    proc = subprocess.Popen(
        command,
        cwd=ROOT,
        env=subprocess_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    tail: list[str] = []
    try:
        if proc.stdout is not None:
            for line in proc.stdout:
                print(line, end="")
                tail.append(line.rstrip("\n"))
                if len(tail) > MAX_FAILURE_LINES:
                    tail = tail[-MAX_FAILURE_LINES:]
        return proc.wait(), tail
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        tail.append("Interrupted by user")
        return 130, tail


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", choices=["fast", "integration", "bridge", "ci_full", "live"], required=True)
    parser.add_argument("--marker-expression", default=None)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("missing command after --")
    return args


def main() -> int:
    args = parse_args()
    lane: VerificationLaneId = args.lane
    marker_expression = args.marker_expression
    if marker_expression is None:
        marker_expression = LANE_MARKER_EXPRESSIONS[lane]
    selected_count, total_count = collect_counts(marker_expression)
    started_at = utc_now()
    started = time.monotonic()
    exit_code, tail = run_command(args.command)
    finished_at = utc_now()
    duration_seconds = time.monotonic() - started
    update_verification_report(
        sessions_dir=sessions_dir(),
        lane=lane,
        command=args.command,
        marker_expression=marker_expression,
        status="passed" if exit_code == 0 else "failed",
        exit_code=exit_code,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration_seconds,
        selected_count=selected_count,
        total_count=total_count,
        failure_summary=None if exit_code == 0 else summarize_failure(tail),
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
