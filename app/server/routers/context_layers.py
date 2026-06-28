"""Context layer toggle API — Track C."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.server.deps import session_folder_or_404

router = APIRouter(prefix="/api")


class ContextLayersPatchRequest(BaseModel):
    mission_wisdom: bool | None = None
    repo_tree: bool | None = None


@router.get("/sessions/{session_id}/context-layers")
def get_session_context_layers(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.context.layers import public_context_layers_payload

    return {"session_id": session_id, **public_context_layers_payload(folder)}


@router.patch("/sessions/{session_id}/context-layers")
def patch_session_context_layers(
    session_id: str,
    body: ContextLayersPatchRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.context.layers import patch_context_layers, public_context_layers_payload

    updates = body.model_dump(exclude_none=True)
    patch_context_layers(folder, updates)
    return {"session_id": session_id, **public_context_layers_payload(folder)}
