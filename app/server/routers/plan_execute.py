from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from agent_lab.plan.execute import (
    abort_merge_execution,
    confirm_merge_execution,
    list_plan_actions,
    reverify_merged_execution,
    revise_pending_execution,
    resolve_execution,
    run_dry_run,
    run_isolation_override,
)
from agent_lab.plan.pending import (
    approve_pending_plan,
    pending_plans_public_payload,
    reject_pending_plan,
)

from app.server.deps import (
    ClarifierAnswersRequest,
    ExternalHandoffRequest,
    PlanExecuteDryRunRequest,
    PlanExecuteIsolationOverrideRequest,
    PlanExecuteMergeRequest,
    PlanExecuteReverifyRequest,
    PlanExecuteReviseRequest,
    PlanExecuteResolveRequest,
    room_session_context,
    session_folder_or_404,
)

router = APIRouter(prefix="/api")


@router.get("/sessions/{session_id}/evidence")
def session_evidence(
    session_id: str,
    limit: int = 50,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.evidence_ledger import public_evidence_payload

    payload = public_evidence_payload(folder, limit=min(max(limit, 1), 200))
    return {"ok": True, "session_id": session_id, **payload}


@router.get("/sessions/{session_id}/wisdom-search")
def session_wisdom_search(
    session_id: str,
    q: str = "",
    limit: int = 20,
    cross_session: bool = False,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.wisdom.index import public_wisdom_search_payload

    return {
        "ok": True,
        "session_id": session_id,
        **public_wisdom_search_payload(
            folder,
            query=q,
            limit=min(max(limit, 1), 50),
            cross_session=cross_session,
        ),
    }


@router.post("/sessions/{session_id}/wisdom-index/rebuild")
def session_wisdom_index_rebuild(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.wisdom.index import build_wisdom_index, public_wisdom_index_status, wisdom_index_enabled

    if not wisdom_index_enabled():
        raise HTTPException(
            status_code=409,
            detail="wisdom index disabled — set AGENT_LAB_WISDOM_INDEX=1",
        )
    build_wisdom_index(folder, force=True)
    return {
        "ok": True,
        "session_id": session_id,
        "index": public_wisdom_index_status(folder),
    }


@router.post("/sessions/{session_id}/clarifier-interview/answers")
def session_clarifier_answers(
    session_id: str,
    body: ClarifierAnswersRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.session.clarifier import public_clarifier_interview, record_clarifier_answers

    if not body.answers:
        raise HTTPException(status_code=400, detail="answers required")
    from agent_lab.run.meta import read_run_meta

    interview = record_clarifier_answers(
        folder,
        answers=body.answers,
        mark_complete=body.mark_complete,
    )
    # Auto-advance CLARIFY→DRAFT when the interview is now complete, so the user doesn't
    # need to send an extra chat turn after submitting answers.
    updated = interview or public_clarifier_interview(read_run_meta(folder))
    if updated and updated.get("status") == "complete":
        from agent_lab.plan.workflow import tick_plan_workflow_after_inbox_resolve

        tick_plan_workflow_after_inbox_resolve(folder)
    return {
        "ok": True,
        "session_id": session_id,
        "interview": updated,
        "plan_workflow": read_run_meta(folder).get("plan_workflow"),
    }


@router.get("/sessions/{session_id}/clarifier-interview")
def session_clarifier_interview(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.run.meta import read_run_meta
    from agent_lab.session.clarifier import public_clarifier_interview

    run = read_run_meta(folder)
    interview = public_clarifier_interview(run)
    return {
        "ok": True,
        "session_id": session_id,
        "interview": interview,
        "enabled": interview is not None,
    }


@router.get("/sessions/{session_id}/merge-checks")
def session_merge_checks(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.merge_checks import public_merge_checks_payload
    from agent_lab.run.meta import read_run_meta

    return {
        "ok": True,
        "session_id": session_id,
        **public_merge_checks_payload(read_run_meta(folder), folder=folder),
    }


@router.get("/sessions/{session_id}/trust-budget")
def session_trust_budget(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.run.meta import read_run_meta
    from agent_lab.trust_budget import get_trust_budget

    run = read_run_meta(folder)
    return {
        "ok": True,
        "session_id": session_id,
        "trust_budget": get_trust_budget(run),
    }


@router.patch("/sessions/{session_id}/trust-budget")
def patch_session_trust_budget(session_id: str, body: dict[str, Any]) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.trust_budget import set_trust_budget

    allowed = {"auto_merge_remaining", "auto_merge_total", "classifier_allow"}
    patch = {k: v for k, v in body.items() if k in allowed}
    if not patch:
        raise HTTPException(status_code=422, detail="trust_budget patch required")
    budget = set_trust_budget(folder, patch)
    return {"ok": True, "session_id": session_id, "trust_budget": budget}


@router.get("/sessions/{session_id}/auto-merge/eligibility")
def session_auto_merge_eligibility(
    session_id: str,
    execution_id: str | None = None,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.auto_approve_gate import try_auto_approve
    from agent_lab.auto_merge import evaluate_auto_merge_eligibility

    if execution_id:
        try_auto_approve(folder, execution_id.strip())

    payload = evaluate_auto_merge_eligibility(folder, execution_id=execution_id)
    return {"ok": True, "session_id": session_id, **payload}


@router.post("/sessions/{session_id}/auto-merge")
def session_auto_merge(
    session_id: str,
    body: PlanExecuteMergeRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.auto_merge import resolve_auto_merge

    try:
        result = resolve_auto_merge(folder, execution_id=body.execution_id.strip())
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"ok": True, "session_id": session_id, **result}


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


@router.post("/sessions/{session_id}/execute/pending-plans/{pending_id}/revise")
def session_revise_pending_execution(
    session_id: str,
    pending_id: str,
    body: PlanExecuteReviseRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    try:
        result = revise_pending_execution(
            folder,
            execution_id=pending_id,
            comment=body.comment,
            chunk_ref=body.chunk_ref,
            line_start=body.line_start,
            line_end=body.line_end,
            permissions=body.permissions,
            executor=body.executor,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"ok": True, **result}


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
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
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


@router.post("/sessions/{session_id}/executions/{execution_id}/external-handoff")
def session_external_handoff(
    session_id: str,
    execution_id: str,
    body: ExternalHandoffRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.external_handoff import attach_external_handoff

    try:
        execution = attach_external_handoff(
            folder,
            execution_id=execution_id.strip(),
            payload=body.model_dump(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "ok": True,
        "session_id": session_id,
        "execution_id": execution_id,
        "execution": execution,
    }


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
            permissions=body.permissions,
            executor=body.executor,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"ok": True, **result}
