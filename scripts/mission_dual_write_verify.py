"""Read-only parity check: legacy `run.json` vs Mission read-model, per session.

Built for repeated use *while a dual-write cohort is actually running* (unlike
the evidence scripts in this directory, which generate synthetic traffic for
one-off pre-cutover proof). This script never writes anything — it only reads
`run.json` and replays the Mission journal (the exact same code path
`GET /api/sessions/{id}/mission/read-model` uses) and reports where the two
disagree.

Usage:
    .venv/bin/python scripts/mission_dual_write_verify.py --sessions sessions/
    .venv/bin/python scripts/mission_dual_write_verify.py --sessions sessions/ --session <id>
    .venv/bin/python scripts/mission_dual_write_verify.py --sessions sessions/ --cohort

``--cohort`` scopes the scan to ``AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS`` (the
same allowlist the production bridge itself honors) instead of every migrated
session — the natural "is my cohort healthy right now" check.

Exit code 0 iff no session has a hard_mismatch finding. ``mission_behind`` and
``review_needed`` findings never affect the exit code — they're expected under
the documented partial-parity design (bridge lags legacy by one route call in
some paths) and are reported for visibility, not as failures.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

# Legacy plan_workflow phases that mean "not yet approved" — Mission should
# still be DRAFTING (or unmigrated). Only APPROVED asserts a hard expectation.
_PRE_APPROVAL_PHASES = {"CLARIFY", "REFINE", "DRAFT", "HUMAN_PENDING", ""}


def _cohort_ids() -> frozenset[str]:
    raw = (os.getenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS") or "").strip()
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


def _load_run(folder: Path) -> dict[str, Any]:
    from agent_lab.run.meta import read_run_meta

    run_path = folder / "run.json"
    if run_path.is_file():
        try:
            parsed = json.loads(run_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"malformed run.json: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("malformed run.json: top-level value must be an object")
    return read_run_meta(folder)


def _latest_execution(run: dict[str, Any]) -> dict[str, Any] | None:
    rows = [row for row in (run.get("executions") or []) if isinstance(row, dict)]
    return rows[-1] if rows else None


def _legacy_commit_sha(execution: dict[str, Any] | None) -> str | None:
    if execution is None:
        return None
    merge = execution.get("merge")
    sha = (merge or {}).get("commit_sha") if isinstance(merge, dict) else None
    if sha:
        return str(sha)
    for repair in reversed(execution.get("repair_history") or []):
        if not isinstance(repair, dict):
            continue
        repair_merge = repair.get("merge")
        repair_sha = (
            (repair_merge or {}).get("commit_sha") if isinstance(repair_merge, dict) else repair.get("exec_commit_sha")
        )
        if repair_sha:
            return str(repair_sha)
    return None


def _legacy_oracle_verdict(execution: dict[str, Any] | None) -> str | None:
    if execution is None:
        return None
    oracle = execution.get("oracle")
    verdict = (oracle or {}).get("verdict") if isinstance(oracle, dict) else None
    return str(verdict).lower() if verdict else None


def _legacy_pending_inbox_ids(run: dict[str, Any]) -> set[str]:
    return {
        str(item.get("id"))
        for item in (run.get("human_inbox") or [])
        if isinstance(item, dict) and item.get("status") == "pending" and item.get("id")
    }


def _plan_phase(run: dict[str, Any]) -> str:
    pw = run.get("plan_workflow")
    return str((pw or {}).get("phase") or "") if isinstance(pw, dict) else ""


def _inbox_rows(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in (run.get("human_inbox") or []) if isinstance(row, dict)]


def _normalized_options(row: dict[str, Any]) -> str:
    options = row.get("options")
    if not isinstance(options, list) or any(not isinstance(option, dict) for option in options):
        return "<invalid-options>"
    return json.dumps(options, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalized_inbox_row(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("id") or ""),
        str(row.get("kind") or ""),
        str(row.get("status") or ""),
        _normalized_options(row),
    )


_TERMINAL_STATES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED"})


def _check_session(folder: Path) -> dict[str, Any]:
    from agent_lab.mission.application import MissionApplication
    from agent_lab.mission.kernel import MissionState
    from agent_lab.mission.read_model import build_read_model

    journal = folder / ".agent-lab" / "mission-events.jsonl"
    findings: list[dict[str, str]] = []
    if not journal.is_file():
        return {"session_id": folder.name, "migrated": False, "findings": [], "severity": "not_migrated"}

    run = _load_run(folder)
    goal = str(run.get("goal") or run.get("topic") or folder.name)
    mission = MissionApplication(folder, goal).load()
    model = build_read_model(mission, legacy_phase=_plan_phase(run), run=run)

    execution = _latest_execution(run)
    legacy_sha = _legacy_commit_sha(execution)
    mission_sha = mission.merged_commit_sha
    if legacy_sha and mission_sha:
        if legacy_sha != mission_sha:
            findings.append(
                {
                    "dimension": "merge_commit_sha",
                    "severity": "hard_mismatch",
                    "detail": f"legacy={legacy_sha} mission={mission_sha}",
                }
            )
    elif legacy_sha and not mission_sha:
        findings.append(
            {
                "dimension": "merge_commit_sha",
                "severity": "mission_behind",
                "detail": f"legacy has {legacy_sha}, mission has not recorded a merge yet",
            }
        )

    legacy_oracle = _legacy_oracle_verdict(execution)
    mission_oracle = model.oracle_verdict.value if model.oracle_verdict is not None else None
    if legacy_oracle and mission_oracle:
        if legacy_oracle != mission_oracle:
            findings.append(
                {
                    "dimension": "oracle_verdict",
                    "severity": "hard_mismatch",
                    "detail": f"legacy={legacy_oracle} mission={mission_oracle}",
                }
            )
    elif legacy_oracle and not mission_oracle:
        findings.append(
            {
                "dimension": "oracle_verdict",
                "severity": "mission_behind",
                "detail": f"legacy has verdict={legacy_oracle}, mission has not recorded an oracle event yet",
            }
        )

    # Item-level comparison via execution-level gates (see
    # docs/redesign-2026-07/evidence/execution-gate-design-draft-2026-07-13.md) — precise
    # per-item_id diff instead of a single boolean (legacy pending vs
    # mission.state == AWAITING_HUMAN), which couldn't tell you *which* item
    # was the problem and couldn't represent more than one pending item at once.
    legacy_rows = _inbox_rows(run)
    legacy_pending_rows = [row for row in legacy_rows if row.get("status") == "pending" and row.get("id")]
    legacy_pending_ids = {str(row["id"]) for row in legacy_pending_rows}
    duplicate_ids = {
        str(row["id"])
        for row in legacy_rows
        if row.get("id") and sum(1 for candidate in legacy_rows if candidate.get("id") == row.get("id")) > 1
    }
    mission_open_ids = {g.gate_id for g in mission.open_gates}
    mission_rows = {str(row.get("id")): row for row in model.inbox_items if row.get("id")}
    missing_in_mission = legacy_pending_ids - mission_open_ids
    if missing_in_mission:
        findings.append(
            {
                "dimension": "human_inbox",
                "severity": "hard_mismatch",
                "detail": f"legacy pending but no Mission gate open: {sorted(missing_in_mission)}",
            }
        )
    for item_id in sorted(legacy_pending_ids & mission_open_ids):
        legacy_row = next(row for row in legacy_pending_rows if str(row.get("id")) == item_id)
        mission_row = mission_rows.get(item_id)
        if mission_row is None:
            continue
        if _normalized_options(legacy_row) == "<invalid-options>":
            findings.append(
                {
                    "dimension": "human_inbox_options",
                    "severity": "hard_mismatch",
                    "detail": f"item {item_id} options are not a list of objects",
                }
            )
            continue
        if _normalized_inbox_row(legacy_row)[1:] != _normalized_inbox_row(mission_row)[1:]:
            findings.append(
                {
                    "dimension": "human_inbox_options"
                    if _normalized_options(legacy_row) != _normalized_options(mission_row)
                    else "human_inbox_row",
                    "severity": "hard_mismatch",
                    "detail": f"item {item_id} normalized legacy/Mission row differs",
                }
            )
    if duplicate_ids:
        findings.append(
            {
                "dimension": "unexpected_duplicate",
                "severity": "hard_mismatch",
                "detail": f"legacy human inbox has duplicate ids: {sorted(duplicate_ids)}",
            }
        )
    mission_summary = model.inbox_summary
    actionable_items = [
        row for row in model.inbox_items if row.get("status") == "pending" and row.get("actionable", True) is True
    ]
    if mission_summary is not None and mission_summary.pending_count != len(actionable_items):
        findings.append(
            {
                "dimension": "inbox_summary",
                "severity": "hard_mismatch",
                "detail": f"pending_count={mission_summary.pending_count} but actionable_items={len(actionable_items)}",
            }
        )
    is_terminal = mission.state.value in _TERMINAL_STATES
    stale_in_mission = mission_open_ids - legacy_pending_ids
    if stale_in_mission and not is_terminal:
        findings.append(
            {
                "dimension": "human_inbox",
                "severity": "hard_mismatch",
                "detail": f"Mission gate open but legacy item not pending (resolved or never existed): {sorted(stale_in_mission)}",
            }
        )

    # Terminal missions aren't expected to keep tracking legacy pending state —
    # a lingering gate there is a data-hygiene signal (missed CloseExecutionGate
    # call), not a live divergence, so it's review_needed instead of hard_mismatch
    # and replaces (rather than adds to) the stale_in_mission check above.
    if is_terminal and mission.open_gates:
        findings.append(
            {
                "dimension": "orphaned_gate",
                "severity": "review_needed",
                "detail": f"mission terminal ({mission.state.value}) but gate(s) never closed: {sorted(g.gate_id for g in mission.open_gates)}",
            }
        )

    plan_phase = _plan_phase(run)
    if plan_phase == "APPROVED" and mission.state in (MissionState.DRAFTING, MissionState.AWAITING_PLAN_DECISION):
        findings.append(
            {
                "dimension": "plan_phase",
                "severity": "review_needed",
                "detail": f"legacy plan_workflow.phase=APPROVED but mission.state={mission.state.value}",
            }
        )

    severities = {f["severity"] for f in findings}
    overall = (
        "hard_mismatch"
        if "hard_mismatch" in severities
        else (
            "review_needed"
            if "review_needed" in severities
            else ("mission_behind" if "mission_behind" in severities else "ok")
        )
    )
    expected_boundary_count = sum(
        1
        for finding in findings
        if finding["dimension"] == "mission_not_ready_to_execute" or finding["severity"] == "expected_boundary"
    )
    return {
        "session_id": folder.name,
        "migrated": True,
        "mission_state": mission.state.value,
        "operational_status": model.operational_status.value,
        "open_gate_ids": sorted(mission_open_ids),
        "legacy_plan_phase": plan_phase,
        "missing": len(missing_in_mission),
        "unexpected_duplicate": len(duplicate_ids),
        "mismatch": sum(1 for finding in findings if finding["severity"] == "hard_mismatch"),
        "mission_not_ready_to_execute": expected_boundary_count,
        "findings": findings,
        "severity": overall,
    }


def run_verification(sessions_root: Path, *, only_session: str | None, cohort_only: bool) -> dict[str, Any]:
    cohort_ids = _cohort_ids() if cohort_only else frozenset()
    if cohort_only and not cohort_ids:
        return {
            "sessions_root": str(sessions_root),
            "checked": 0,
            "not_found": 0,
            "error_count": 1,
            "errors": ["--cohort requires a non-empty AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS allowlist"],
            "mismatch": 0,
            "missing": 0,
            "unexpected_duplicate": 0,
            "mission_not_ready_to_execute": 0,
            "migrated_count": 0,
            "hard_mismatch_count": 0,
            "hard_mismatch_sessions": [],
            "results": [],
        }
    if not sessions_root.is_dir():
        missing_ids = [only_session] if only_session else sorted(cohort_ids) if cohort_only else []
        results = [
            {
                "session_id": session_id,
                "migrated": False,
                "findings": [],
                "severity": "not_found",
                "missing": 0,
                "unexpected_duplicate": 0,
                "mismatch": 0,
                "mission_not_ready_to_execute": 0,
            }
            for session_id in missing_ids
        ]
        report = {
            "sessions_root": str(sessions_root),
            "checked": len(results),
            "not_found": len(results),
            "error_count": 1 if cohort_only else 0,
            "errors": ["--cohort allowlist matched no session directories"] if cohort_only else [],
            "mismatch": 0,
            "missing": 0,
            "unexpected_duplicate": 0,
            "mission_not_ready_to_execute": 0,
            "hard_mismatch_count": 0,
            "results": results,
        }
        return report

    if only_session:
        targets = [sessions_root / only_session]
    elif cohort_only:
        targets = [sessions_root / sid for sid in sorted(cohort_ids)]
    else:
        targets = sorted(p for p in sessions_root.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))

    results: list[dict[str, Any]] = []
    for folder in targets:
        if not folder.is_dir():
            results.append(
                {
                    "session_id": folder.name,
                    "migrated": False,
                    "findings": [],
                    "severity": "not_found",
                    "missing": 0,
                    "unexpected_duplicate": 0,
                    "mismatch": 0,
                    "mission_not_ready_to_execute": 0,
                }
            )
            continue
        try:
            results.append(_check_session(folder))
        except Exception as exc:  # one bad session must not abort the scan
            results.append(
                {
                    "session_id": folder.name,
                    "migrated": None,
                    "findings": [],
                    "severity": "error",
                    "error": str(exc)[:300],
                    "missing": 0,
                    "unexpected_duplicate": 0,
                    "mismatch": 1,
                    "mission_not_ready_to_execute": 0,
                }
            )

    migrated = [r for r in results if r.get("migrated")]
    hard = [r for r in migrated if r["severity"] == "hard_mismatch"]
    errors = [r for r in results if r.get("severity") == "error"]
    not_found = [r for r in results if r.get("severity") == "not_found"]
    matched = [r for r in results if r.get("severity") != "not_found"]
    scope_errors = [str(r["error"]) for r in errors if r.get("error")]
    if cohort_only and not matched:
        scope_errors.append("--cohort allowlist matched no session directories")
    return {
        "sessions_root": str(sessions_root),
        "checked": len(results),
        "not_found": len(not_found),
        "error_count": len(errors) + (1 if cohort_only and not matched else 0),
        "errors": scope_errors,
        "mismatch": sum(int(r.get("mismatch") or 0) for r in migrated) + len(errors),
        "missing": sum(int(r.get("missing") or 0) for r in migrated),
        "unexpected_duplicate": sum(int(r.get("unexpected_duplicate") or 0) for r in migrated),
        "mission_not_ready_to_execute": sum(int(r.get("mission_not_ready_to_execute") or 0) for r in results),
        "migrated_count": len(migrated),
        "hard_mismatch_count": len(hard),
        "hard_mismatch_sessions": [r["session_id"] for r in hard],
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--session", type=str, default=None, help="check a single session_id only")
    parser.add_argument("--cohort", action="store_true", help="check only AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS")
    args = parser.parse_args()
    report = run_verification(args.sessions, only_session=args.session, cohort_only=args.cohort)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["hard_mismatch_count"] == 0 and report["error_count"] == 0 and report["not_found"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
