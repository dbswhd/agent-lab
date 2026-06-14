from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent_lab.dev_preview import (
    DevPreviewError,
    auto_probe_dev_port,
    clear_dev_server_port,
    dev_server_bg_presets,
    get_dev_server_port,
    is_port_listening,
    probe_listening_ports,
    resolve_session_workspace_cwd,
    set_dev_server_port,
)
from app.server.deps import session_folder_or_404

router = APIRouter(prefix="/api")


class SetPortBody(BaseModel):
    port: int


@router.get("/sessions/{session_id}/preview/status")
def preview_status(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    port = get_dev_server_port(folder)
    alive = is_port_listening(port) if port is not None else False
    return {"port": port, "alive": alive}


@router.put("/sessions/{session_id}/preview/port")
def preview_set_port(session_id: str, body: SetPortBody) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    try:
        set_dev_server_port(folder, body.port)
    except DevPreviewError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    alive = is_port_listening(body.port)
    return {"port": body.port, "alive": alive}


@router.delete("/sessions/{session_id}/preview/port")
def preview_clear_port(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    clear_dev_server_port(folder)
    return {"port": None, "alive": False}


@router.post("/sessions/{session_id}/preview/probe")
def preview_probe(session_id: str) -> dict[str, Any]:
    """Scan common dev ports; persist the first listener in run.json."""
    folder = session_folder_or_404(session_id)
    probed = probe_listening_ports()
    port = auto_probe_dev_port(folder) if probed else None
    alive = is_port_listening(port) if port is not None else False
    return {"port": port, "alive": alive, "probed": probed}


@router.get("/sessions/{session_id}/preview/presets")
def preview_presets(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    cwd = resolve_session_workspace_cwd(folder)
    return {"presets": dev_server_bg_presets(cwd)}
