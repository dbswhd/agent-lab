from __future__ import annotations

import json
from typing import Any

from agent_lab.run_meta import write_run_meta

from fastapi import APIRouter, HTTPException

from app.server.deps import (
    AgentCapabilitiesPatchRequest,
    ObjectionResolveRequest,
    TeamLeadRequest,
    room_session_context,
    session_folder_or_404,
)

router = APIRouter(prefix="/api")


@router.post("/sessions/{session_id}/objections/{objection_id}/resolve")
def resolve_session_objection(
    session_id: str,
    objection_id: str,
    body: ObjectionResolveRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.room_objections import resolve_objection
    from agent_lab.room_tasks import tasks_public_payload

    _plan_md, run_meta = room_session_context(folder)
    try:
        row = resolve_objection(
            run_meta,
            objection_id,
            verdict=body.verdict,
            note=body.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    write_run_meta(folder, run_meta)
    return {"ok": True, "objection": row, **tasks_public_payload(run_meta)}


@router.get("/sessions/{session_id}/agent-capabilities")
def get_session_agent_capabilities(
    session_id: str,
    permissions: str | None = None,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    _plan_md, run_meta = room_session_context(folder)
    perm_obj: dict[str, Any] = {}
    if permissions:
        try:
            perm_obj = json.loads(permissions)
        except json.JSONDecodeError:
            perm_obj = {}
    from agent_lab.room_agent_capabilities import capabilities_public_payload

    return {"ok": True, **capabilities_public_payload(run_meta, perm_obj)}


@router.patch("/sessions/{session_id}/agent-capabilities")
def patch_session_agent_capabilities(
    session_id: str,
    body: AgentCapabilitiesPatchRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.room_agent_capabilities import (
        capabilities_public_payload,
        write_agent_capabilities,
    )

    _plan_md, run_meta = room_session_context(folder)
    caps_in = body.capabilities if isinstance(body.capabilities, dict) else {}
    write_agent_capabilities(run_meta, caps_in, mark_custom=True)
    write_run_meta(folder, run_meta)
    return {"ok": True, **capabilities_public_payload(run_meta)}


@router.patch("/sessions/{session_id}/team-lead")
def set_session_team_lead(
    session_id: str,
    body: TeamLeadRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.room_tasks import set_team_lead_agent, tasks_public_payload

    _plan_md, run_meta = room_session_context(folder)
    lead = set_team_lead_agent(run_meta, body.agent.strip().lower())
    write_run_meta(folder, run_meta)
    return {"ok": True, "team_lead": lead, **tasks_public_payload(run_meta)}
