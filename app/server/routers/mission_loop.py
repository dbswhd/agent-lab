"""Mission Loop API — Layer 6 orchestration state."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.server.deps import session_folder_or_404

router = APIRouter(prefix="/api")


class MissionEnableRequest(BaseModel):
    start_autonomous: bool = True


class MissionResumeRequest(BaseModel):
    resume_phase: str = Field(default="DISCUSS", max_length=40)


class MissionPlanGateRequest(BaseModel):
    plan_md: str | None = Field(default=None, max_length=200_000)


class MissionAdvanceRequest(BaseModel):
    permissions: dict[str, Any] | None = None
    executor: str | None = Field(default=None, max_length=40)


class MissionPauseRequest(BaseModel):
    reason: str = Field(default="user_cancel", max_length=200)
    cleanup_executions: bool = True


@router.get("/sessions/{session_id}/mission-loop")
def get_mission_loop_state(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.mission_loop import public_mission_payload

    return public_mission_payload(folder)


@router.post("/sessions/{session_id}/mission-loop/enable")
def post_mission_loop_enable(
    session_id: str,
    body: MissionEnableRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.mission_loop import enable_mission_loop, public_mission_payload

    enable_mission_loop(folder, start_autonomous=body.start_autonomous)
    return public_mission_payload(folder)


@router.post("/sessions/{session_id}/mission-loop/plan-gate")
def post_mission_plan_gate(
    session_id: str,
    body: MissionPlanGateRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    plan_path = folder / "plan.md"
    plan_md = body.plan_md
    if plan_md is None:
        if not plan_path.is_file():
            raise HTTPException(status_code=404, detail="plan.md not found")
        plan_md = plan_path.read_text(encoding="utf-8")
    from agent_lab.mission_loop import run_plan_gate

    result = run_plan_gate(folder, plan_md)
    if result.get("http_status") == 409:
        raise HTTPException(status_code=409, detail=result.get("reason") or "blocked")
    return {"ok": True, "session_id": session_id, **result}


@router.post("/sessions/{session_id}/mission-loop/advance")
def post_mission_advance(
    session_id: str,
    body: MissionAdvanceRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.mission_loop import maybe_advance_mission, public_mission_payload

    advance = maybe_advance_mission(
        folder,
        permissions=body.permissions,
        executor=body.executor,
    )
    payload = public_mission_payload(folder)
    return {"ok": True, "session_id": session_id, "advance": advance, **payload}


@router.post("/sessions/{session_id}/mission-loop/pause")
def post_mission_pause(
    session_id: str,
    body: MissionPauseRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.mission_loop import pause_mission_loop, public_mission_payload

    result = pause_mission_loop(
        folder,
        reason=body.reason,
        cleanup_executions=body.cleanup_executions,
    )
    payload = public_mission_payload(folder)
    return {"ok": True, "session_id": session_id, "pause": result, **payload}


@router.post("/sessions/{session_id}/mission-loop/resume")
def post_mission_resume(
    session_id: str,
    body: MissionResumeRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.mission_loop import public_mission_payload, resume_mission_loop

    result = resume_mission_loop(folder, resume_phase=body.resume_phase)
    payload = public_mission_payload(folder)
    return {"ok": True, "session_id": session_id, "resume": result, **payload}


@router.post("/sessions/{session_id}/mission-loop/clear-circuit-breaker")
def post_clear_circuit_breaker(
    session_id: str,
    body: MissionResumeRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.mission_loop import clear_circuit_breaker, public_mission_payload

    clear_circuit_breaker(folder, resume_phase=body.resume_phase)
    return public_mission_payload(folder)
