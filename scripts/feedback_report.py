#!/usr/bin/env python3
"""S1.5 feedback effect report — bucket outcomes.jsonl by advisor_source.

Answers "did the advisor actually help?" by comparing clean-pass / repair /
BLOCK rates across default / history / explore buckets. See the S1.5 plan and
docs/DESIGN-S1-FEEDBACK-LOOP.md.

Usage:
    python scripts/feedback_report.py [--root DIR] [--json]

--root points at the directory that holds ``.agent-lab/outcomes.jsonl``
(defaults to AGENT_LAB_OUTCOMES_ROOT or the project root).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_lab.feedback_report import build_feedback_report, render_feedback_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="S1.5 advisor feedback effect report")
    parser.add_argument("--root", type=str, default=None, help="dir holding .agent-lab/outcomes.jsonl")
    parser.add_argument("--json", action="store_true", help="emit raw JSON instead of a table")
    args = parser.parse_args()

    root = Path(args.root) if args.root else None
    report = build_feedback_report(root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_feedback_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
