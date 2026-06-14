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
    from agent_lab.plan_workflow import plan_workflow_public
    from agent_lab.run_meta import read_run_meta

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
    from agent_lab.plan_workflow import approve_plan

    try:
        result = approve_plan(
            folder,
            goal=body.goal,
            completion_promise=body.completion_promise,
            criteria=body.criteria,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "session_id": session_id, **result}


@router.post("/sessions/{session_id}/plan/reject")
def post_plan_reject(
    session_id: str,
    body: PlanRejectRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.plan_workflow import reject_plan

    phase = body.target_phase.strip().upper() or "CLARIFY"
    if phase not in {"CLARIFY", "REFINE", "DRAFT"}:
        raise HTTPException(status_code=422, detail="invalid target_phase")
    pw = reject_plan(folder, note=body.note, target_phase=phase)  # type: ignore[arg-type]
    return {"ok": True, "session_id": session_id, "plan_workflow": pw}
