"""Verified loop approval API (LazyCodex-inspired)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from app.server.deps import session_folder_or_404

router = APIRouter(prefix="/api")

_DEPRECATION = "true"


class VerifiedLoopApproveRequest(BaseModel):
    goal: str | None = Field(default=None, max_length=2000)
    completion_promise: str | None = Field(default=None, max_length=120)
    criteria: str | None = Field(default=None, max_length=2000)


class VerifiedLoopRejectRequest(BaseModel):
    note: str = Field(default="", max_length=500)


def _set_plan_successor_headers(response: Response, session_id: str, successor: str) -> None:
    response.headers["Deprecation"] = _DEPRECATION
    response.headers["Link"] = (
        f'</api/sessions/{session_id}/{successor}>; rel="successor-version"'
    )


@router.post("/sessions/{session_id}/verified-loop/approve")
def post_verified_loop_approve(
    session_id: str,
    body: VerifiedLoopApproveRequest,
    response: Response,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.plan_workflow import approve_plan, get_plan_workflow, is_plan_workflow_active
    from agent_lab.verified_loop import approve_verified_loop

    from agent_lab.run_meta import read_run_meta

    run_meta = read_run_meta(folder)
    if is_plan_workflow_active(run_meta) and get_plan_workflow(run_meta).get("phase") == "HUMAN_PENDING":
        try:
            result = approve_plan(
                folder,
                goal=body.goal,
                completion_promise=body.completion_promise,
                criteria=body.criteria,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        _set_plan_successor_headers(response, session_id, "plan/approve")
        return {
            "ok": True,
            "session_id": session_id,
            **result,
            "deprecated": "use POST /plan/approve",
        }

    try:
        result = approve_verified_loop(
            folder,
            goal=body.goal,
            completion_promise=body.completion_promise,
            criteria=body.criteria,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "session_id": session_id, **result}


@router.post("/sessions/{session_id}/verified-loop/reject")
def post_verified_loop_reject(
    session_id: str,
    body: VerifiedLoopRejectRequest,
    response: Response,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.plan_workflow import get_plan_workflow, is_plan_workflow_active, reject_plan
    from agent_lab.run_meta import read_run_meta
    from agent_lab.verified_loop import reject_verified_loop

    run_meta = read_run_meta(folder)
    if is_plan_workflow_active(run_meta) and get_plan_workflow(run_meta).get("phase") == "HUMAN_PENDING":
        pw = reject_plan(folder, note=body.note, target_phase="CLARIFY")
        run = read_run_meta(folder)
        _set_plan_successor_headers(response, session_id, "plan/reject")
        return {
            "ok": True,
            "session_id": session_id,
            "plan_workflow": pw,
            "verified_loop": run.get("verified_loop"),
            "deprecated": "use POST /plan/reject",
        }

    loop = reject_verified_loop(folder, note=body.note)
    return {"ok": True, "session_id": session_id, "verified_loop": loop}
