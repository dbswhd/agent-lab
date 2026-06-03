from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from app.server.deps import (
    TaskClaimRequest,
    TaskCompleteRequest,
    room_session_context,
    session_folder_or_404,
)

router = APIRouter(prefix="/api")


@router.get("/sessions/{session_id}/tasks")
def session_tasks(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    _plan_md, run_meta = room_session_context(folder)
    from agent_lab.room_tasks import tasks_public_payload

    return tasks_public_payload(run_meta)


@router.post("/sessions/{session_id}/tasks/{task_id}/claim")
def claim_session_task(
    session_id: str,
    task_id: str,
    body: TaskClaimRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.room_tasks import claim_task, tasks_public_payload

    _plan_md, run_meta = room_session_context(folder)
    try:
        task = claim_task(run_meta, task_id, body.agent.strip().lower())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    (folder / "run.json").write_text(
        json.dumps(run_meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {"ok": True, "task": task, **tasks_public_payload(run_meta)}


@router.post("/sessions/{session_id}/tasks/{task_id}/complete")
def complete_session_task(
    session_id: str,
    task_id: str,
    body: TaskCompleteRequest | None = None,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.room_tasks import complete_task, tasks_public_payload

    _plan_md, run_meta = room_session_context(folder)
    run_meta["_session_folder"] = str(folder.resolve())
    run_meta["_session_id"] = session_id
    refs = list((body.artifact_refs if body else None) or [])
    try:
        task = complete_task(run_meta, task_id, artifact_refs=refs or None)
    except ValueError as e:
        msg = str(e)
        status = 409 if "승인" in msg or "검증" in msg or "실행" in msg else 400
        raise HTTPException(status_code=status, detail=msg) from e
    from agent_lab.run_meta import persist_run_meta

    (folder / "run.json").write_text(
        json.dumps(persist_run_meta(run_meta), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {"ok": True, "task": task, **tasks_public_payload(run_meta)}
