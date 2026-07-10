"""Human mid-run steer API (ABSORB P1) — queue only, no gate bypass."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent_lab.steer import enqueue_steer, peek_steer_count

from app.server.deps import session_folder_or_404

router = APIRouter(prefix="/api")


class SteerBody(BaseModel):
    text: str = Field(..., min_length=1)
    target: str = "any"


@router.post("/sessions/{session_id}/steer")
def post_session_steer(session_id: str, body: SteerBody) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    try:
        result = enqueue_steer(folder, body.text, target=body.target)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "session_id": session_id,
        **result,
    }


@router.get("/sessions/{session_id}/steer")
def get_session_steer(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    return {
        "ok": True,
        "session_id": session_id,
        "queued": peek_steer_count(folder),
    }
