from __future__ import annotations

import shutil
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from agent_lab.attachments import list_attachment_names
from agent_lab.goal_loop import check_session_goal, goal_loop_enabled, set_session_goal

from app.server.deps import (
    RenameSessionRequest,
    SessionGoalPatchRequest,
    archive_meta,
    list_sessions,
    read_meta,
    save_uploads,
    session_detail,
    session_folder_or_404,
    write_meta,
)

router = APIRouter(prefix="/api")


@router.get("/sessions")
def sessions(archived: bool = False) -> dict[str, Any]:
    return {"sessions": list_sessions(archived=archived)}


@router.post("/sessions/{session_id}/archive")
def archive_session(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    archive_meta(folder)
    return {"ok": True, "id": session_id, "archived": True}


@router.post("/sessions/{session_id}/unarchive")
def unarchive_session(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    meta = read_meta(folder)
    meta["archived"] = False
    meta.pop("archived_at", None)
    write_meta(folder, meta)
    return {"ok": True, "id": session_id, "archived": False}


@router.get("/sessions/{session_id}")
def session(session_id: str) -> dict[str, Any]:
    return session_detail(session_id)


@router.patch("/sessions/{session_id}")
def rename_session(session_id: str, body: RenameSessionRequest) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    topic = body.topic.strip()
    (folder / "topic.txt").write_text(topic + "\n", encoding="utf-8")
    meta = read_meta(folder)
    meta["topic"] = topic
    write_meta(folder, meta)
    return {"ok": True, "id": session_id, "topic": topic}


@router.patch("/sessions/{session_id}/goal")
def patch_session_goal(
    session_id: str,
    body: SessionGoalPatchRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    try:
        result = set_session_goal(folder, body.text, max_checks=body.max_checks)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, **result}


@router.post("/sessions/{session_id}/goal/check")
def post_session_goal_check(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    if not goal_loop_enabled():
        raise HTTPException(status_code=409, detail="goal loop is disabled")
    result = check_session_goal(folder)
    if not result.get("checked") and result.get("reason") in {
        "goal_missing",
        "goal_loop_disabled",
    }:
        raise HTTPException(status_code=409, detail=result["reason"])
    return {"ok": True, **result}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    shutil.rmtree(folder)
    return {"ok": True, "id": session_id}


@router.post("/sessions/{session_id}/attachments")
async def upload_attachments(
    session_id: str,
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    saved = await save_uploads(folder, files)
    return {"ok": True, "saved": saved, "attachments": list_attachment_names(folder)}
