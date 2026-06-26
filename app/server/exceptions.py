"""Shared FastAPI exception handlers for plan/execute gate errors."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from agent_lab.plan_execute_worktree import WorktreeUnavailable
from agent_lab.plan_pending import PlanSnapshotRequired
from agent_lab.room_hooks import PreExecuteBlocked
from agent_lab.room_objections import ObjectionBlocksExecute


def _notify_execute_gate_blocked(folder, *, source: str) -> None:
    try:
        from agent_lab.gateway.notify_helpers import notify_gate_blocked
        from agent_lab.runtime.policy import PolicyEngine
        from agent_lab.run_meta import read_run_meta

        snap = PolicyEngine.gate_snapshot(read_run_meta(folder))
        notify_gate_blocked(folder, snap, source=source)
    except Exception:
        pass


def _session_folder_from_request(request: Request):
    session_id = request.path_params.get("session_id")
    if not session_id:
        return None
    from app.server.deps import session_folder_or_404

    return session_folder_or_404(str(session_id))


async def handle_worktree_unavailable(_request: Request, exc: WorktreeUnavailable) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "detail": {
                "code": exc.reason,
                "message": str(exc),
                "execution_id": exc.execution_id,
                "remediation": ["fix_git_worktree_and_retry"],
            }
        },
    )


async def handle_plan_snapshot_required(_request: Request, exc: PlanSnapshotRequired) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "detail": {
                "code": "plan_snapshot_required",
                "message": "plan 스냅샷 승인 후 dry-run 할 수 있습니다.",
                "pending_plan": exc.pending_plan,
            }
        },
    )


async def handle_objection_blocks_execute(request: Request, exc: ObjectionBlocksExecute) -> JSONResponse:
    folder = _session_folder_from_request(request)
    if folder is not None:
        _notify_execute_gate_blocked(folder, source="execute_api_objection")
    return JSONResponse(
        status_code=409,
        content={
            "detail": {
                "code": "open_objection",
                "message": str(exc),
                "objections": exc.objections,
            }
        },
    )


async def handle_pre_execute_blocked(request: Request, exc: PreExecuteBlocked) -> JSONResponse:
    folder = _session_folder_from_request(request)
    if folder is not None:
        _notify_execute_gate_blocked(folder, source="execute_api_pre_verify")
    return JSONResponse(
        status_code=409,
        content={
            "detail": {
                "code": "pre_execute_blocked",
                "message": str(exc),
                "pre_verify": exc.pre_verify,
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(WorktreeUnavailable, handle_worktree_unavailable)
    app.add_exception_handler(PlanSnapshotRequired, handle_plan_snapshot_required)
    app.add_exception_handler(ObjectionBlocksExecute, handle_objection_blocks_execute)
    app.add_exception_handler(PreExecuteBlocked, handle_pre_execute_blocked)
