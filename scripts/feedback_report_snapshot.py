#!/usr/bin/env python3
"""Persist a feedback_report snapshot with timestamp + git metadata.

This is for dogfood evidence capture: after live supervisor sessions, save the
current ``make feedback-report JSON=1`` state into ``sessions/_benchmark/reports``
so N1/N4 review has a durable artifact instead of terminal-only output.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_lab.feedback_report import build_feedback_report  # noqa: E402


def _git_output(root: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return proc.stdout.strip()


def build_snapshot(root: Path, report: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    ts = now or datetime.now(UTC)
    return {
        "captured_at": ts.isoformat().replace("+00:00", "Z"),
        "git_rev": _git_output(root, "rev-parse", "HEAD"),
        "git_branch": _git_output(root, "rev-parse", "--abbrev-ref", "HEAD"),
        "git_dirty": bool(_git_output(root, "status", "--short")),
        "root": str(root),
        "report": report,
    }


def write_snapshot(out_dir: Path, payload: dict[str, Any]) -> Path:
    captured_at = str(payload.get("captured_at") or "")
    stamp = captured_at.replace("-", "").replace(":", "").replace("T", "T").replace("Z", "Z")
    filename = f"feedback-report-{stamp}.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Project root that holds .agent-lab/outcomes.jsonl")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "sessions" / "_benchmark" / "reports",
        help="Directory to store the snapshot JSON",
    )
    parser.add_argument("--json", action="store_true", help="Emit the payload JSON to stdout after saving")
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    report = build_feedback_report(root)
    payload = build_snapshot(root, report)
    saved = write_snapshot(args.out_dir.expanduser().resolve(), payload)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(saved)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
