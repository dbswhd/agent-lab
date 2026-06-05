from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from agent_lab.human_inbox import (
    create_inbox_item,
    public_inbox_payload,
    resolve_inbox_item,
    supersede_pending_inbox,
)
from agent_lab.run_meta import read_run_meta

from app.server.deps import (
    HumanInboxCreateRequest,
    HumanInboxResolveRequest,
    session_folder_or_404,
)

router = APIRouter(prefix="/api")


@router.get("/sessions/{session_id}/inbox")
def get_session_inbox(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    run = read_run_meta(folder)
    return {"ok": True, "session_id": session_id, **public_inbox_payload(run)}


@router.post("/sessions/{session_id}/inbox/items")
def create_session_inbox_item(
    session_id: str,
    body: HumanInboxCreateRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    try:
        item = create_inbox_item(
            folder,
            kind=body.kind,
            source=body.source or "manual",
            prompt=body.prompt,
            options=body.options,
            multi_select=body.multi_select,
            action_ref=body.action_ref,
            summary=body.summary,
            risks=body.risks,
            human_turn_id=body.human_turn_id,
            context_ref=body.context_ref,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    run = read_run_meta(folder)
    return {
        "ok": True,
        "item": item,
        **public_inbox_payload(run),
    }


@router.post("/sessions/{session_id}/inbox/{item_id}/resolve")
def resolve_session_inbox_item(
    session_id: str,
    item_id: str,
    body: HumanInboxResolveRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    status = body.status or "resolved"
    try:
        item = resolve_inbox_item(
            folder,
            item_id,
            status=status,  # type: ignore[arg-type]
            selected=body.selected,
            decision=body.decision,
            note=body.note,
            append_chat=body.append_chat,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    run = read_run_meta(folder)
    from agent_lab.human_inbox import format_human_decision

    return {
        "ok": True,
        "item": item,
        "human_decision": format_human_decision(item),
        **public_inbox_payload(run),
    }


@router.post("/sessions/{session_id}/inbox/supersede")
def supersede_session_inbox(
    session_id: str,
    human_turn_id: int | None = None,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    count = supersede_pending_inbox(folder, human_turn_id=human_turn_id)
    run = read_run_meta(folder)
    return {
        "ok": True,
        "superseded_count": count,
        **public_inbox_payload(run),
    }
