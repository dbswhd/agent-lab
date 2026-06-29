from __future__ import annotations

import shutil
from typing import Any, Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from agent_lab.attachments import list_attachment_names
from agent_lab.goal_loop import check_session_goal, goal_loop_enabled, set_session_goal
from agent_lab.response_contracts import (
    response_contract_presets,
    set_response_contract,
)

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


class ResponseContractPatchRequest(BaseModel):
    preset: Literal[
        "concise",
        "evidence_first",
        "plan_ready",
        "review_only",
        "build_handoff",
    ]


@router.get("/sessions")
def sessions(
    archived: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, Any]:
    items, total = list_sessions(archived=archived, limit=limit, offset=offset)
    return {"ok": True, "sessions": items, "total": total}


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
def session(
    session_id: str,
    chat_limit: int | None = None,
    chat_offset: int = 0,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.room import ensure_session_plan_pipeline

    ensure_session_plan_pipeline(folder)
    return session_detail(session_id, chat_limit=chat_limit, chat_offset=chat_offset)


@router.post("/sessions/{session_id}/plan/auto-sync")
def auto_sync_session_plan(
    session_id: str,
    chat_limit: int | None = None,
    chat_offset: int = 0,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.room import ensure_session_plan_pipeline

    synced = ensure_session_plan_pipeline(folder)
    detail = session_detail(session_id, chat_limit=chat_limit, chat_offset=chat_offset)
    return {**detail, "ok": True, "synced": synced}


@router.patch("/sessions/{session_id}")
def rename_session(session_id: str, body: RenameSessionRequest) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    topic = body.topic.strip()
    (folder / "topic.txt").write_text(topic + "\n", encoding="utf-8")
    meta = read_meta(folder)
    meta["topic"] = topic
    write_meta(folder, meta)
    return {"ok": True, "id": session_id, "topic": topic}


@router.patch("/sessions/{session_id}/response-contract")
def patch_session_response_contract(
    session_id: str,
    body: ResponseContractPatchRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    contract = set_response_contract(folder, body.preset)
    return {
        "ok": True,
        "response_contract": contract,
        "presets": response_contract_presets(),
    }


@router.patch("/sessions/{session_id}/goal")
def patch_session_goal(
    session_id: str,
    body: SessionGoalPatchRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.plan.workflow import is_plan_workflow_active
    from agent_lab.run.meta import read_run_meta

    if is_plan_workflow_active(read_run_meta(folder)):
        raise HTTPException(
            status_code=409,
            detail="manual goal patch disabled during plan workflow; approve plan.md instead",
        )
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
