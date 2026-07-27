"""2026-07-23 restoration evidence: Slice 1/3 soft authority via real production HTTP routes.

Restores AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY / AGENT_LAB_MISSION_EXECUTION_WRITE_AUTHORITY,
retired 2026-07-14 (commit 8ccfe2c2), for a cohort session -- under the CURRENT
dual_write_enabled() semantics (non-empty AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS
required; the 2026-07-14 "empty allowlist = all sessions" shortcut no longer
applies). Exercises the real FastAPI routes via TestClient (not internal function
calls), same pattern as scripts/mission_ui_read_model_cohort.py.

Scope: plan approve/reject through /api/sessions/{id}/plan/{approve,reject} (Slice 1),
plus a rollback check (flag off -> legacy-first). Execution authority (Slice 3) is
covered at the function level by tests/test_mission_dual_write.py
(test_execution_write_authority_commit_approve) -- a real-worktree HTTP-route
evidence run for execute/merge/reverify is a separate, larger exercise (needs git
worktree scaffolding) and is intentionally out of scope here.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _client(sessions_root: Path) -> Any:
    from fastapi.testclient import TestClient
    from agent_lab.session import paths as session_paths
    from agent_lab import session as session_module
    import app.server.deps as deps_mod
    from app.server.main import create_app

    session_paths.SESSIONS_DIR = sessions_root
    session_module.SESSIONS_DIR = sessions_root
    deps_mod.SESSIONS_DIR = sessions_root
    return TestClient(create_app(bootstrap=False))


def _seed_session(sessions_root: Path, session_id: str, *, phase: str = "HUMAN_PENDING") -> Path:
    folder = sessions_root / session_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "plan.md").write_text("# Plan\n\n- ship widget\n", encoding="utf-8")
    (folder / "run.json").write_text(
        json.dumps({"plan_workflow": {"enabled": True, "phase": phase}}), encoding="utf-8"
    )
    return folder


def run(sessions_root: Path) -> dict[str, Any]:
    os.environ.setdefault("AGENT_LAB_MOCK_AGENTS", "1")
    os.environ["AGENT_LAB_MISSION_DUAL_WRITE"] = "1"
    os.environ["AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY"] = "1"

    client = _client(sessions_root)
    report: dict[str, Any] = {}

    # 1. Authority ON, session IN the allowlist -> real route uses Mission-first commit.
    sid_approve = "auth-route-approve"
    _seed_session(sessions_root, sid_approve)
    os.environ["AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS"] = sid_approve
    resp = client.post(f"/api/sessions/{sid_approve}/plan/approve", json={"goal": "ship widget"})
    body = resp.json()
    journal = sessions_root / sid_approve / ".agent-lab" / "mission-events.jsonl"
    report["approve_via_authority"] = {
        "status_code": resp.status_code,
        "plan_workflow_phase": body.get("plan_workflow", {}).get("phase"),
        "mission_dual_write_mirrored": body.get("mission_dual_write", {}).get("mirrored"),
        "journal_created": journal.is_file(),
        "journal_has_plan_approved": "PlanApproved" in journal.read_text(encoding="utf-8") if journal.is_file() else False,
    }

    # 2. Reject -> REFINE via authority path.
    sid_reject = "auth-route-reject"
    _seed_session(sessions_root, sid_reject)
    os.environ["AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS"] = f"{sid_approve},{sid_reject}"
    resp = client.post(
        f"/api/sessions/{sid_reject}/plan/reject",
        json={"note": "narrow scope", "target_phase": "REFINE"},
    )
    body = resp.json()
    report["reject_via_authority"] = {
        "status_code": resp.status_code,
        "plan_workflow_phase": body.get("plan_workflow", {}).get("phase"),
        "mission_dual_write_mirrored": body.get("mission_dual_write", {}).get("mirrored"),
    }

    # 3. Session NOT in the allowlist -> falls back to legacy-first + mirror (unaffected).
    sid_outside = "auth-route-outside-cohort"
    _seed_session(sessions_root, sid_outside)
    # deliberately do not add sid_outside to the allowlist
    resp = client.post(f"/api/sessions/{sid_outside}/plan/approve", json={"goal": "ship widget"})
    body = resp.json()
    report["outside_cohort_stays_legacy"] = {
        "status_code": resp.status_code,
        "plan_workflow_phase": body.get("plan_workflow", {}).get("phase"),
        "mission_dual_write_mirrored": body.get("mission_dual_write", {}).get("mirrored"),
        "mission_dual_write_reason": body.get("mission_dual_write", {}).get("reason"),
    }

    # 4. Rollback: flag off -> even an allowlisted session falls back to legacy-first.
    del os.environ["AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY"]
    sid_rollback = "auth-route-rollback"
    _seed_session(sessions_root, sid_rollback)
    os.environ["AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS"] = f"{sid_approve},{sid_reject},{sid_rollback}"
    resp = client.post(f"/api/sessions/{sid_rollback}/plan/approve", json={"goal": "ship widget"})
    body = resp.json()
    report["rollback_flag_off"] = {
        "status_code": resp.status_code,
        "plan_workflow_phase": body.get("plan_workflow", {}).get("phase"),
        "mission_dual_write_mirrored": body.get("mission_dual_write", {}).get("mirrored"),
        "mission_dual_write_operation": body.get("mission_dual_write", {}).get("operation"),
    }

    del os.environ["AGENT_LAB_MISSION_DUAL_WRITE"]
    del os.environ["AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS"]

    report["pass"] = (
        report["approve_via_authority"]["status_code"] == 200
        and report["approve_via_authority"]["plan_workflow_phase"] == "APPROVED"
        and report["approve_via_authority"]["mission_dual_write_mirrored"] is True
        and report["approve_via_authority"]["journal_has_plan_approved"] is True
        and report["reject_via_authority"]["status_code"] == 200
        and report["reject_via_authority"]["plan_workflow_phase"] == "REFINE"
        and report["reject_via_authority"]["mission_dual_write_mirrored"] is True
        and report["outside_cohort_stays_legacy"]["status_code"] == 200
        and report["outside_cohort_stays_legacy"]["plan_workflow_phase"] == "APPROVED"
        and report["outside_cohort_stays_legacy"]["mission_dual_write_reason"] == "cohort_not_selected"
        and report["rollback_flag_off"]["status_code"] == 200
        and report["rollback_flag_off"]["plan_workflow_phase"] == "APPROVED"
        and report["rollback_flag_off"]["mission_dual_write_operation"] == "plan_approve"
    )
    return report


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.sessions)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
