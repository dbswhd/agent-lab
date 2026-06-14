from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent_lab.background_tasks import get_manager, load_persisted_tasks
from app.server.deps import session_folder_or_404

router = APIRouter(prefix="/api")


class SubmitBody(BaseModel):
    label: str
    command: list[str]
    cwd: str | None = None


@router.post("/sessions/{session_id}/bg-tasks")
def submit_task(session_id: str, body: SubmitBody) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    if not body.command:
        raise HTTPException(status_code=422, detail="command must not be empty")
    mgr = get_manager()
    _ensure_session_loaded(session_id, mgr, folder)
    task = mgr.submit(folder, body.label, body.command, body.cwd)
    return task.to_dict()


@router.get("/sessions/{session_id}/bg-tasks")
def list_tasks(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    mgr = get_manager()
    _ensure_session_loaded(session_id, mgr, folder)
    tasks = mgr.list_for_session(session_id)
    return {"tasks": [t.to_dict() for t in tasks]}


@router.get("/sessions/{session_id}/bg-tasks/{task_id}")
def get_task(session_id: str, task_id: str) -> dict[str, Any]:
    session_folder_or_404(session_id)
    mgr = get_manager()
    task = mgr.get(task_id)
    if task is None or task.session_id != session_id:
        raise HTTPException(status_code=404, detail="task not found")
    return task.to_dict()


@router.get("/sessions/{session_id}/bg-tasks/{task_id}/log")
def get_task_log(
    session_id: str, task_id: str, offset: int = 0
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    mgr = get_manager()
    task = mgr.get(task_id)
    if task is None or task.session_id != session_id:
        raise HTTPException(status_code=404, detail="task not found")
    lines = mgr.read_log(folder, task_id, offset=offset)
    return {"task_id": task_id, "offset": offset, "lines": lines}


@router.delete("/sessions/{session_id}/bg-tasks/{task_id}")
def cancel_task(session_id: str, task_id: str) -> dict[str, Any]:
    session_folder_or_404(session_id)
    mgr = get_manager()
    task = mgr.get(task_id)
    if task is None or task.session_id != session_id:
        raise HTTPException(status_code=404, detail="task not found")
    cancelled = mgr.cancel(task_id)
    task = mgr.get(task_id)
    return {"cancelled": cancelled, "task": task.to_dict() if task else None}


# ── session load-once ─────────────────────────────────────────────────────────

_loaded_sessions: set[str] = set()
_loaded_lock = __import__("threading").Lock()


def _ensure_session_loaded(
    session_id: str, mgr: Any, folder: Any
) -> None:
    with _loaded_lock:
        if session_id not in _loaded_sessions:
            load_persisted_tasks(folder, mgr)
            _loaded_sessions.add(session_id)
