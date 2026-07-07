from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent_lab.agents.registry import AGENT_IDS
from agent_lab.context.limits import all_limits_for_api
from agent_lab.invoke import ensure_ready
from agent_lab.model_policy import partition_loop_capable_agents
from agent_lab.room import (
    DEFAULT_AGENT_PARALLEL_ROUNDS,
    MAX_AGENT_PARALLEL_ROUNDS,
    continue_room_round,
    preview_agent_payload,
    run_room,
    synthesize_session_plan,
)
from agent_lab.run.control import (
    end_run,
    force_reset_run_lock,
    is_cancelled,
    maybe_release_orphaned_run_lock,
    request_cancel,
    reset_run_session_id,
    run_lock_recovery_hint,
    run_lock_status,
    set_run_session_id,
    try_begin_run,
)
from agent_lab.runner import provider_override, run_topic_with_progress
from agent_lab.session import session_dir
from agent_lab.session.paths import active_sessions_dir
from agent_lab.session.setup import merge_setup_permissions, seed_session_setup
from agent_lab.agent.thread_catalog import normalize_agent_thread_bindings
from agent_lab.turn_modes import (
    ModeContractError,
    mode_contract_catalog,
    patch_run_mode_contract,
    resolve_mode_contract,
)
from agent_lab.room.preset import (
    preset_catalog,
    preset_role_policy,
    preset_turn_profile,
    resolve_preset,
)

from app.server.deps import (
    ContextPreviewRequest,
    RunRequest,
    room_session_context,
    save_uploads,
    session_folder_or_404,
    sse,
)

router = APIRouter(prefix="/api")

_ROOM_SSE_KEEPALIVE_SEC = 25.0


def _room_run_terminal_events(
    result: dict[str, Any],
    *,
    run_session_id: str | None,
) -> list[dict[str, Any]]:
    """Terminal SSE payloads after the worker finishes (or client disconnect cleanup)."""
    if result.get("cancelled") or is_cancelled(run_session_id):
        complete = result.get("complete_event") or {}
        return [
            {"type": "run_cancelled", "message": "답변 중지됨"},
            {
                "type": "complete",
                "session_id": complete.get("session_id") or run_session_id,
                "plan_preview": "",
                "status": complete.get("status") or "partial",
                "failed_agents": complete.get("failed_agents") or [],
                "succeeded_agents": complete.get("succeeded_agents") or [],
                "send_receipt": complete.get("send_receipt"),
                "turn_index": complete.get("turn_index"),
                "cancelled": True,
            },
        ]
    if "error" in result:
        err = str(result["error"])
        return [
            {"type": "run_failed", "message": err},
            {"type": "error", "message": err},
        ]
    if "folder" not in result:
        msg = "room run ended without result"
        return [
            {"type": "run_failed", "message": msg},
            {"type": "error", "message": msg},
        ]
    out_folder = result["folder"]
    plan_md = result.get("plan_md", "")
    complete = result.get("complete_event") or {}
    return [
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
    ]


def _drain_room_event_queue(
    event_q: asyncio.Queue[dict[str, Any] | None],
    result: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    while True:
        try:
            ev = event_q.get_nowait()
        except asyncio.QueueEmpty:
            break
        if ev is None:
            break
        if ev.get("type") == "complete":
            result["complete_event"] = ev
            continue
        yield ev


def _run_with_lock(
    *,
    session_id: str | None,
    on_event: Any,
    run_body: Any,
    result: dict[str, Any],
    event_q: asyncio.Queue[dict[str, Any] | None],
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Acquire run lock, execute sync room work, release lock (single lifecycle)."""
    session_token = set_run_session_id(session_id)

    def _emit(item: dict[str, Any] | None) -> None:
        loop.call_soon_threadsafe(event_q.put_nowait, item)

    if not try_begin_run(session_id=session_id, run_kind="room"):
        maybe_release_orphaned_run_lock()
        if not try_begin_run(session_id=session_id, run_kind="room"):
            lock_msg = "a run is already in progress"
            lock_hint = run_lock_recovery_hint()
            result["error"] = lock_msg
            result["run_lock"] = lock_hint
            _emit({"type": "run_lock_blocked", **lock_hint})
            _emit({"type": "error", "message": lock_msg})
            _emit(None)
            reset_run_session_id(session_token)
            return

    try:
        run_body(on_event)
    except Exception as e:
        from agent_lab.run.control import RoomRunCancelled

        if isinstance(e, RoomRunCancelled) or is_cancelled(session_id):
            result["cancelled"] = True
        else:
            result["error"] = e
    finally:
        if is_cancelled(session_id):
            _emit({"type": "run_cancelled", "message": "답변 중지됨"})
        end_run()
        reset_run_session_id(session_token)
        _emit(None)


def _agents_not_ready(agent_list: list[str]) -> list[dict[str, Any]]:
    from agent_lab.agent.preflight import agents_not_ready

    return agents_not_ready(agent_list)


def _session_hard_cap_exhausted(folder: Path) -> bool:
    """True when AGENT_LAB_SESSION_HARD_CAP is on and the session is budget-exhausted."""
    import os

    if (os.getenv("AGENT_LAB_SESSION_HARD_CAP") or "").strip().lower() not in ("1", "true", "yes", "on"):
        return False
    from agent_lab.run.meta import read_run_meta

    return bool(read_run_meta(folder).get("budget_exhausted"))


def _session_has_pending_human_inbox(folder: Path | None) -> bool:
    """True when this session is legitimately waiting on a human_inbox answer.

    A dropped SSE connection (tab backgrounded, laptop sleep, network blip)
    must not kill the worker while it is mid-``ask_human`` — that wait has
    its own generous timeout (``DEFAULT_INBOX_TIMEOUT_SEC``) precisely so a
    human can take their time; an unconditional kill on disconnect bypassed
    that grace period entirely.
    """
    if folder is None:
        return False
    from agent_lab.run.meta import read_run_meta

    inbox = read_run_meta(folder).get("human_inbox") or []
    if not isinstance(inbox, list):
        return False
    return any(isinstance(item, dict) and item.get("status") == "pending" for item in inbox)


def _loop_readiness_detail(agent_list: list[str] | None) -> dict[str, Any] | None:
    from agent_lab.model_policy import loop_readiness_failure_detail

    effective_agents = agent_list or list(AGENT_IDS)
    detail = loop_readiness_failure_detail(effective_agents)
    if detail is None:
        return None
    return dict(detail)


@router.get("/room/modes")
def room_modes() -> dict[str, Any]:
    return mode_contract_catalog()


@router.get("/room/presets")
def room_presets() -> dict[str, Any]:

    return preset_catalog()


@router.get("/room/roles")
def room_roles() -> dict[str, Any]:
    from agent_lab.role_plan import role_catalog

    return {"roles": role_catalog()}


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
    topic = body.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic required")

    def generate():
        if not try_begin_run(run_kind="classic"):
            maybe_release_orphaned_run_lock()
            if not try_begin_run(run_kind="classic"):
                yield sse({"type": "run_lock_blocked", **run_lock_recovery_hint()})
                yield sse({"type": "error", "message": "a run is already in progress"})
                return

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
            state, folder = run_topic_with_progress(topic, on_step=on_step, backend=body.backend)
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
            end_run()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_synthesize_only(
    request: Request,
    *,
    session_id: str,
    request_id: str | None,
    permissions: str,
) -> StreamingResponse:
    """TurnPolicy Human override: Scribe-only plan refresh (no agents, no mode contract).

    Deprecated ``mode`` / ``synthesize`` form fields are ignored — ``synthesize_only`` is SSOT.
    """
    folder = active_sessions_dir() / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    try:
        perm_obj = json.loads(permissions) if permissions else {}
    except json.JSONDecodeError:
        perm_obj = {}
    if not isinstance(perm_obj, dict):
        perm_obj = {}
    req_id = (request_id or "").strip() or None
    run_session_id = folder.name

    def _cancel_on_client_disconnect() -> None:
        request_cancel(run_session_id)

    async def generate():
        event_q: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        result: dict[str, Any] = {}
        loop = asyncio.get_running_loop()

        def on_event(typ: str, payload: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(event_q.put_nowait, {"type": typ, **payload})
            from agent_lab.room.live_log import append_live_room_event

            append_live_room_event(folder, typ, payload)

        def run_body(on_event_cb: Any) -> None:
            from agent_lab.room.live_log import clear_live_room_log

            clear_live_room_log(folder)
            plan_md, _summary = synthesize_session_plan(
                folder,
                on_event=on_event_cb,
                permissions=perm_obj,
                request_id=req_id,
            )
            result["folder"] = folder
            result["plan_md"] = plan_md

        try:
            yield sse(
                {
                    "type": "start",
                    "topic": "",
                    "session_id": run_session_id,
                    "workflow": "room.synthesize_only",
                    "mode": "discuss",
                    "synthesize": False,
                    "synthesize_only": True,
                    "request_id": req_id,
                    "agent_rounds": 0,
                    "review_mode": False,
                    "consensus_mode": False,
                    "efficiency_mode": False,
                    "turn_profile": "analyze",
                    "discuss_light": False,
                }
            )
            worker = loop.run_in_executor(
                None,
                lambda: _run_with_lock(
                    session_id=run_session_id,
                    on_event=on_event,
                    run_body=run_body,
                    result=result,
                    event_q=event_q,
                    loop=loop,
                ),
            )
            last_keepalive = time.monotonic()
            while True:
                if await request.is_disconnected():
                    _cancel_on_client_disconnect()
                    try:
                        await asyncio.wait_for(worker, timeout=8.0)
                    except asyncio.TimeoutError:
                        pass
                    for ev in _drain_room_event_queue(event_q, result):
                        yield sse(ev)
                    for payload in _room_run_terminal_events(
                        result,
                        run_session_id=run_session_id,
                    ):
                        yield sse(payload)
                    return
                try:
                    ev = await asyncio.wait_for(event_q.get(), timeout=0.25)
                except asyncio.TimeoutError:
                    now = time.monotonic()
                    if now - last_keepalive >= _ROOM_SSE_KEEPALIVE_SEC:
                        last_keepalive = now
                        yield ": keepalive\n\n"
                    continue
                if ev is None:
                    break
                if ev.get("type") == "complete":
                    result["complete_event"] = ev
                    continue
                last_keepalive = time.monotonic()
                yield sse(ev)
            await worker
            for payload in _room_run_terminal_events(
                result,
                run_session_id=run_session_id,
            ):
                yield sse(payload)
        except Exception as e:
            yield sse({"type": "error", "message": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/room/runs")
async def create_room_run(
    request: Request,
    topic: str = Form(""),
    agents: str = Form("[]"),
    synthesize: bool | None = Form(None),
    mode: str = Form("discuss"),
    synthesize_only: bool = Form(False),
    skill_intent: str | None = Form(None),
    agent_rounds: int = Form(DEFAULT_AGENT_PARALLEL_ROUNDS),
    session_id: str | None = Form(None),
    request_id: str | None = Form(None),
    permissions: str = Form("{}"),
    review_mode: bool = Form(False),
    consensus_mode: bool = Form(False),
    efficiency_mode: bool = Form(False),
    turn_profile: str = Form("discuss"),
    preset: str = Form(""),
    role_policy: str = Form(""),
    research_mode: bool = Form(False),
    workspace_id: str = Form("agent-lab"),
    workspace_path: str | None = Form(None),
    session_template: str = Form("general"),
    agent_capabilities: str = Form("{}"),
    agent_thread_bindings: str = Form("{}"),
    room_models: str = Form(""),
    files: list[UploadFile] = File(default=[]),
) -> StreamingResponse:
    # TurnPolicy Human override — dedicated path; ignores mode/synthesize/agents.
    if synthesize_only:
        if not session_id:
            raise HTTPException(
                status_code=400,
                detail="synthesize_only requires session_id",
            )
        return await _stream_synthesize_only(
            request,
            session_id=session_id,
            request_id=request_id,
            permissions=permissions,
        )

    topic = topic.strip()
    mode_norm = (mode or "discuss").strip().lower()
    if mode_norm not in ("discuss", "plan"):
        raise HTTPException(status_code=400, detail="mode must be discuss or plan")
    if synthesize is None:
        synthesize = mode_norm == "plan"
    from agent_lab.room.turn_policy import turn_policy_enabled

    if turn_policy_enabled():
        synthesize = False
        mode_norm = "discuss"
    skill_intent_norm = (skill_intent or "").strip().lower() or None
    if not topic:
        raise HTTPException(status_code=400, detail="topic required")

    try:
        agent_ids = json.loads(agents) if agents else []
    except json.JSONDecodeError:
        agent_ids = []
    agent_list = [a.strip().lower() for a in agent_ids if str(a).strip()] or None
    requested_roster = list(agent_list) if agent_list else None
    # Resolve Room Preset → turn_profile. §3.2.1: roster > max_agents promotes
    # fast → supervisor (never silent truncate).
    from agent_lab.room.preset import (
        preset_turn_profile,
        resolve_implicit_room_preset,
        resolve_preset_for_roster,
    )

    preset_from_client = (preset or "").strip().lower()
    roster_n = len(agent_list) if agent_list else 0
    if preset_from_client:
        preset_raw = preset_from_client
    else:
        preset_raw = resolve_implicit_room_preset(topic, roster_n)
    preset_norm, preset_promoted_from = resolve_preset_for_roster(preset_raw, roster_n)
    profile_norm = (turn_profile or "discuss").strip().lower()
    _legacy_client_turn_profile = profile_norm in (
        "discuss",
        "",
        "analyze",
        "loop",
        "team",
        "quick",
        "free",
    )
    _form_default_turn_profile = profile_norm in ("discuss", "")
    if preset_norm and resolve_preset(preset_norm) is not None:
        # Topic-only / preset clients: ignore legacy Form default (discuss).
        # Explicit API turn_profile=loop|team|… is preserved when preset was inferred.
        if preset_from_client:
            if _legacy_client_turn_profile or preset_promoted_from:
                turn_profile = preset_turn_profile(preset_norm, fallback="loop")
        elif _form_default_turn_profile or preset_promoted_from:
            turn_profile = preset_turn_profile(preset_norm, fallback="loop")
    topic_text = (topic or "").strip()
    try:
        mode_contract = resolve_mode_contract(
            mode=mode_norm,
            synthesize=bool(synthesize),
            turn_profile=turn_profile,
            agents=agent_list,
            agent_rounds=max(1, min(agent_rounds, MAX_AGENT_PARALLEL_ROUNDS)),
            review_mode=review_mode,
            consensus_mode=consensus_mode,
            topic=topic_text,
        )
    except ModeContractError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    agent_list = mode_contract.agents

    if agent_list and topic_text:
        from agent_lab.room.agent_mentions import apply_agent_mention_filter

        mention_roster = requested_roster or agent_list or []
        narrowed, _, mention_targets = apply_agent_mention_filter(
            topic_text,
            agent_list,
            roster_pool=mention_roster,
        )
        if mention_targets:
            agent_list = narrowed

    if agent_list:
        bad = _agents_not_ready(agent_list)
        if bad:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "agents not ready",
                    "agents": bad,
                },
            )
    if mode_contract.plan_intent == "loop":
        effective_loop_agents = agent_list or list(AGENT_IDS)
        loop_capable, loop_skipped = partition_loop_capable_agents(effective_loop_agents)
        if not loop_capable:
            loop_readiness_detail = _loop_readiness_detail(list(loop_skipped))
            if loop_readiness_detail is not None:
                loop_readiness_detail["topology"] = mode_contract.topology
                loop_readiness_detail["requested_agents"] = list(effective_loop_agents)
                raise HTTPException(status_code=422, detail=loop_readiness_detail)
        elif loop_skipped:
            agent_list = list(loop_capable)
        elif agent_list is None:
            agent_list = list(loop_capable)

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
        folder = active_sessions_dir() / session_id
        if not folder.is_dir():
            raise HTTPException(status_code=404, detail="session not found")
        if _session_hard_cap_exhausted(folder):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "session token budget exhausted (AGENT_LAB_SESSION_HARD_CAP)",
                    "code": "budget_exhausted",
                },
            )
    else:
        folder = session_dir(topic, base=active_sessions_dir())
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

    if room_models and folder is not None:
        try:
            parsed_models = json.loads(room_models)
        except json.JSONDecodeError:
            parsed_models = None
        if isinstance(parsed_models, list):
            from agent_lab.agent.roster import normalize_composition_order
            from agent_lab.run.meta import patch_run_meta

            pinned = normalize_composition_order([str(tok) for tok in parsed_models if str(tok).strip()])
            if pinned:
                patch_run_meta(folder, lambda meta: {**meta, "room_models": pinned})

    if caps_obj:
        from agent_lab.room.agent_capabilities import write_agent_capabilities

        _plan_md, run_meta = room_session_context(folder)
        write_agent_capabilities(run_meta, caps_obj, mark_custom=True)
        from agent_lab.run.meta import persist_run_meta

        (folder / "run.json").write_text(
            json.dumps(persist_run_meta(run_meta), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    saved_files = await save_uploads(folder, files)
    if preset_norm and resolve_preset(preset_norm) is not None:
        from agent_lab.run.meta import patch_run_meta

        def _stamp_preset(run: dict[str, Any]) -> dict[str, Any]:
            run["room_preset"] = preset_norm
            if preset_promoted_from:
                run["room_preset_promoted_from"] = preset_promoted_from
                run["room_preset_promote_reason"] = "roster_exceeds_max_agents"
            elif "room_preset_promoted_from" in run:
                run.pop("room_preset_promoted_from", None)
                run.pop("room_preset_promote_reason", None)
            from agent_lab.room.turn_policy import (
                maybe_stamp_plan_execute_skill_intent,
                resolve_discuss_light,
            )

            run["discuss_light"] = resolve_discuss_light(
                mode=mode_norm,
                synthesize=bool(synthesize),
                consensus_mode=mode_contract.consensus_mode,
                agent_rounds=mode_contract.agent_rounds,
                room_preset=preset_norm,
                turn_profile=turn_profile,
                topic=topic,
                run_meta=run,
            )
            maybe_stamp_plan_execute_skill_intent(run, topic=topic)
            explicit = (role_policy or "").strip().lower()
            if explicit in ("auto", "force", "off"):
                run["role_policy"] = explicit
            else:
                run["role_policy"] = preset_role_policy(preset_norm)
            if preset_norm == "supervisor":
                from agent_lab.role_plan import resolve_delegator_agent

                run["team_lead"] = resolve_delegator_agent(
                    ["cursor", "codex", "claude"],
                    run_meta=run,
                )
            return run

        patch_run_meta(folder, _stamp_preset)
    parallel_rounds = max(1, min(mode_contract.agent_rounds, MAX_AGENT_PARALLEL_ROUNDS))
    review_mode = mode_contract.review_mode
    consensus_mode = mode_contract.consensus_mode
    use_efficiency = bool(efficiency_mode)
    profile_norm = mode_contract.runtime_turn_profile

    run_session_id = folder.name if folder else None

    from agent_lab.run.meta import read_run_meta
    from agent_lab.room.turn_policy import resolve_discuss_light

    sse_run_meta = read_run_meta(folder) if folder is not None else {}
    discuss_light_sse = resolve_discuss_light(
        mode=mode_norm,
        synthesize=bool(synthesize),
        consensus_mode=consensus_mode,
        agent_rounds=parallel_rounds,
        room_preset=preset_norm,
        turn_profile=profile_norm,
        topic=topic,
        run_meta=sse_run_meta,
    )

    def _cancel_on_client_disconnect() -> None:
        request_cancel(run_session_id)
        if folder is not None:
            from agent_lab.mission.loop import on_global_run_cancel

            try:
                on_global_run_cancel(folder)
            except Exception:
                pass

    async def generate():
        event_q: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        result: dict[str, Any] = {}
        disconnected = False
        loop = asyncio.get_running_loop()

        def on_event(typ: str, payload: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(event_q.put_nowait, {"type": typ, **payload})
            if folder is not None:
                from agent_lab.room.live_log import append_live_room_event

                from agent_lab.event_schema import event_validation_enabled

                if event_validation_enabled():
                    from agent_lab.event_schema import validate_event

                    ok, _errors = validate_event({"ts": "x", "type": typ, **payload})
                    if not ok:
                        return
                append_live_room_event(folder, typ, payload)

        def run_body(on_event_cb: Any) -> None:
            if folder is not None:
                from agent_lab.room.live_log import clear_live_room_log

                clear_live_room_log(folder)
            if folder is not None:
                patch_run_mode_contract(folder, mode_contract)
            if session_id:
                _messages, plan_md = continue_room_round(
                    folder,  # type: ignore[arg-type]
                    topic,
                    agents=agent_list,  # type: ignore[arg-type]
                    synthesize=synthesize,
                    skill_intent=skill_intent_norm,
                    parallel_rounds=parallel_rounds,
                    on_event=on_event_cb,
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
                    skill_intent=skill_intent_norm,
                    parallel_rounds=parallel_rounds,
                    on_event=on_event_cb,
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

        try:
            yield sse(
                {
                    "type": "start",
                    "topic": topic,
                    "session_id": run_session_id,
                    "workflow": "room.parallel",
                    "mode": mode_norm,
                    "synthesize": synthesize,
                    "synthesize_only": False,
                    "request_id": (request_id or "").strip() or None,
                    "agent_rounds": parallel_rounds,
                    "review_mode": review_mode,
                    "consensus_mode": consensus_mode,
                    "efficiency_mode": use_efficiency,
                    "turn_profile": profile_norm,
                    "room_preset": preset_norm,
                    "room_preset_promoted_from": preset_promoted_from,
                    "discuss_light": discuss_light_sse,
                    "workspace_id": workspace_norm,
                    "session_template": template_norm,
                    "attachments": saved_files,
                }
            )
            worker = loop.run_in_executor(
                None,
                lambda: _run_with_lock(
                    session_id=run_session_id,
                    on_event=on_event,
                    run_body=run_body,
                    result=result,
                    event_q=event_q,
                    loop=loop,
                ),
            )
            last_keepalive = time.monotonic()
            detached = False
            while True:
                if await request.is_disconnected():
                    if not disconnected:
                        disconnected = True
                        if _session_has_pending_human_inbox(folder):
                            # Human is still composing an answer to ask_human —
                            # let the worker keep waiting instead of killing it.
                            detached = True
                        else:
                            _cancel_on_client_disconnect()
                    break
                try:
                    ev = await asyncio.wait_for(event_q.get(), timeout=0.25)
                except asyncio.TimeoutError:
                    now = time.monotonic()
                    if now - last_keepalive >= _ROOM_SSE_KEEPALIVE_SEC:
                        last_keepalive = now
                        # Keep dev proxy (vite) and idle HTTP clients from closing long Room turns.
                        yield ": keepalive\n\n"
                    continue
                if ev is None:
                    break
                if ev.get("type") == "complete":
                    result["complete_event"] = ev
                    continue
                last_keepalive = time.monotonic()
                yield sse(ev)
            if disconnected:
                if detached:
                    # Worker is still legitimately running (e.g. mid ask_human
                    # wait) — leave it to finish on its own thread and release
                    # the run lock itself; don't block this dead connection on it.
                    return
                try:
                    await asyncio.wait_for(worker, timeout=8.0)
                except asyncio.TimeoutError:
                    pass
                for ev in _drain_room_event_queue(event_q, result):
                    yield sse(ev)
                for payload in _room_run_terminal_events(
                    result,
                    run_session_id=run_session_id,
                ):
                    yield sse(payload)
                return
            await worker
            for payload in _room_run_terminal_events(
                result,
                run_session_id=run_session_id,
            ):
                yield sse(payload)
        except Exception as e:
            yield sse({"type": "error", "message": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


_ROOM_RESUME_POLL_SEC = 0.35


def _terminal_event_from_persisted_state(
    folder: Path,
    run_session_id: str,
) -> list[dict[str, Any]]:
    """Synthesize a terminal SSE payload for a resume client attaching after
    the worker already finished (and possibly cleared live.jsonl on persist).

    Mirrors ``_room_run_terminal_events`` but reads from disk instead of the
    request-scoped ``result`` dict, since resume runs in a fresh request that
    never saw the original turn's in-memory state.
    """
    from agent_lab.run.meta import read_run_meta

    run_meta = read_run_meta(folder)
    status = str(run_meta.get("status") or "completed")
    if status == "cancelled":
        return [
            {"type": "run_cancelled", "message": "답변 중지됨"},
            {
                "type": "complete",
                "session_id": run_session_id,
                "plan_preview": "",
                "status": "partial",
                "failed_agents": [],
                "succeeded_agents": [],
                "cancelled": True,
                "resumed": True,
            },
        ]
    if status == "failed":
        msg = "room run ended with an error"
        return [
            {"type": "run_failed", "message": msg, "resumed": True},
            {"type": "error", "message": msg},
        ]
    from agent_lab.plan.paths import read_session_plan_md

    plan_md = read_session_plan_md(folder, run_meta)
    turns = run_meta.get("turns") or []
    last_turn = turns[-1] if turns else {}
    return [
        {
            "type": "complete",
            "session_id": run_session_id,
            "plan_preview": plan_md[:500] if plan_md else "",
            "status": status,
            "failed_agents": last_turn.get("failed_agents") or [],
            "succeeded_agents": last_turn.get("succeeded_agents") or [],
            "resumed": True,
        }
    ]


async def _room_resume_events(
    folder: Path,
    session_id: str,
    *,
    since: int,
    is_disconnected: Callable[[], Awaitable[bool]],
    poll_sec: float = _ROOM_RESUME_POLL_SEC,
):
    """Poll ``live.jsonl`` + the run lock and yield SSE-ready dict payloads.

    Extracted from the route so it can be driven directly in tests without a
    real ASGI ``Request`` (which has no cheap way to fake disconnects).
    """
    from agent_lab.room.live_log import read_live_room_log

    cursor = max(0, since)
    last_keepalive = time.monotonic()
    while True:
        if await is_disconnected():
            return
        live_log = read_live_room_log(folder)
        if len(live_log) > cursor:
            for row in live_log[cursor:]:
                yield {k: v for k, v in row.items() if k != "ts"}
            cursor = len(live_log)
            last_keepalive = time.monotonic()
        status = run_lock_status()
        is_live = bool(status.get("locked")) and status.get("session_id") == session_id
        if not is_live:
            for payload in _terminal_event_from_persisted_state(folder, session_id):
                yield payload
            return
        now = time.monotonic()
        if now - last_keepalive >= _ROOM_SSE_KEEPALIVE_SEC:
            last_keepalive = now
            yield None  # keepalive marker
        await asyncio.sleep(poll_sec)


@router.get("/room/runs/{session_id}/resume")
async def room_run_resume(session_id: str, request: Request, since: int = 0) -> StreamingResponse:
    """Reattach to an in-flight (or just-finished) Room turn after an SSE drop.

    Replays ``live.jsonl`` from ``since`` (a count of previously-consumed
    live-log-eligible events, tracked client-side), then either tails new
    events while the run lock still belongs to this session, or synthesizes
    a terminal event from persisted ``run.json`` state once it doesn't.
    """
    folder = session_folder_or_404(session_id)

    async def generate():
        async for ev in _room_resume_events(
            folder,
            session_id,
            since=since,
            is_disconnected=request.is_disconnected,
        ):
            yield ": keepalive\n\n" if ev is None else sse(ev)

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
    session_id = (body.session_id if body else None) or None
    children_terminated = request_cancel(session_id)
    released = maybe_release_orphaned_run_lock()
    mission_pause: dict[str, Any] | None = None
    if session_id:
        from agent_lab.mission.loop import on_global_run_cancel

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


class RetryAgentsRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=120)
    agents: list[str] | None = None


@router.post("/room/runs/retry-agents")
def retry_room_agents(body: RetryAgentsRequest) -> dict[str, Any]:
    """Re-invoke only the failed agents of the last partial turn (same human turn)."""
    from app.server.deps import session_folder_or_404
    from agent_lab.room.retry import RetryError, retry_failed_agents

    folder = session_folder_or_404(body.session_id)
    if not try_begin_run(session_id=body.session_id, run_kind="retry", label="Retry failed agents"):
        maybe_release_orphaned_run_lock()
        if not try_begin_run(session_id=body.session_id, run_kind="retry", label="Retry failed agents"):
            raise HTTPException(
                status_code=409,
                detail={"message": "a run is already in progress", **run_lock_recovery_hint()},
            )
    try:
        result = retry_failed_agents(folder, agents=body.agents)
    except RetryError as exc:
        raise HTTPException(status_code=exc.code, detail=exc.message) from exc
    finally:
        end_run()
    return {"ok": True, **result}


class SlashCommandRequest(BaseModel):
    text: str = Field(default="", max_length=2000)
    session_id: str = Field(default="")


@router.post("/room/slash")
def room_slash_command(body: SlashCommandRequest) -> dict[str, Any]:
    """Dispatch a slash command (/login|/logout|/accounts|/model|/usage|/agents
    or pipeline handles /pipeline|/clarify|/plan). Pipeline handles require session_id."""
    from agent_lab.slash_commands import dispatch

    folder = session_folder_or_404(body.session_id) if body.session_id.strip() else None
    return dispatch(body.text, session_folder=folder)
