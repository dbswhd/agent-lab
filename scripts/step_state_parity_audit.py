#!/usr/bin/env python3
"""Characterization audit: how well does execution-row status predict mission_loop.phase?

Read-only. Walks sessions/_regression/*/run.json and reports two things, without
asserting either must hold:

1. Phase parity -- for fixtures where mission_loop.current_action_index is set,
   does step_state.derive_step_phase() of the matching execution row agree with
   the mission_loop-phase bucket implied by mission_loop.phase?
2. Repair-count parity -- for every execution row, does mission_loop.action_repair_counts[idx]
   equal len(row.repair_history)?

This does not change any behavior; it produces the ratchet baseline consumed by
tests/test_step_state_parity_ratchet.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGRESSION_DIR = ROOT / "sessions" / "_regression"
BASELINE_PATH = ROOT / "tests" / "fixtures" / "step-state-parity-baseline.json"

sys.path.insert(0, str(ROOT / "src"))

from agent_lab.mission.step_state import derive_step_phase, repair_count_from_history  # noqa: E402

# mission_loop.phase -> the step-phase bucket it implies for the *current* action.
_PHASE_TO_STEP = {
    "DRY_RUN": "MERGE_REVIEW",
    "MERGE_REVIEW": "MERGE_REVIEW",
    "VERIFY": "VERIFYING",
    "REPAIR": "REPAIRING",
    "EXECUTE_QUEUE": "NOT_STARTED",
}


def _find_row(executions: list[Any], action_index: int) -> dict[str, Any] | None:
    for row in reversed(executions or []):
        if isinstance(row, dict) and row.get("action_index") == action_index:
            return row
    return None


def audit() -> dict[str, Any]:
    phase_mismatches: list[dict[str, Any]] = []
    unmapped_statuses: list[dict[str, Any]] = []
    repair_mismatches: list[dict[str, Any]] = []

    for fixture_dir in sorted(p for p in REGRESSION_DIR.iterdir() if p.is_dir()):
        run_path = fixture_dir / "run.json"
        if not run_path.is_file():
            continue
        try:
            run = json.loads(run_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(run, dict):
            continue
        ml = run.get("mission_loop")
        ml = ml if isinstance(ml, dict) else {}
        raw_executions = run.get("executions")
        executions: list[Any] = raw_executions if isinstance(raw_executions, list) else []

        current_idx = ml.get("current_action_index")
        phase = str(ml.get("phase") or "")
        if isinstance(current_idx, int) and phase in _PHASE_TO_STEP:
            row = _find_row(executions, current_idx)
            derived = derive_step_phase(row)
            expected = _PHASE_TO_STEP[phase]
            if derived is None:
                unmapped_statuses.append(
                    {
                        "fixture": fixture_dir.name,
                        "action_index": current_idx,
                        "status": (row or {}).get("status"),
                        "mission_loop_phase": phase,
                    }
                )
            elif derived != expected:
                phase_mismatches.append(
                    {
                        "fixture": fixture_dir.name,
                        "action_index": current_idx,
                        "mission_loop_phase": phase,
                        "expected_step_phase": expected,
                        "derived_step_phase": derived,
                    }
                )

        repair_counts = ml.get("action_repair_counts")
        repair_counts = repair_counts if isinstance(repair_counts, dict) else {}
        seen_indices: set[int] = set()
        for row in executions:
            if not isinstance(row, dict):
                continue
            idx = row.get("action_index")
            if not isinstance(idx, int) or idx in seen_indices:
                continue
            seen_indices.add(idx)
            counted = repair_counts.get(str(idx))
            if counted is None:
                continue
            from_history = repair_count_from_history(row)
            if counted != from_history:
                repair_mismatches.append(
                    {
                        "fixture": fixture_dir.name,
                        "action_index": idx,
                        "action_repair_counts": counted,
                        "repair_history_len": from_history,
                    }
                )

    return {
        "phase_mismatches": phase_mismatches,
        "unmapped_statuses": unmapped_statuses,
        "repair_mismatches": repair_mismatches,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if report exceeds the saved baseline")
    parser.add_argument("--update", action="store_true", help="write the current report as the new baseline")
    parser.add_argument("--print", action="store_true", dest="print_report", help="print the human-readable report")
    args = parser.parse_args()
    if not (args.check or args.update or args.print_report):
        parser.error("one of --check, --update, or --print is required")

    report = audit()

    if args.print_report:
        for key, rows in report.items():
            print(f"== {key} ({len(rows)}) ==")
            for row in rows:
                print(f"  {row}")

    if args.update:
        BASELINE_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote baseline: {BASELINE_PATH}")

    if args.check:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8")) if BASELINE_PATH.is_file() else {}
        new_findings = {
            key: [row for row in rows if row not in baseline.get(key, [])] for key, rows in report.items()
        }
        total_new = sum(len(rows) for rows in new_findings.values())
        if total_new:
            print(f"step-state parity ratchet FAILED: {total_new} new finding(s) not in baseline")
            for key, rows in new_findings.items():
                for row in rows:
                    print(f"  NEW {key}: {row}")
            return 1
        print("step-state parity ratchet OK: no new findings beyond baseline")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
