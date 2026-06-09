"""Unified runtime snapshot API — H1 read path."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.server.deps import session_folder_or_404

router = APIRouter(prefix="/api")


@router.get("/sessions/{session_id}/runtime")
def get_session_runtime(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.runtime.snapshot import public_runtime_payload

    plan_path = folder / "plan.md"
    plan_md = None
    if plan_path.is_file():
        try:
            plan_md = plan_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"plan.md read failed: {exc}") from exc
    return public_runtime_payload(folder, plan_md=plan_md)
