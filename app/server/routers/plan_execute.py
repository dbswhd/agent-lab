from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from agent_lab.plan_execute import (
    abort_merge_execution,
    confirm_merge_execution,
    list_plan_actions,
    reverify_merged_execution,
    resolve_execution,
    run_dry_run,
    run_isolation_override,
)
from agent_lab.plan_execute_worktree import WorktreeUnavailable
from agent_lab.plan_pending import (
    PlanSnapshotRequired,
    approve_pending_plan,
    pending_plans_public_payload,
    reject_pending_plan,
)
from agent_lab.room_hooks import PreExecuteBlocked
from agent_lab.room_objections import ObjectionBlocksExecute

from app.server.deps import (
    PlanExecuteDryRunRequest,
    PlanExecuteIsolationOverrideRequest,
    PlanExecuteMergeRequest,
    PlanExecuteReverifyRequest,
    PlanExecuteResolveRequest,
    room_session_context,
    session_folder_or_404,
)

router = APIRouter(prefix="/api")


@router.get("/sessions/{session_id}/plan-actions")
def session_plan_actions(
    session_id: str,
    permissions: str | None = None,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    perms: dict[str, Any] = {}
    if permissions:
        try:
            perms = json.loads(permissions)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail="invalid permissions JSON") from e
    return list_plan_actions(folder, permissions=perms)


@router.get("/sessions/{session_id}/execute/pending-plans")
def session_pending_plans(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    _plan_md, run_meta = room_session_context(folder)
    return {"ok": True, **pending_plans_public_payload(run_meta)}


@router.post("/sessions/{session_id}/execute/pending-plans/{pending_id}/approve")
def session_approve_pending_plan(
    session_id: str,
    pending_id: str,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    try:
        row = approve_pending_plan(folder, pending_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    _plan_md, run_meta = room_session_context(folder)
    return {
        "ok": True,
        "pending_plan": row,
        **pending_plans_public_payload(run_meta),
    }


@router.post("/sessions/{session_id}/execute/pending-plans/{pending_id}/reject")
def session_reject_pending_plan(
    session_id: str,
    pending_id: str,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    try:
        row = reject_pending_plan(folder, pending_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    _plan_md, run_meta = room_session_context(folder)
    return {
        "ok": True,
        "pending_plan": row,
        **pending_plans_public_payload(run_meta),
    }


@router.post("/sessions/{session_id}/execute/dry-run")
def session_execute_dry_run(
    session_id: str,
    body: PlanExecuteDryRunRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    try:
        execution = run_dry_run(
            folder,
            action_index=body.action_index,
            action_kind=body.action_kind,
            permissions=body.permissions,
        )
    except PlanSnapshotRequired as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "plan_snapshot_required",
                "message": "plan 스냅샷 승인 후 dry-run 할 수 있습니다.",
                "pending_plan": e.pending_plan,
            },
        ) from e
    except WorktreeUnavailable as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": e.reason,
                "message": str(e),
                "execution_id": e.execution_id,
                "remediation": ["fix_git_worktree_and_retry"],
            },
        ) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ObjectionBlocksExecute as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "open_objection",
                "message": str(e),
                "objections": e.objections,
            },
        ) from e
    except PreExecuteBlocked as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "pre_execute_blocked",
                "message": str(e),
                "pre_verify": e.pre_verify,
            },
        ) from e
    return {"ok": True, "execution": execution}


@router.post("/sessions/{session_id}/execute/isolation/override")
def session_execute_isolation_override(
    session_id: str,
    body: PlanExecuteIsolationOverrideRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    try:
        execution = run_isolation_override(
            folder,
            execution_id=body.execution_id.strip(),
            mode=body.mode,
            confirmation=body.confirmation,
            permissions=body.permissions,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"ok": True, "execution": execution}


@router.post("/sessions/{session_id}/execute/resolve")
def session_execute_resolve(
    session_id: str,
    body: PlanExecuteResolveRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    try:
        result = resolve_execution(
            folder,
            execution_id=body.execution_id.strip(),
            vote=body.vote,
            permissions=body.permissions,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, **result}


@router.post("/sessions/{session_id}/execute/merge/abort")
def session_execute_merge_abort(
    session_id: str,
    body: PlanExecuteMergeRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    try:
        result = abort_merge_execution(
            folder,
            execution_id=body.execution_id.strip(),
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"ok": True, **result}


@router.post("/sessions/{session_id}/execute/merge/confirm")
def session_execute_merge_confirm(
    session_id: str,
    body: PlanExecuteMergeRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    try:
        result = confirm_merge_execution(
            folder,
            execution_id=body.execution_id.strip(),
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"ok": True, **result}


@router.post("/sessions/{session_id}/execute/reverify")
def session_execute_reverify(
    session_id: str,
    body: PlanExecuteReverifyRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    try:
        result = reverify_merged_execution(
            folder,
            execution_id=body.execution_id.strip(),
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"ok": True, **result}
