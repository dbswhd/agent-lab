"""Files tab API — read-only workspace browse + attachments-only writes."""

from __future__ import annotations

import mimetypes
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agent_lab.attachments import MAX_FILE_BYTES
from agent_lab.workspace.files import (
    PathNotAllowed,
    RootNotFound,
    WriteNotAllowed,
    list_dir,
    list_roots,
    read_file,
    resolve_readable_file,
    write_session_file,
)

from app.server.deps import session_folder_or_404

router = APIRouter(prefix="/api")


class WriteFileRequest(BaseModel):
    root_id: str
    path: str
    content: str


@router.get("/sessions/{session_id}/files/roots")
def files_roots(session_id: str) -> dict[str, Any]:
    session_folder_or_404(session_id)
    try:
        return list_roots(session_id)
    except RootNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/files")
def files_list(session_id: str, root_id: str, path: str = "") -> dict[str, Any]:
    session_folder_or_404(session_id)
    try:
        return list_dir(session_id, root_id, path)
    except RootNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PathNotAllowed as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/files/content")
def files_content(session_id: str, root_id: str, path: str) -> dict[str, Any]:
    session_folder_or_404(session_id)
    try:
        return read_file(session_id, root_id, path)
    except RootNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PathNotAllowed as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/files/raw")
def files_raw(session_id: str, root_id: str, path: str) -> FileResponse:
    """Serve a file's raw bytes (for inline image/HTML preview)."""
    session_folder_or_404(session_id)
    try:
        target = resolve_readable_file(session_id, root_id, path)
    except RootNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PathNotAllowed as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if target.stat().st_size > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="file too large to preview")
    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(str(target), media_type=media_type, filename=target.name)


@router.put("/sessions/{session_id}/files/content")
def files_write(session_id: str, body: WriteFileRequest) -> dict[str, Any]:
    session_folder_or_404(session_id)
    try:
        return write_session_file(session_id, body.root_id, body.path, body.content)
    except RootNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PathNotAllowed as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except WriteNotAllowed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
