"""Plan workflow approval API (Merge Verified)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.server.deps import session_folder_or_404

router = APIRouter(prefix="/api")


class PlanApproveRequest(BaseModel):
    goal: str | None = Field(default=None, max_length=2000)
    completion_promise: str | None = Field(default=None, max_length=120)
    criteria: str | None = Field(default=None, max_length=2000)


class PlanRejectRequest(BaseModel):
    note: str = Field(default="", max_length=500)
    target_phase: str = Field(default="CLARIFY", max_length=32)


@router.get("/sessions/{session_id}/plan/workflow")
def get_plan_workflow(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.plan.workflow import plan_workflow_public
    from agent_lab.run.meta import read_run_meta

    run = read_run_meta(folder)
    plan_md = ""
    plan_path = folder / "plan.md"
    if plan_path.is_file():
        plan_md = plan_path.read_text(encoding="utf-8")
    return {
        "ok": True,
        "session_id": session_id,
        "plan_md": plan_md,
        **plan_workflow_public(run),
    }


@router.post("/sessions/{session_id}/plan/approve")
def post_plan_approve(
    session_id: str,
    body: PlanApproveRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.mission.dual_write import plan_write_authority_enabled
    from agent_lab.plan.workflow import approve_plan, approve_plan_with_mission_authority

    try:
        if plan_write_authority_enabled(folder):
            result = approve_plan_with_mission_authority(
                folder,
                goal=body.goal,
                completion_promise=body.completion_promise,
                criteria=body.criteria,
            )
            bridge = result.pop("mission_dual_write", {"enabled": True, "mirrored": True})
            return {"ok": True, "session_id": session_id, "mission_dual_write": bridge, **result}

        result = approve_plan(
            folder,
            goal=body.goal,
            completion_promise=body.completion_promise,
            criteria=body.criteria,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    from agent_lab.mission.dual_write import mirror_plan_approval

    bridge = mirror_plan_approval(folder, goal=body.goal)
    return {"ok": True, "session_id": session_id, "mission_dual_write": bridge, **result}


@router.post("/sessions/{session_id}/plan/reject")
def post_plan_reject(
    session_id: str,
    body: PlanRejectRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.mission.dual_write import plan_write_authority_enabled
    from agent_lab.plan.workflow import reject_plan, reject_plan_with_mission_authority

    phase = body.target_phase.strip().upper() or "CLARIFY"
    if phase not in {"CLARIFY", "REFINE", "DRAFT"}:
        raise HTTPException(status_code=422, detail="invalid target_phase")

    try:
        if plan_write_authority_enabled(folder):
            result = reject_plan_with_mission_authority(
                folder,
                note=body.note,
                target_phase=phase,  # type: ignore[arg-type]
                goal=None,
            )
            bridge = result.pop("mission_dual_write", {"enabled": True, "mirrored": True})
            return {
                "ok": True,
                "session_id": session_id,
                "plan_workflow": result["plan_workflow"],
                "mission_dual_write": bridge,
            }

        pw = reject_plan(folder, note=body.note, target_phase=phase)  # type: ignore[arg-type]
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    from agent_lab.mission.dual_write import mirror_plan_rejection

    bridge = mirror_plan_rejection(folder, note=body.note)
    return {"ok": True, "session_id": session_id, "plan_workflow": pw, "mission_dual_write": bridge}
