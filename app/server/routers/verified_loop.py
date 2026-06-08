"""Verified loop approval API (LazyCodex-inspired)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.server.deps import session_folder_or_404

router = APIRouter(prefix="/api")


class VerifiedLoopApproveRequest(BaseModel):
    goal: str | None = Field(default=None, max_length=2000)
    completion_promise: str | None = Field(default=None, max_length=120)
    criteria: str | None = Field(default=None, max_length=2000)


class VerifiedLoopRejectRequest(BaseModel):
    note: str = Field(default="", max_length=500)


@router.post("/sessions/{session_id}/verified-loop/approve")
def post_verified_loop_approve(
    session_id: str,
    body: VerifiedLoopApproveRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.verified_loop import approve_verified_loop

    try:
        result = approve_verified_loop(
            folder,
            goal=body.goal,
            completion_promise=body.completion_promise,
            criteria=body.criteria,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "session_id": session_id, **result}


@router.post("/sessions/{session_id}/verified-loop/reject")
def post_verified_loop_reject(
    session_id: str,
    body: VerifiedLoopRejectRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.verified_loop import reject_verified_loop

    loop = reject_verified_loop(folder, note=body.note)
    return {"ok": True, "session_id": session_id, "verified_loop": loop}
