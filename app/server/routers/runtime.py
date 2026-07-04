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


@router.get("/sessions/{session_id}/autonomy")
def get_session_autonomy(session_id: str) -> dict[str, Any]:
    """N4: autonomy ladder payload (subset of runtime snapshot)."""
    folder = session_folder_or_404(session_id)
    from agent_lab.autonomy_ladder import public_autonomy_payload
    from agent_lab.run.meta import read_run_meta

    payload = public_autonomy_payload(read_run_meta(folder))
    return {"ok": True, "session_id": session_id, "autonomy": payload}


@router.patch("/sessions/{session_id}/autonomy")
def patch_session_autonomy(session_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """N4 v2: Human-set autonomy ceiling (stored level + audit transition)."""
    from agent_lab.autonomy_ladder import record_autonomy_transition

    folder = session_folder_or_404(session_id)
    level = str(body.get("level") or "").strip().upper()
    if level not in ("L0", "L1", "L2", "L3"):
        raise HTTPException(status_code=422, detail="level must be L0|L1|L2|L3")
    reason = str(body.get("reason") or "human_level_change").strip() or "human_level_change"
    payload = record_autonomy_transition(
        folder,
        to_level=level,  # type: ignore[arg-type]
        reason=reason[:500],
        trigger="human",
    )
    return {"ok": True, "session_id": session_id, "autonomy": payload}
