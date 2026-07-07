#!/usr/bin/env python3
"""OpenAI식 eval surface local runner — case → trace → grader → report.

Usage:
    .venv/bin/python evals/run_local.py --cases evals/cases.jsonl --out evals/results/latest.json

Fixture/mock-safe only: cases resolve to committed ``sessions/_regression``
fixtures or deterministic mock runs in a temporary sessions directory (never a
live agent run). See docs/EVAL-SURFACE-V1-PLAN.md.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.cases import load_cases
from evals.report import FORK_TIME_MINUTES_BASELINE, REGRESSION_DIR, build_report

ROOT = Path(__file__).resolve().parents[1]
_REGRESSION_DIR = REGRESSION_DIR
_FORK_TIME_MINUTES_BASELINE = FORK_TIME_MINUTES_BASELINE
_load_cases = load_cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=ROOT / "evals" / "cases.jsonl")
    parser.add_argument("--out", type=Path, default=ROOT / "evals" / "results" / "latest.json")
    args = parser.parse_args()

    cases_path = args.cases
    out_path = args.out
    if not isinstance(cases_path, Path) or not isinstance(out_path, Path):
        raise TypeError("argparse path conversion failed")

    report = build_report(load_cases(cases_path))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = report["summary"]
    failed = summary["failed"]
    print(f"eval-surface-local: {summary['graded']} graded, {summary['skipped']} skipped, {len(failed)} failed")
    if failed:
        print(f"  failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
