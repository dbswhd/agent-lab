"""Mission Loop API — Layer 6 orchestration state."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.server.deps import session_folder_or_404
from agent_lab.runtime.events import RuntimeEvent
from agent_lab.runtime.runtime import dispatch

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


def _dispatch_or_http(
    folder,
    event: RuntimeEvent,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = dispatch(folder, event, payload)
    if not out.handled:
        raise HTTPException(status_code=500, detail=out.reason or "dispatch failed")
    result = out.result if isinstance(out.result, dict) else {}
    if result.get("http_status") == 409:
        raise HTTPException(status_code=409, detail=result.get("reason") or "blocked")
    return result


@router.get("/sessions/{session_id}/mission-loop")
def get_mission_loop_state(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.mission.loop import public_mission_payload

    return public_mission_payload(folder)


@router.post("/sessions/{session_id}/mission-loop/enable")
def post_mission_loop_enable(
    session_id: str,
    body: MissionEnableRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.mission.loop import public_mission_payload

    _dispatch_or_http(
        folder,
        RuntimeEvent.MISSION_ENABLE,
        {"start_autonomous": body.start_autonomous},
    )
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

    result = _dispatch_or_http(
        folder,
        RuntimeEvent.MISSION_PLAN_GATE,
        {"plan_md": plan_md},
    )
    return {"ok": True, "session_id": session_id, **result}


@router.post("/sessions/{session_id}/mission-loop/advance")
def post_mission_advance(
    session_id: str,
    body: MissionAdvanceRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.mission.loop import public_mission_payload

    advance = _dispatch_or_http(
        folder,
        RuntimeEvent.MISSION_ADVANCE,
        {
            "permissions": body.permissions,
            "executor": body.executor,
        },
    )
    payload = public_mission_payload(folder)
    return {"ok": True, "session_id": session_id, "advance": advance, **payload}


@router.post("/sessions/{session_id}/mission-loop/pause")
def post_mission_pause(
    session_id: str,
    body: MissionPauseRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.mission.loop import public_mission_payload

    result = _dispatch_or_http(
        folder,
        RuntimeEvent.MISSION_PAUSE,
        {
            "reason": body.reason,
            "cleanup_executions": body.cleanup_executions,
        },
    )
    payload = public_mission_payload(folder)
    return {"ok": True, "session_id": session_id, "pause": result, **payload}


@router.post("/sessions/{session_id}/mission-loop/resume")
def post_mission_resume(
    session_id: str,
    body: MissionResumeRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.mission.loop import public_mission_payload

    result = _dispatch_or_http(
        folder,
        RuntimeEvent.MISSION_RESUME,
        {"resume_phase": body.resume_phase},
    )
    payload = public_mission_payload(folder)
    return {"ok": True, "session_id": session_id, "resume": result, **payload}


@router.post("/sessions/{session_id}/mission-loop/clear-circuit-breaker")
def post_clear_circuit_breaker(
    session_id: str,
    body: MissionResumeRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.mission.loop import public_mission_payload

    _dispatch_or_http(
        folder,
        RuntimeEvent.MISSION_CIRCUIT_CLEAR,
        {"resume_phase": body.resume_phase},
    )
    return public_mission_payload(folder)


@router.post("/sessions/{session_id}/mission-loop/discuss-recovery")
def post_mission_discuss_recovery(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.mission.loop import public_mission_payload

    result = _dispatch_or_http(folder, RuntimeEvent.MISSION_DISCUSS_RECOVERY, {})
    payload = public_mission_payload(folder)
    return {"ok": True, "session_id": session_id, "discuss_recovery": result, **payload}
