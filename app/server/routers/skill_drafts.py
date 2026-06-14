"""Skill draft API — list, promote, reject."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from agent_lab.skill_drafts import (
    promote_skill_draft,
    public_skill_drafts_payload,
    reject_skill_draft,
    skill_drafts_enabled,
)

from app.server.deps import session_folder_or_404

router = APIRouter(prefix="/api")


@router.get("/sessions/{session_id}/skills/drafts")
def get_session_skill_drafts(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    return {
        "ok": True,
        "session_id": session_id,
        **public_skill_drafts_payload(folder),
    }


@router.post("/sessions/{session_id}/skills/drafts/{draft_id}/promote")
def post_promote_skill_draft(session_id: str, draft_id: str) -> dict[str, Any]:
    if not skill_drafts_enabled():
        raise HTTPException(status_code=409, detail="skill drafts disabled")
    folder = session_folder_or_404(session_id)
    try:
        row = promote_skill_draft(folder, draft_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "ok": True,
        "session_id": session_id,
        "draft": row,
        **public_skill_drafts_payload(folder),
    }


@router.post("/sessions/{session_id}/skills/drafts/{draft_id}/reject")
def post_reject_skill_draft(session_id: str, draft_id: str) -> dict[str, Any]:
    if not skill_drafts_enabled():
        raise HTTPException(status_code=409, detail="skill drafts disabled")
    folder = session_folder_or_404(session_id)
    try:
        row = reject_skill_draft(folder, draft_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "ok": True,
        "session_id": session_id,
        "draft": row,
        **public_skill_drafts_payload(folder),
    }
