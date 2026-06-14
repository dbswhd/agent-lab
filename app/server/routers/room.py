from __future__ import annotations

import json
import queue
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent_lab.context_limits import all_limits_for_api
from agent_lab.invoke import ensure_ready
from agent_lab.room import (
    DEFAULT_AGENT_PARALLEL_ROUNDS,
    MAX_AGENT_PARALLEL_ROUNDS,
    continue_room_round,
    preview_agent_payload,
    run_room,
    synthesize_session_plan,
)
from agent_lab.run_control import (
    end_run,
    force_reset_run_lock,
    maybe_release_orphaned_run_lock,
    request_cancel,
    run_lock_status,
    try_begin_run,
)
from agent_lab.runner import provider_override, run_topic_with_progress
from agent_lab.session import SESSIONS_DIR, session_dir
from agent_lab.session_setup import merge_setup_permissions, seed_session_setup
from agent_lab.agent_thread_catalog import normalize_agent_thread_bindings

from app.server.deps import (
    ContextPreviewRequest,
    RunRequest,
    TURN_PROFILES,
    room_session_context,
    save_uploads,
    session_folder_or_404,
    sse,
)

router = APIRouter(prefix="/api")
_active_run = False


def _agents_not_ready(agent_list: list[str]) -> list[dict[str, Any]]:
    from agent_lab.agent_preflight import agents_not_ready

    return agents_not_ready(agent_list)


@router.post("/room/context-preview")
def room_context_preview(body: ContextPreviewRequest) -> dict[str, Any]:
    folder = session_folder_or_404(body.session_id)
    agent = body.agent.strip().lower()
    if agent not in ("cursor", "codex", "claude"):
        raise HTTPException(status_code=400, detail="agent must be cursor, codex, or claude")
    agent_list: list[str] | None = None
    if body.agents:
        agent_list = [a.strip().lower() for a in body.agents if str(a).strip()]
    try:
        payload, bundle = preview_agent_payload(
            folder,
            agent,  # type: ignore[arg-type]
            agents=agent_list,  # type: ignore[arg-type]
            parallel_round=body.parallel_round,
            permissions=body.permissions,
            review_mode=body.review_mode,
            efficiency_mode=body.efficiency_mode,
            slim_context=body.slim_context,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="session not found") from None
    return {
        "session_id": body.session_id,
        "agent": agent,
        "parallel_round": body.parallel_round,
        "review_mode": body.review_mode,
        "payload": payload,
        "chars": len(payload),
        "meta": bundle.meta.to_dict(),
        "limits": all_limits_for_api(),
    }


@router.post("/runs")
def create_run(body: RunRequest) -> StreamingResponse:
    global _active_run
    topic = body.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic required")

    def generate():
        global _active_run
        if not try_begin_run():
            maybe_release_orphaned_run_lock()
            if not try_begin_run():
                yield sse({"type": "error", "message": "a run is already in progress"})
                return

        _active_run = True
        events: list[dict[str, Any]] = []

        def on_step(node: str, status: str, extra: dict | None = None):
            events.append(
                {
                    "type": "step",
                    "node": node,
                    "status": status,
                    "extra": extra or {},
                }
            )

        try:
            with provider_override(body.backend):
                try:
                    ensure_ready()
                except RuntimeError as e:
                    yield sse({"type": "error", "message": str(e)})
                    return
            yield sse({"type": "start", "topic": topic, "backend": body.backend})
            state, folder = run_topic_with_progress(
                topic, on_step=on_step, backend=body.backend
            )
            for ev in events:
                yield sse(ev)
            session_id = Path(folder).name
            yield sse(
                {
                    "type": "complete",
                    "session_id": session_id,
                    "events": events,
                    "plan_preview": state["plan_md"][:500],
                }
            )
        except Exception as e:
            yield sse({"type": "error", "message": str(e), "events": events})
        finally:
            _active_run = False
            end_run()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/room/runs")
async def create_room_run(
    topic: str = Form(...),
    agents: str = Form("[]"),
    synthesize: bool | None = Form(None),
    mode: str = Form("discuss"),
    synthesize_only: bool = Form(False),
    agent_rounds: int = Form(DEFAULT_AGENT_PARALLEL_ROUNDS),
    session_id: str | None = Form(None),
    request_id: str | None = Form(None),
    permissions: str = Form("{}"),
    review_mode: bool = Form(False),
    consensus_mode: bool = Form(False),
    efficiency_mode: bool = Form(False),
    turn_profile: str = Form("discuss"),
    research_mode: bool = Form(False),
    workspace_id: str = Form("agent-lab"),
    workspace_path: str | None = Form(None),
    session_template: str = Form("general"),
    agent_capabilities: str = Form("{}"),
    agent_thread_bindings: str = Form("{}"),
    files: list[UploadFile] = File(default=[]),
) -> StreamingResponse:
    topic = topic.strip()
    mode_norm = (mode or "discuss").strip().lower()
    if mode_norm not in ("discuss", "plan"):
        raise HTTPException(status_code=400, detail="mode must be discuss or plan")
    if synthesize is None:
        synthesize = mode_norm == "plan"
    if synthesize_only and not session_id:
        raise HTTPException(
            status_code=400, detail="synthesize_only requires session_id"
        )
    if not synthesize_only and not topic:
        raise HTTPException(status_code=400, detail="topic required")

    try:
        agent_ids = json.loads(agents) if agents else []
    except json.JSONDecodeError:
        agent_ids = []
    agent_list = [a.strip().lower() for a in agent_ids if str(a).strip()] or None

    if not synthesize_only and agent_list:
        bad = _agents_not_ready(agent_list)
        if bad:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "agents not ready",
                    "agents": bad,
                },
            )

    try:
        perm_obj = json.loads(permissions) if permissions else {}
    except json.JSONDecodeError:
        perm_obj = {}

    workspace_norm = (workspace_id or "agent-lab").strip().lower()
    workspace_path_norm = (workspace_path or "").strip() or None
    template_norm = (session_template or "general").strip().lower()
    try:
        perm_obj = merge_setup_permissions(
            perm_obj,
            workspace_norm,
            workspace_path_norm,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    caps_obj: dict[str, Any] = {}
    try:
        parsed_caps = json.loads(agent_capabilities) if agent_capabilities else {}
        if isinstance(parsed_caps, dict):
            caps_obj = parsed_caps
    except json.JSONDecodeError:
        caps_obj = {}

    thread_bindings_obj: dict[str, str] = {}
    try:
        parsed_threads = json.loads(agent_thread_bindings) if agent_thread_bindings else {}
        thread_bindings_obj = normalize_agent_thread_bindings(parsed_threads)
    except json.JSONDecodeError:
        thread_bindings_obj = {}

    folder: Path | None = None
    if session_id:
        folder = SESSIONS_DIR / session_id
        if not folder.is_dir():
            raise HTTPException(status_code=404, detail="session not found")
    else:
        folder = session_dir(topic, base=SESSIONS_DIR)
        (folder / "topic.txt").write_text(topic + "\n", encoding="utf-8")
        try:
            seed_session_setup(
                folder,
                workspace_id=workspace_norm,
                session_template=template_norm,
                workspace_path=workspace_path_norm,
                topic=topic,
                agent_thread_bindings=thread_bindings_obj or None,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    if caps_obj:
        from agent_lab.room_agent_capabilities import write_agent_capabilities

        _plan_md, run_meta = room_session_context(folder)
        write_agent_capabilities(run_meta, caps_obj, mark_custom=True)
        from agent_lab.run_meta import persist_run_meta

        (folder / "run.json").write_text(
            json.dumps(persist_run_meta(run_meta), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    saved_files = await save_uploads(folder, files)
    parallel_rounds = max(1, min(agent_rounds, MAX_AGENT_PARALLEL_ROUNDS))
    # Align with UI turn profiles: discuss=1, review>=2 (non-UI callers may omit agent_rounds).
    if review_mode and not consensus_mode and parallel_rounds < 2:
        parallel_rounds = 2
    use_efficiency = bool(efficiency_mode)
    profile_norm = (turn_profile or "analyze").strip().lower()
    if profile_norm == "discuss":
        profile_norm = "analyze"
    if profile_norm not in TURN_PROFILES:
        profile_norm = "analyze"

    def generate():
        event_q: queue.SimpleQueue[dict[str, Any] | None] = queue.SimpleQueue()
        result: dict[str, Any] = {}

        def on_event(typ: str, payload: dict[str, Any]) -> None:
            event_q.put({"type": typ, **payload})

        def worker() -> None:
            if not try_begin_run():
                maybe_release_orphaned_run_lock()
                if not try_begin_run():
                    lock_msg = "a run is already in progress"
                    result["error"] = lock_msg
                    event_q.put(
                        {
                            "type": "error",
                            "message": lock_msg,
                        }
                    )
                    event_q.put(None)
                    return
            try:
                if synthesize_only and session_id:
                    plan_md, _summary = synthesize_session_plan(
                        folder,  # type: ignore[arg-type]
                        on_event=on_event,
                        permissions=perm_obj,
                        request_id=(request_id or "").strip() or None,
                    )
                    result["folder"] = folder
                    result["plan_md"] = plan_md
                elif session_id:
                    _messages, plan_md = continue_room_round(
                        folder,  # type: ignore[arg-type]
                        topic,
                        agents=agent_list,  # type: ignore[arg-type]
                        synthesize=synthesize,
                        parallel_rounds=parallel_rounds,
                        on_event=on_event,
                        permissions=perm_obj,
                        review_mode=review_mode,
                        consensus_mode=consensus_mode,
                        efficiency_mode=use_efficiency,
                        turn_profile=profile_norm,
                        research_mode=research_mode,
                    )
                    result["folder"] = folder
                    result["plan_md"] = plan_md
                else:
                    f, _messages, plan_md = run_room(
                        topic,
                        agents=agent_list,  # type: ignore[arg-type]
                        synthesize=synthesize,
                        parallel_rounds=parallel_rounds,
                        on_event=on_event,
                        session_folder=folder,
                        permissions=perm_obj,
                        review_mode=review_mode,
                        consensus_mode=consensus_mode,
                        efficiency_mode=use_efficiency,
                        turn_profile=profile_norm,
                        research_mode=research_mode,
                    )
                    result["folder"] = f
                    result["plan_md"] = plan_md
            except Exception as e:
                result["error"] = e
            finally:
                end_run()
                event_q.put(None)

        try:
            yield sse(
                {
                    "type": "start",
                    "topic": topic,
                    "session_id": folder.name if folder else None,
                    "workflow": "room.parallel",
                    "mode": mode_norm,
                    "synthesize": synthesize,
                    "synthesize_only": synthesize_only,
                    "request_id": (request_id or "").strip() or None,
                    "agent_rounds": parallel_rounds,
                    "review_mode": review_mode,
                    "consensus_mode": consensus_mode,
                    "efficiency_mode": use_efficiency,
                    "turn_profile": profile_norm,
                    "workspace_id": workspace_norm,
                    "session_template": template_norm,
                    "attachments": saved_files,
                }
            )
            threading.Thread(target=worker, daemon=True).start()
            while True:
                ev = event_q.get()
                if ev is None:
                    break
                if ev.get("type") == "complete":
                    result["complete_event"] = ev
                    continue
                yield sse(ev)
            if "error" in result:
                err = result["error"]
                yield sse({"type": "run_failed", "message": str(err)})
                yield sse({"type": "error", "message": str(err)})
                return
            if "folder" not in result:
                yield sse(
                    {
                        "type": "run_failed",
                        "message": "room run ended without result",
                    }
                )
                yield sse(
                    {
                        "type": "error",
                        "message": "room run ended without result",
                    }
                )
                return
            out_folder = result["folder"]
            plan_md = result.get("plan_md", "")
            complete = result.get("complete_event") or {}
            yield sse(
                {
                    "type": "complete",
                    "session_id": complete.get("session_id") or out_folder.name,
                    "plan_preview": plan_md[:500] if plan_md else "",
                    "status": complete.get("status") or "completed",
                    "failed_agents": complete.get("failed_agents") or [],
                    "succeeded_agents": complete.get("succeeded_agents") or [],
                    "send_receipt": complete.get("send_receipt"),
                    "turn_index": complete.get("turn_index"),
                }
            )
        except Exception as e:
            yield sse({"type": "error", "message": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/room/run-lock")
def room_run_lock() -> dict[str, Any]:
    return {"ok": True, **run_lock_status()}


class RoomRunCancelRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=120)


@router.post("/room/runs/cancel")
def cancel_room_run(body: RoomRunCancelRequest | None = None) -> dict[str, Any]:
    children_terminated = request_cancel()
    released = maybe_release_orphaned_run_lock()
    mission_pause: dict[str, Any] | None = None
    session_id = (body.session_id if body else None) or None
    if session_id:
        from app.server.deps import session_folder_or_404
        from agent_lab.mission_loop import on_global_run_cancel

        folder = session_folder_or_404(session_id)
        mission_pause = on_global_run_cancel(folder)
    return {
        "ok": True,
        "released_stale_lock": released,
        "children_terminated": children_terminated,
        "mission_pause": mission_pause,
        **run_lock_status(),
    }


@router.post("/room/runs/release-lock")
def release_room_run_lock() -> dict[str, Any]:
    released = maybe_release_orphaned_run_lock()
    status = run_lock_status()
    if status.get("locked"):
        force_reset_run_lock()
        released = True
        status = run_lock_status()
    return {"ok": True, "released": released, **status}
