#!/usr/bin/env python3
"""HS4 REGRESS — offline regression-gate CLI.

Applies a PatchCandidate's diff in an isolated git worktree and runs the
deterministic gate (docs/DESIGN-HARNESS-SELF-IMPROVE.md §9 HS4):
declared assertions (HS4-1) + held-out test-fast (HS4-3) + smoke signal
(HS4-4). Writes ``.agent-lab/harness/candidates/{id}/regression_report.json``
regardless of verdict (HS4-5 — negative results preserved, never deleted).

Usage:
    python scripts/regress_harness.py --candidate-id pc-... --diff-path path/to.patch
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidate-id", required=True, help="harness_proposer.propose_candidate()가 발급한 id")
    parser.add_argument("--diff-path", required=True, help="적용할 unified diff 파일 경로")
    parser.add_argument("--root", help="repo root override (기본: 실제 repo root)")
    parser.add_argument("--git-root", help="git worktree add 대상 (기본: --root 또는 실제 repo root)")
    args = parser.parse_args()

    from agent_lab.regression_gate import regression_gate_enabled, run_regression_gate

    if not regression_gate_enabled():
        print("AGENT_LAB_REGRESSION_GATE=0 — set =1 to run the gate.", file=sys.stderr)
        return 2

    root = Path(args.root) if args.root else None
    git_root = Path(args.git_root) if args.git_root else (root or ROOT)

    report = run_regression_gate(
        args.candidate_id,
        diff_path=Path(args.diff_path),
        git_root=git_root,
        root=root,
    )

    print(f"verdict: {report.verdict}")
    print(f"reason: {report.reason}")
    if report.held_in.get("topics"):
        print(f"held_in topics: {report.held_in['topics']}")
    for a in report.assertions:
        status = "PASS" if a["passed"] else "FAIL"
        print(f"  assertion [{status}] {a['node_id']}")
    return 0 if report.verdict == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
