from __future__ import annotations

import shutil
from typing import Any, Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from agent_lab.attachments import list_attachment_names
from agent_lab.goal_loop import check_session_goal, goal_loop_enabled, set_session_goal
from agent_lab.response_contracts import (
    response_contract_presets,
    set_response_contract,
)

from app.server.deps import (
    RenameSessionRequest,
    SessionGoalPatchRequest,
    archive_meta,
    list_sessions,
    read_meta,
    save_uploads,
    session_detail,
    session_folder_or_404,
    write_meta,
)

router = APIRouter(prefix="/api")


class ResponseContractPatchRequest(BaseModel):
    preset: Literal[
        "concise",
        "evidence_first",
        "plan_ready",
        "review_only",
        "build_handoff",
    ]


@router.get("/sessions")
def sessions(
    archived: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, Any]:
    items, total = list_sessions(archived=archived, limit=limit, offset=offset)
    return {"ok": True, "sessions": items, "total": total}


@router.post("/sessions/{session_id}/archive")
def archive_session(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    archive_meta(folder)
    return {"ok": True, "id": session_id, "archived": True}


@router.post("/sessions/{session_id}/unarchive")
def unarchive_session(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    meta = read_meta(folder)
    meta["archived"] = False
    meta.pop("archived_at", None)
    write_meta(folder, meta)
    return {"ok": True, "id": session_id, "archived": False}


class ForkSessionRequest(BaseModel):
    copy_plan: bool = True
    chat_tail: int = 80


@router.post("/sessions/{session_id}/fork")
def fork_session_endpoint(
    session_id: str,
    body: ForkSessionRequest | None = None,
) -> dict[str, Any]:
    """Fork session into a new id. Does not copy pending gates/executions."""
    folder = session_folder_or_404(session_id)
    from agent_lab.session.fork import fork_session

    opts = body or ForkSessionRequest()
    try:
        result = fork_session(
            folder,
            copy_plan=opts.copy_plan,
            chat_tail=opts.chat_tail,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.get("/sessions/{session_id}")
def session(
    session_id: str,
    chat_limit: int | None = None,
    chat_offset: int = 0,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.room import ensure_session_plan_pipeline

    ensure_session_plan_pipeline(folder)
    return session_detail(session_id, chat_limit=chat_limit, chat_offset=chat_offset)


@router.post("/sessions/{session_id}/plan/auto-sync")
def auto_sync_session_plan(
    session_id: str,
    chat_limit: int | None = None,
    chat_offset: int = 0,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.room import ensure_session_plan_pipeline

    synced = ensure_session_plan_pipeline(folder)
    detail = session_detail(session_id, chat_limit=chat_limit, chat_offset=chat_offset)
    return {**detail, "ok": True, "synced": synced}


@router.patch("/sessions/{session_id}")
def rename_session(session_id: str, body: RenameSessionRequest) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    topic = body.topic.strip()
    (folder / "topic.txt").write_text(topic + "\n", encoding="utf-8")
    meta = read_meta(folder)
    meta["topic"] = topic
    write_meta(folder, meta)
    return {"ok": True, "id": session_id, "topic": topic}


@router.patch("/sessions/{session_id}/response-contract")
def patch_session_response_contract(
    session_id: str,
    body: ResponseContractPatchRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    contract = set_response_contract(folder, body.preset)
    return {
        "ok": True,
        "response_contract": contract,
        "presets": response_contract_presets(),
    }


@router.patch("/sessions/{session_id}/goal")
def patch_session_goal(
    session_id: str,
    body: SessionGoalPatchRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.ideation import IdeationError
    from agent_lab.plan.workflow import is_plan_workflow_active
    from agent_lab.run.meta import read_run_meta

    if is_plan_workflow_active(read_run_meta(folder)):
        raise HTTPException(
            status_code=409,
            detail="manual goal patch disabled during plan workflow; approve plan.md instead",
        )
    try:
        result = set_session_goal(folder, body.text, max_checks=body.max_checks)
    except IdeationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, **result}


@router.post("/sessions/{session_id}/goal/check")
def post_session_goal_check(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    if not goal_loop_enabled():
        raise HTTPException(status_code=409, detail="goal loop is disabled")
    result = check_session_goal(folder)
    if not result.get("checked") and result.get("reason") in {
        "goal_missing",
        "goal_loop_disabled",
    }:
        raise HTTPException(status_code=409, detail=result["reason"])
    return {"ok": True, **result}


# --- idea lane (RI-07) ---------------------------------------------------
#
# Selecting, combining, or rejecting a candidate is the user deciding what to
# build. None of it approves execution: `plan/approve`, the template fast-path,
# and a direct execute call all stay refused for this lane (RI-04), and these
# endpoints never call them.


class IdeationPatchRequest(BaseModel):
    command: Literal["select", "combine", "reject", "reset"]
    option_id: str = ""
    parent_ids: list[str] = Field(default_factory=list)
    new_id: str = ""
    title: str = ""
    reason: str = ""
    expected_revision: int | None = None
    request_id: str | None = None


def _ideation_state_or_404(folder) -> dict[str, Any]:
    from agent_lab.ideation import read_ideation
    from agent_lab.run.meta import read_run_meta

    state = read_ideation(read_run_meta(folder))
    if state is None:
        raise HTTPException(status_code=404, detail="session has no ideation state")
    return state


def _ideation_payload(state: dict[str, Any], **extra: Any) -> dict[str, Any]:
    from agent_lab.ideation import plan_is_stale

    return {
        "ok": True,
        "ideation": state,
        "revision": state.get("revision"),
        "stage": state.get("stage"),
        "plan_stale": plan_is_stale(state),
        **extra,
    }


@router.get("/sessions/{session_id}/ideation")
def get_session_ideation(session_id: str) -> dict[str, Any]:
    """Read idea state. Deliberately does not run the plan pipeline.

    `GET /api/sessions/{id}` calls `ensure_session_plan_pipeline`; this one must
    not, so reading or refreshing an idea session writes nothing at all.
    """
    folder = session_folder_or_404(session_id)
    return _ideation_payload(_ideation_state_or_404(folder))


@router.patch("/sessions/{session_id}/ideation")
def patch_session_ideation(
    session_id: str,
    body: IdeationPatchRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    from agent_lab.ideation import (
        IdeationCommandError,
        IdeationError,
        IdeationStaleError,
        apply_ideation_command,
        read_ideation,
    )
    from agent_lab.run.meta import patch_run_meta
    from agent_lab.run.control import run_lock_status

    _ideation_state_or_404(folder)

    # A room turn holds the authoritative run_meta in memory and replays it at
    # turn end, so a write landing now would be silently overwritten. Refuse
    # instead of losing the newer state.
    lock = run_lock_status()
    if lock.get("locked") and str(lock.get("session_id") or "") == session_id:
        raise HTTPException(
            status_code=409,
            detail={"message": "session is running a room turn; retry after it finishes", "code": "busy"},
        )

    outcome: dict[str, Any] = {}

    def _apply(run: dict[str, Any]) -> dict[str, Any]:
        outcome.update(
            apply_ideation_command(
                run,
                command=body.command,
                option_id=body.option_id,
                parent_ids=body.parent_ids,
                new_id=body.new_id,
                title=body.title,
                reason=body.reason,
                expected_revision=body.expected_revision,
                request_id=body.request_id,
            )
        )
        return run

    try:
        updated = patch_run_meta(folder, _apply)
    except IdeationStaleError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "code": "stale_revision",
                "expected_revision": exc.expected,
                "current_revision": exc.actual,
            },
        ) from exc
    except IdeationCommandError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IdeationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    state = read_ideation(updated) or outcome["state"]
    return _ideation_payload(
        state,
        applied=bool(outcome.get("applied")),
        idempotent=bool(outcome.get("idempotent")),
    )


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    shutil.rmtree(folder)
    return {"ok": True, "id": session_id}


@router.post("/sessions/{session_id}/attachments")
async def upload_attachments(
    session_id: str,
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    saved = await save_uploads(folder, files)
    return {"ok": True, "saved": saved, "attachments": list_attachment_names(folder)}
