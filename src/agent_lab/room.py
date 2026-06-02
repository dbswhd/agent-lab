"""Multi-agent room: Cursor + Codex + Claude in parallel (controlled workflow)."""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent_lab.agents.prompts import ROOM_SCRIBE
from agent_lab.agents.registry import AGENT_IDS, AgentId, available_agents, call_agent, label, model_label
from agent_lab.attachments import describe_attachments
from agent_lab.context_bundle import build_context_bundle
from agent_lab.context_meta import summarize_turn_context
from agent_lab.agent_envelope import (
    envelope_protocol_block,
    is_endorse_reply,
    is_pass_reply,
    parse_agent_response,
)
from agent_lab.room_consensus import (
    consensus_caps,
    consensus_follow_up,
    consensus_reply_verdict,
    debate_review_round,
    debate_round_last,
    is_substantive_reply,
    pick_anchor,
)
from agent_lab.consensus_agreements import (
    mark_agreements_plan_synced,
    record_consensus_agreement,
)
from agent_lab.room_turn_state import sync_run_meta_turn_state
from agent_lab.session_guidance import (
    apply_discuss_workspace,
    preserve_session_meta_from_prev,
    resolve_session_workspace_binding,
)
from agent_lab.agent_permissions import apply_discuss_executor_policy
from agent_lab.run_control import RoomRunCancelled, check_cancelled, is_cancelled
from agent_lab.session import SESSIONS_DIR, session_dir

MAX_AGENTS_PER_ROUND = 3
MAX_AGENT_PARALLEL_ROUNDS = 4  # per human message
DEFAULT_AGENT_PARALLEL_ROUNDS = 1  # discuss default; use 2+ for review / peer debate
RUN_SCHEMA_VERSION = 1
PLAN_FORMAT_VERSION = 1  # 지금 실행 + 실행 순서 sections
# Review round 2+: sequential pipeline (matches web ROOM_MODEL_AGENT_ORDER).
REVIEW_ROUND2_ORDER: tuple[AgentId, ...] = ("claude", "codex", "cursor")


@dataclass
class ChatMessage:
    role: str  # user | agent | system
    agent: str | None
    content: str
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    parallel_round: int | None = None  # 1..N within one human turn
    envelope: dict[str, Any] | None = None
    visibility: str = "human"  # human | peer (peer = coordination channel)

    def to_dict(self) -> dict[str, Any]:
        from agent_lab.room_chat_channels import normalize_visibility

        d: dict[str, Any] = {
            "role": self.role,
            "agent": self.agent,
            "content": self.content,
            "ts": self.ts,
        }
        if self.parallel_round is not None:
            d["parallel_round"] = self.parallel_round
        if self.envelope:
            d["envelope"] = self.envelope
        vis = normalize_visibility(self.visibility)
        if vis != "human":
            d["visibility"] = vis
        return d


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def format_thread(topic: str, messages: list[ChatMessage]) -> str:
    lines = [f"Human topic:\n{topic.strip()}\n"]
    for m in messages:
        if m.role == "user":
            lines.append(f"Human:\n{m.content}\n")
        elif m.role == "agent" and m.agent:
            lines.append(f"{label(m.agent)}:\n{m.content}\n")
    return "\n".join(lines)


def _human_turn_count(messages: list[ChatMessage]) -> int:
    return sum(1 for m in messages if m.role == "user")


def _review_advocate(agents: list[AgentId], human_turn_index: int) -> AgentId:
    """Rotate devil's advocate by human turn (0-based index before current round)."""
    if not agents:
        raise ValueError("agents required for review mode")
    return agents[human_turn_index % len(agents)]


def _current_turn_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
    """Agent replies after the latest human message (same human turn)."""
    last_user = -1
    for i, m in enumerate(messages):
        if m.role == "user":
            last_user = i
    if last_user < 0:
        return messages
    return messages[last_user + 1 :]


def _round_agent_order(
    agents: list[AgentId],
    *,
    review_mode: bool,
    parallel_round: int,
    run_meta: dict[str, Any] | None = None,
) -> list[AgentId]:
    if review_mode and parallel_round >= 2:
        return [a for a in REVIEW_ROUND2_ORDER if a in agents]
    if parallel_round == 1 and run_meta and not review_mode:
        from agent_lab.room_team_orchestration import team_r1_split

        teammates, lead_tail = team_r1_split([str(a) for a in agents], run_meta)
        if lead_tail and teammates:
            order = teammates + lead_tail
            pool = {str(a).lower(): a for a in agents}
            return [pool[k] for k in order if k in pool]
    return agents


def _agent_user_payload(
    topic: str,
    messages: list[ChatMessage],
    agent: AgentId,
    *,
    permissions: dict | None = None,
    parallel_round: int = 1,
    review_mode: bool = False,
    review_advocate: AgentId | None = None,
    plan_md: str = "",
    run_meta: dict[str, Any] | None = None,
) -> str:
    from agent_lab.agent_permissions import permission_preamble

    bundle = build_context_bundle(
        topic,
        messages,
        agent,
        permission_lines=permission_preamble(permissions, agent),
        parallel_round=parallel_round,
        review_mode=review_mode,
        review_advocate=review_advocate,
        plan_md=plan_md,
        run_meta=run_meta,
        permissions=permissions,
        all_messages=messages,
    )
    return bundle.render()


def build_agent_context_bundle(
    topic: str,
    messages: list[ChatMessage],
    agent: AgentId,
    *,
    permissions: dict | None = None,
    parallel_round: int = 1,
    review_mode: bool = False,
    review_advocate: AgentId | None = None,
    plan_md: str = "",
    run_meta: dict[str, Any] | None = None,
    efficiency_mode: bool = False,
    slim_context: bool = False,
):
    """ContextBundle for preview / debugging (payload + layer metadata)."""
    from agent_lab.agent_permissions import permission_preamble

    return build_context_bundle(
        topic,
        messages,
        agent,
        permission_lines=permission_preamble(permissions, agent),
        parallel_round=parallel_round,
        review_mode=review_mode,
        review_advocate=review_advocate,
        plan_md=plan_md,
        run_meta=run_meta,
        permissions=permissions,
        all_messages=messages,
        efficiency_mode=efficiency_mode,
        slim_context=slim_context,
    )


OnAgentEvent = Callable[[str, dict[str, Any]], None]
# event types: agent_start, agent_activity, agent_done, agent_error, turn_failed


def _effective_discuss_permissions(
    permissions: dict | None,
    *,
    topic: str,
    plan_md: str,
    run_meta: dict[str, Any] | None,
) -> dict:
    binding = resolve_session_workspace_binding(
        permissions,
        topic=topic,
        plan_md=plan_md,
        run_meta=run_meta,
    )
    perms = apply_discuss_executor_policy(permissions, discuss=True)
    return apply_discuss_workspace(perms, binding)


def _agent_turn_failed(replies: list[ChatMessage]) -> bool:
    return any(m.role == "system" and m.agent for m in replies)


def _is_agent_error_message(msg: ChatMessage) -> bool:
    return msg.role == "system" and bool(msg.agent)


def _call_one_agent(
    aid: AgentId,
    *,
    topic: str,
    thread: list[ChatMessage],
    parallel_round: int,
    permissions: dict | None,
    review_mode: bool,
    review_advocate: AgentId | None,
    plan_md: str,
    run_meta: dict[str, Any] | None,
    on_event: OnAgentEvent | None,
    context_log: list[dict[str, Any]] | None = None,
    extra_follow_up: str = "",
    efficiency_mode: bool = False,
    slim_context: bool = False,
) -> ChatMessage:
    def _emit(typ: str, payload: dict[str, Any]) -> None:
        if on_event:
            on_event(typ, payload)

    _emit("agent_start", {"agent": aid, "round": parallel_round})

    def _activity(line: str) -> None:
        _emit(
            "agent_activity",
            {"agent": aid, "round": parallel_round, "text": line},
        )

    effective_permissions = _effective_discuss_permissions(
        permissions,
        topic=topic,
        plan_md=plan_md,
        run_meta=run_meta,
    )

    from agent_lab.room_team_orchestration import is_discuss_only_turn, lead_discuss_role_block

    lead_block = ""
    if run_meta and is_discuss_only_turn(
        mode=str(run_meta.get("_active_turn_mode") or "discuss"),
        synthesize=bool(run_meta.get("_active_synthesize")),
        consensus_mode=bool(run_meta.get("_active_consensus")),
    ):
        lead_block = lead_discuss_role_block(aid, run_meta)
    combined_follow = "\n\n".join(
        x for x in (lead_block, extra_follow_up) if x and x.strip()
    )

    try:
        bundle = build_agent_context_bundle(
            topic,
            thread,
            aid,
            permissions=permissions,
            parallel_round=parallel_round,
            review_mode=review_mode,
            review_advocate=review_advocate,
            plan_md=plan_md,
            run_meta=run_meta,
            efficiency_mode=efficiency_mode,
            slim_context=slim_context,
        )
        payload = bundle.render()
        if combined_follow.strip():
            payload = f"{payload}\n\n{combined_follow.strip()}"
        context_meta = bundle.meta.to_dict()
        context_meta["model"] = model_label(aid)
        if context_log is not None:
            context_log.append(context_meta)
        text = call_agent(
            aid,
            "",
            payload,
            permissions=effective_permissions,
            on_activity=_activity if aid in ("cursor", "codex") else None,
        )
        parsed = parse_agent_response(text)
        envelope_dict = parsed.envelope.to_dict() if parsed.envelope else None
        body = parsed.body or text
        from agent_lab.room_chat_channels import message_visibility

        msg = ChatMessage(
            role="agent",
            agent=aid,
            content=body,
            parallel_round=parallel_round,
            envelope=envelope_dict,
            visibility=message_visibility(role="agent", content=body),
        )
        _emit(
            "agent_done",
            {
                "agent": aid,
                "chars": len(body),
                "content": body,
                "round": parallel_round,
                "pass": is_pass_reply(body, envelope_dict),
                "no_objection": is_endorse_reply(body, envelope_dict),
                "envelope": envelope_dict,
                "envelope_valid": parsed.envelope is not None,
                "envelope_parse_error": parsed.envelope_parse_error,
                "context_meta": context_meta,
            },
        )
        return msg
    except Exception as e:
        _emit(
            "agent_error",
            {
                "agent": aid,
                "message": str(e),
                "round": parallel_round,
                "failed": True,
            },
        )
        _emit(
            "turn_failed",
            {
                "agent": aid,
                "message": str(e),
                "round": parallel_round,
                "reason": "bridge_or_timeout",
            },
        )
        return ChatMessage(
            role="system",
            agent=aid,
            content=f"[{label(aid)} error] {e}",
            parallel_round=parallel_round,
        )


def run_consensus_agent_rounds(
    topic: str,
    messages: list[ChatMessage],
    *,
    agents: list[AgentId] | None = None,
    on_event: OnAgentEvent | None = None,
    permissions: dict | None = None,
    human_turn_index: int = 0,
    plan_md: str = "",
    run_meta: dict[str, Any] | None = None,
    context_log: list[dict[str, Any]] | None = None,
    efficiency_mode: bool = False,
) -> tuple[list[ChatMessage], dict[str, Any] | None]:
    """자유 토론: R1 병렬 후 앵커 제안에 전원 「이의 없습니다」까지 순차 반복."""
    active = list(agents or available_agents())[:MAX_AGENTS_PER_ROUND]
    if not active:
        raise RuntimeError("No agents available.")

    all_replies: list[ChatMessage] = []
    calls = 0
    cap_rounds, cap_calls = consensus_caps(efficiency_mode=efficiency_mode)

    try:
        check_cancelled()
        if on_event:
            on_event(
                "agent_round_start",
                {"round": 1, "total": cap_rounds, "consensus": True},
            )
        batch = run_parallel_round(
            topic,
            messages,
            agents=active,
            parallel_round=1,
            on_event=on_event,
            permissions=permissions,
            review_mode=False,
            human_turn_index=human_turn_index,
            plan_md=plan_md,
            run_meta=run_meta,
            context_log=context_log,
            efficiency_mode=efficiency_mode,
        )
        all_replies.extend(batch)
        calls += len(batch)

        if _agent_turn_failed(batch):
            if on_event:
                on_event(
                    "turn_failed",
                    {"reason": "agent_error", "round": 1, "consensus": True},
                )
                on_event(
                    "consensus_incomplete",
                    {
                        "reason": "agent_error",
                        "message": "에이전트 호출 실패 — 합의를 기록하지 않습니다.",
                    },
                )
            return all_replies, {
                "status": "failed",
                "reason": "agent_error",
                "rounds": 1,
                "calls": calls,
            }

        working = messages + all_replies
        sync_run_meta_turn_state(
            run_meta,
            working,
            active_agents=active,
            plan_md=plan_md,
        )

        if len(active) < 2:
            return all_replies, None

        working = messages + all_replies
        last_debate = debate_round_last(efficiency_mode=efficiency_mode)
        for r in range(2, last_debate + 1):
            if calls >= cap_calls:
                break
            check_cancelled()
            review = debate_review_round(r)
            if on_event:
                on_event(
                    "agent_round_start",
                    {
                        "round": r,
                        "total": cap_rounds,
                        "consensus": True,
                        "debate": True,
                        "review_mode": review,
                    },
                )
            batch = run_parallel_round(
                topic,
                working,
                agents=active,
                parallel_round=r,
                on_event=on_event,
                permissions=permissions,
                review_mode=review,
                human_turn_index=human_turn_index,
                plan_md=plan_md,
                run_meta=run_meta,
                context_log=context_log,
                efficiency_mode=efficiency_mode,
            )
            all_replies.extend(batch)
            calls += len(batch)
            working = messages + all_replies
            sync_run_meta_turn_state(
                run_meta,
                working,
                active_agents=active,
                plan_md=plan_md,
            )
            if _agent_turn_failed(batch):
                if on_event:
                    on_event(
                        "turn_failed",
                        {"reason": "agent_error", "round": r, "consensus": True},
                    )
                    on_event(
                        "consensus_incomplete",
                        {
                            "reason": "agent_error",
                            "message": "토론 루프 중 에이전트 실패 — 합의를 기록하지 않습니다.",
                        },
                    )
                return all_replies, {
                    "status": "failed",
                    "reason": "agent_error",
                    "rounds": r,
                    "calls": calls,
                }

        anchor = pick_anchor(_current_turn_messages(working), active)
        if not anchor:
            if on_event:
                on_event(
                    "consensus_incomplete",
                    {
                        "reason": "no_anchor",
                        "message": "실질 제안이 없어 합의 확인을 건너뜁니다.",
                    },
                )
            return all_replies, None

        pending: set[AgentId] = {a for a in active if a != anchor.agent}
        consented: list[str] = []
        parallel_round = last_debate + 1
        sync_run_meta_turn_state(
            run_meta,
            working,
            active_agents=active,
            consensus={
                "status": "open",
                "anchor": anchor.to_dict(),
                "pending_agents": sorted(pending),
            },
            plan_md=plan_md,
            pending_agents=sorted(pending),
        )

        while pending and parallel_round <= cap_rounds and calls < cap_calls:
            check_cancelled()
            if on_event:
                on_event(
                    "agent_round_start",
                    {
                        "round": parallel_round,
                        "total": cap_rounds,
                        "consensus": True,
                    },
                )
            thread = list(messages) + list(all_replies)
            from agent_lab.room_tasks import open_tasks_for_consensus

            open_tasks = open_tasks_for_consensus(run_meta)
            task_refs = [
                str(t.get("id") or "")
                for t in open_tasks
                if t.get("id")
            ]
            follow = consensus_follow_up(anchor, open_task_refs=task_refs or None)
            for aid in [a for a in active if a in pending]:
                if calls >= cap_calls:
                    break
                check_cancelled()
                msg = _call_one_agent(
                    aid,
                    topic=topic,
                    thread=thread,
                    parallel_round=parallel_round,
                    permissions=permissions,
                    review_mode=False,
                    review_advocate=None,
                    plan_md=plan_md,
                    run_meta=run_meta,
                    on_event=on_event,
                    context_log=context_log,
                    extra_follow_up=follow,
                    efficiency_mode=efficiency_mode,
                    slim_context=efficiency_mode,
                )
                all_replies.append(msg)
                thread.append(msg)
                calls += 1
                if _is_agent_error_message(msg):
                    if on_event:
                        on_event(
                            "turn_failed",
                            {
                                "agent": aid,
                                "reason": "agent_error",
                                "round": parallel_round,
                                "consensus": True,
                            },
                        )
                        on_event(
                            "consensus_incomplete",
                            {
                                "reason": "agent_error",
                                "agent": aid,
                                "message": "에이전트 호출 실패 — ENDORSE 합의를 중단합니다.",
                            },
                        )
                    meta = {
                        "status": "failed",
                        "reason": "agent_error",
                        "agent": aid,
                        "anchor": anchor.to_dict(),
                        "rounds": parallel_round,
                        "calls": calls,
                    }
                    sync_run_meta_turn_state(
                        run_meta,
                        thread,
                        active_agents=active,
                        consensus=meta,
                        plan_md=plan_md,
                    )
                    return all_replies, meta
                text = msg.content or ""
                verdict = consensus_reply_verdict(text, msg.envelope)
                if verdict in ("endorse", "pass"):
                    pending.discard(aid)
                    consented.append(aid)
                elif verdict == "substantive" or is_substantive_reply(
                    text, msg.envelope
                ):
                    new_anchor = pick_anchor(_current_turn_messages(thread), active)
                    if new_anchor:
                        anchor = new_anchor
                        pending = {a for a in active if a != anchor.agent}
                        consented = []
                    else:
                        pending.discard(aid)

                sync_run_meta_turn_state(
                    run_meta,
                    thread,
                    active_agents=active,
                    consensus={
                        "status": "open",
                        "anchor": anchor.to_dict(),
                        "pending_agents": sorted(pending),
                        "agents_consented": consented,
                    },
                    plan_md=plan_md,
                    pending_agents=sorted(pending),
                )

            if not pending:
                from agent_lab.room_tasks import (
                    consensus_tasks_ready,
                    harvest_task_endorsements,
                )

                thread_all = list(messages) + list(all_replies)
                harvest_task_endorsements(
                    run_meta,
                    thread_all,
                    [str(a) for a in active],
                )
                tasks_ready, task_blockers = consensus_tasks_ready(
                    run_meta, [str(a) for a in active]
                )
                max_r = max((m.parallel_round or 1) for m in all_replies)
                if not tasks_ready:
                    meta = {
                        "status": "incomplete",
                        "reason": "open_tasks",
                        "anchor": anchor.to_dict(),
                        "rounds": max_r,
                        "agents_consented": consented,
                        "calls": calls,
                        "open_tasks": task_blockers[:12],
                    }
                    sync_run_meta_turn_state(
                        run_meta,
                        thread_all,
                        active_agents=active,
                        consensus=meta,
                        plan_md=plan_md,
                    )
                    if on_event:
                        on_event(
                            "consensus_incomplete",
                            {
                                "reason": "open_tasks",
                                "message": (
                                    "앵커 합의는 됐지만 열린 작업에 팀 ENDORSE가 부족합니다. "
                                    "envelope refs에 task id/제목을 넣거나 작업을 완료하세요."
                                ),
                                "open_tasks": task_blockers[:8],
                            },
                        )
                    return all_replies, meta
                meta = {
                    "status": "reached",
                    "anchor": anchor.to_dict(),
                    "rounds": max_r,
                    "agents_consented": consented,
                    "calls": calls,
                }
                sync_run_meta_turn_state(
                    run_meta,
                    thread_all,
                    active_agents=active,
                    consensus=meta,
                    plan_md=plan_md,
                )
                if on_event:
                    on_event("consensus_reached", meta)
                return all_replies, meta
            parallel_round += 1

        max_r = max((m.parallel_round or 1) for m in all_replies) if all_replies else 1
        meta = {
            "status": "incomplete",
            "anchor": anchor.to_dict(),
            "pending_agents": sorted(pending),
            "rounds": max_r,
            "agents_consented": consented,
            "calls": calls,
            "reason": "cap",
        }
        sync_run_meta_turn_state(
            run_meta,
            list(messages) + list(all_replies),
            active_agents=active,
            consensus=meta,
            plan_md=plan_md,
            pending_agents=sorted(pending),
        )
        if on_event:
            on_event(
                "consensus_incomplete",
                {
                    **meta,
                    "message": (
                        f"합의 상한 도달 (라운드 {cap_rounds}, 호출 {cap_calls}). "
                        f"미응답: {', '.join(label(a) for a in pending)}"
                    ),
                },
            )
        return all_replies, meta
    except RoomRunCancelled:
        return all_replies, None


def run_parallel_round(
    topic: str,
    messages: list[ChatMessage],
    agents: list[AgentId] | None = None,
    *,
    parallel_round: int = 1,
    on_event: OnAgentEvent | None = None,
    permissions: dict | None = None,
    review_mode: bool = False,
    human_turn_index: int = 0,
    plan_md: str = "",
    run_meta: dict[str, Any] | None = None,
    context_log: list[dict[str, Any]] | None = None,
    efficiency_mode: bool = False,
) -> list[ChatMessage]:
    """Call selected agents for one round (round 1 parallel; round 2+ sequential for all modes)."""
    active = agents or available_agents()
    if not active:
        raise RuntimeError(
            "No agents available. Configure CURSOR_API_KEY, codex login, or claude login."
        )
    active = active[:MAX_AGENTS_PER_ROUND]
    ordered = _round_agent_order(
        active,
        review_mode=review_mode,
        parallel_round=parallel_round,
        run_meta=run_meta,
    )
    review_advocate = (
        _review_advocate(active, human_turn_index) if review_mode else None
    )

    check_cancelled()
    replies: list[ChatMessage] = []
    sequential = parallel_round >= 2
    from agent_lab.room_team_orchestration import team_r1_split

    parallel_batch, lead_tail = (
        team_r1_split([str(a) for a in ordered], run_meta)
        if parallel_round == 1 and not review_mode and run_meta
        else ([str(a) for a in ordered], [])
    )
    use_lead_last_r1 = (
        parallel_round == 1
        and not review_mode
        and lead_tail
        and len(parallel_batch) < len(ordered)
    )

    if use_lead_last_r1:
        check_cancelled()
        thread = list(messages)
        if parallel_batch:
            with ThreadPoolExecutor(max_workers=len(parallel_batch)) as pool:
                futures = {
                    pool.submit(
                        _call_one_agent,
                        aid,
                        topic=topic,
                        thread=messages,
                        parallel_round=parallel_round,
                        permissions=permissions,
                        review_mode=review_mode,
                        review_advocate=review_advocate,
                        plan_md=plan_md,
                        run_meta=run_meta,
                        on_event=on_event,
                        context_log=context_log,
                        efficiency_mode=efficiency_mode,
                    ): aid
                    for aid in parallel_batch
                }
                try:
                    for fut in as_completed(futures):
                        check_cancelled()
                        replies.append(fut.result())
                except RoomRunCancelled:
                    pass
            thread = list(messages) + replies
        for aid in lead_tail:
            check_cancelled()
            try:
                msg = _call_one_agent(
                    str(aid),
                    topic=topic,
                    thread=thread,
                    parallel_round=parallel_round,
                    permissions=permissions,
                    review_mode=review_mode,
                    review_advocate=review_advocate,
                    plan_md=plan_md,
                    run_meta=run_meta,
                    on_event=on_event,
                    context_log=context_log,
                    efficiency_mode=efficiency_mode,
                )
                replies.append(msg)
                thread.append(msg)
            except RoomRunCancelled:
                break
        return replies

    if sequential:
        thread = list(messages)
        round_follow = ""
        if parallel_round >= 2:
            ctx = "review" if review_mode else "discuss"
            round_follow = envelope_protocol_block(context=ctx)
        try:
            for aid in ordered:
                check_cancelled()
                msg = _call_one_agent(
                    aid,
                    topic=topic,
                    thread=thread,
                    parallel_round=parallel_round,
                    permissions=permissions,
                    review_mode=review_mode,
                    review_advocate=review_advocate,
                    plan_md=plan_md,
                    run_meta=run_meta,
                    on_event=on_event,
                    context_log=context_log,
                    extra_follow_up=round_follow,
                    efficiency_mode=efficiency_mode,
                )
                replies.append(msg)
                thread.append(msg)
        except RoomRunCancelled:
            pass
        return replies

    with ThreadPoolExecutor(max_workers=len(ordered)) as pool:
        futures = {
            pool.submit(
                _call_one_agent,
                aid,
                topic=topic,
                thread=messages,
                parallel_round=parallel_round,
                permissions=permissions,
                review_mode=review_mode,
                review_advocate=review_advocate,
                plan_md=plan_md,
                run_meta=run_meta,
                on_event=on_event,
                context_log=context_log,
                efficiency_mode=efficiency_mode,
            ): aid
            for aid in ordered
        }
        for fut in as_completed(futures):
            check_cancelled()
            replies.append(fut.result())
    return replies


def run_agent_rounds(
    topic: str,
    messages: list[ChatMessage],
    *,
    agents: list[AgentId] | None = None,
    parallel_rounds: int = DEFAULT_AGENT_PARALLEL_ROUNDS,
    on_event: OnAgentEvent | None = None,
    permissions: dict | None = None,
    review_mode: bool = False,
    human_turn_index: int = 0,
    plan_md: str = "",
    run_meta: dict[str, Any] | None = None,
    context_log: list[dict[str, Any]] | None = None,
    efficiency_mode: bool = False,
) -> list[ChatMessage]:
    """Run multiple parallel waves; later waves see earlier agents' replies in the thread."""
    n = max(1, min(parallel_rounds, MAX_AGENT_PARALLEL_ROUNDS))
    all_replies: list[ChatMessage] = []
    try:
        for r in range(1, n + 1):
            check_cancelled()
            if on_event:
                on_event("agent_round_start", {"round": r, "total": n})
            batch = run_parallel_round(
                topic,
                messages + all_replies,
                agents=agents,
                parallel_round=r,
                on_event=on_event,
                permissions=permissions,
                review_mode=review_mode,
                human_turn_index=human_turn_index,
                plan_md=plan_md,
                run_meta=run_meta,
                context_log=context_log,
                efficiency_mode=efficiency_mode,
            )
            all_replies.extend(batch)
            sync_run_meta_turn_state(
                run_meta,
                messages + all_replies,
                active_agents=list(agents or available_agents())[:MAX_AGENTS_PER_ROUND],
                plan_md=plan_md,
            )
    except RoomRunCancelled:
        pass
    return all_replies


def preview_agent_payload(
    folder: Path,
    agent: AgentId,
    *,
    agents: list[AgentId] | None = None,
    parallel_round: int = 1,
    permissions: dict | None = None,
    review_mode: bool = False,
    efficiency_mode: bool = False,
    slim_context: bool = False,
):
    """Build agent context without calling an LLM. Returns (payload str, ContextBundle)."""
    if not folder.is_dir():
        raise FileNotFoundError(f"session not found: {folder}")
    topic = (folder / "topic.txt").read_text(encoding="utf-8").strip()
    messages = load_session_messages(folder)
    plan_md, run_meta = _session_context(folder)
    active = agents or available_agents()
    active = active[:MAX_AGENTS_PER_ROUND]
    human_turn_index = max(0, _human_turn_count(messages) - 1)
    review_advocate = (
        _review_advocate(active, human_turn_index) if review_mode else None
    )
    bundle = build_agent_context_bundle(
        topic,
        messages,
        agent,
        permissions=permissions,
        parallel_round=parallel_round,
        review_mode=review_mode,
        review_advocate=review_advocate,
        plan_md=plan_md,
        run_meta=run_meta,
        efficiency_mode=efficiency_mode,
        slim_context=slim_context,
    )
    return bundle.render(), bundle


def format_thread_numbered(messages: list[ChatMessage]) -> str:
    """Thread with chat.jsonl line numbers for scribe provenance."""
    lines: list[str] = []
    for i, m in enumerate(messages, start=1):
        if m.role == "user":
            lines.append(f"L{i} Human:\n{m.content}\n")
        elif m.role == "agent" and m.agent:
            lines.append(f"L{i} {label(m.agent)}:\n{m.content}\n")
        else:
            lines.append(f"L{i} System:\n{m.content}\n")
    return "\n".join(lines)


def synthesize_plan(
    topic: str,
    messages: list[ChatMessage],
    backend_agent: AgentId | None = None,
) -> str:
    """Scribe pass using one agent backend."""
    from agent_lab.room_context import scribe_thread_block

    agent: AgentId = backend_agent or _default_scribe_agent()
    numbered = scribe_thread_block(messages)
    user = (
        f"Human topic:\n{topic.strip()}\n\n"
        f"---\n\nNumbered conversation (use L{{n}} as chat.jsonl#L{{n}} refs):\n\n"
        f"{numbered}\n\n---\n\nWrite the final plan.md content."
    )
    return call_agent(agent, ROOM_SCRIBE, user, scribe=True)


def _default_scribe_agent() -> AgentId:
    raw = (os.getenv("ROOM_SCRIBE_AGENT") or "claude").strip().lower()
    if raw in AGENT_IDS and raw in available_agents():
        return raw  # type: ignore[return-value]
    for fallback in ("codex", "claude", "cursor"):
        if fallback in available_agents():
            return fallback  # type: ignore[return-value]
    return "claude"


def _emit_plan_actions_validation(
    plan_md: str,
    on_event: Callable[[str, dict[str, Any]], None] | None,
) -> dict[str, Any]:
    import logging

    from agent_lab.plan_actions import validate_plan_actions_format

    result = validate_plan_actions_format(plan_md)
    if on_event:
        on_event("plan_actions_validation", result)
    if not result.get("ok"):
        logging.getLogger("agent_lab.plan_actions").warning(
            "plan_actions_validation issues=%s",
            result.get("issues"),
        )
    return result


def load_session_messages(folder: Path) -> list[ChatMessage]:
    from agent_lab.room_chat_channels import message_visibility

    chat_path = folder / "chat.jsonl"
    if not chat_path.is_file():
        return []
    messages: list[ChatMessage] = []
    for line in chat_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        pr = data.get("parallel_round")
        role = data.get("role", "system")
        content = data.get("content", "")
        messages.append(
            ChatMessage(
                role=role,
                agent=data.get("agent"),
                content=content,
                ts=data.get("ts", _now()),
                parallel_round=int(pr) if pr is not None else None,
                envelope=data.get("envelope"),
                visibility=message_visibility(
                    role=role,
                    content=content,
                    explicit=data.get("visibility"),
                ),
            )
        )
    return messages


def _append_peer_turn_digest(messages: list[ChatMessage]) -> list[ChatMessage]:
    """One peer-channel snapshot per human turn when R2+ agent replies exist."""
    from agent_lab.room_chat_channels import is_peer_visibility

    turn = _current_turn_messages(messages)
    for m in reversed(turn):
        if (
            m.role == "system"
            and is_peer_visibility(m.visibility)
            and "peer digest" in (m.content or "").lower()
        ):
            return messages
    agent_lines: list[str] = []
    max_pr = 1
    for m in turn:
        if m.role != "agent":
            continue
        pr = m.parallel_round or 1
        max_pr = max(max_pr, pr)
        if pr < 2:
            continue
        if is_peer_visibility(m.visibility):
            continue
        agent = m.agent or "agent"
        body = (m.content or "").strip()
        if not body:
            continue
        from agent_lab.agents.registry import label

        agent_lines.append(f"**{label(agent)}** (R{pr}):\n{body[:4000]}\n")
    if not agent_lines:
        return messages
    digest = (
        "[peer digest — internal coordination snapshot]\n\n"
        + "\n---\n".join(agent_lines)
    )
    return messages + [
        ChatMessage(
            role="system",
            agent=None,
            content=digest,
            visibility="peer",
            parallel_round=max_pr,
        )
    ]


def _append_human_turn_synthesis(
    messages: list[ChatMessage],
    run_meta: dict[str, Any] | None,
) -> list[ChatMessage]:
    """Human-channel turn summary (Sprint C) — one per completed human turn."""
    from agent_lab.room_team_orchestration import (
        build_human_turn_synthesis,
        is_human_synthesis_message,
    )
    from agent_lab.room_tasks import team_lead

    if not messages:
        return messages
    last_user = -1
    for i, m in enumerate(messages):
        if m.role == "user":
            last_user = i
    if last_user < 0:
        return messages
    for m in messages[last_user + 1 :]:
        if is_human_synthesis_message(m.content, m.visibility):
            return messages
    turn_slice = messages[last_user:]
    human_excerpt = messages[last_user].content or ""
    lead = team_lead(run_meta)
    body = build_human_turn_synthesis(
        turn_slice,
        lead=lead,
        human_excerpt=human_excerpt,
    )
    max_pr = max(
        (m.parallel_round or 1 for m in turn_slice if m.role == "agent"),
        default=1,
    )
    return messages + [
        ChatMessage(
            role="system",
            agent=None,
            content=body,
            visibility="human",
            parallel_round=max_pr,
        )
    ]


def _read_run_meta(folder: Path) -> dict[str, Any]:
    run_path = folder / "run.json"
    if not run_path.is_file():
        return {}
    try:
        return json.loads(run_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _session_context(folder: Path | None) -> tuple[str, dict[str, Any]]:
    """plan.md + run.json for trimmed agent payloads."""
    if not folder or not folder.is_dir():
        return "", {}
    plan_md = ""
    plan_path = folder / "plan.md"
    if plan_path.is_file():
        plan_md = plan_path.read_text(encoding="utf-8")
    return plan_md, _read_run_meta(folder)


def _prepare_team_coordination_before_round(
    folder: Path | None,
    run_meta: dict[str, Any],
    active_agents: list[AgentId],
    *,
    mode: str = "discuss",
    synthesize: bool = False,
    consensus_mode: bool = False,
) -> list[dict[str, Any]]:
    """Round-robin assign claimable tasks; persist run.json when session exists."""
    from agent_lab.room_tasks import assign_tasks_to_agents, ensure_team_lead
    from agent_lab.room_team_orchestration import should_assign_tasks_on_turn
    from agent_lab.run_meta import write_run_meta

    ensure_team_lead(run_meta)
    assigned: list[dict[str, Any]] = []
    if should_assign_tasks_on_turn(
        mode=mode, synthesize=synthesize, consensus_mode=consensus_mode
    ):
        assigned = assign_tasks_to_agents(
            run_meta, [str(a) for a in active_agents]
        )
    if folder and folder.is_dir():
        write_run_meta(folder, run_meta)
    return assigned


def _plan_content_normalized(plan_md: str) -> str:
    return plan_md.rstrip("\n") + "\n"


def _write_plan_if_changed(folder: Path, plan_md: str) -> bool:
    """Write plan.md only when content changes. Returns True if file was updated."""
    plan_path = folder / "plan.md"
    new_content = _plan_content_normalized(plan_md)
    if plan_path.is_file():
        existing = plan_path.read_text(encoding="utf-8")
        if existing == new_content:
            return False
    plan_path.write_text(new_content, encoding="utf-8")
    return True


def _find_completed_synthesize(folder: Path, request_id: str) -> dict[str, Any] | None:
    if not request_id:
        return None
    prev_run = _read_run_meta(folder)
    lpu = prev_run.get("last_plan_update") or {}
    if lpu.get("request_id") == request_id and lpu.get("status") == "completed":
        return lpu
    for turn in reversed(prev_run.get("turns") or []):
        if (
            turn.get("request_id") == request_id
            and turn.get("mode") == "plan"
            and turn.get("status") == "completed"
        ):
            return turn
    return None


def _write_session_files(
    folder: Path,
    topic: str,
    messages: list[ChatMessage],
    plan_md: str,
    *,
    agents_used: list[str] | None = None,
    merge_meta: dict[str, Any] | None = None,
    turn_meta: dict[str, Any] | None = None,
) -> None:
    (folder / "topic.txt").write_text(topic.strip() + "\n", encoding="utf-8")
    plan_changed = _write_plan_if_changed(folder, plan_md)

    from agent_lab.room_chat_channels import is_peer_visibility

    transcript_lines = [f"# Room transcript\n\n**Topic:** {topic}\n"]
    for m in messages:
        if is_peer_visibility(m.visibility):
            continue
        if m.role == "user":
            transcript_lines.append(f"## Human\n\n{m.content}")
        elif m.role == "agent" and m.agent:
            transcript_lines.append(f"## {label(m.agent)}\n\n{m.content}")
        else:
            transcript_lines.append(f"## System\n\n{m.content}")
    (folder / "transcript.md").write_text(
        "\n\n".join(transcript_lines) + "\n", encoding="utf-8"
    )

    prev_run = _read_run_meta(folder)
    messages_to_store = _append_peer_turn_digest(list(messages))
    messages_to_store = _append_human_turn_synthesis(messages_to_store, prev_run)
    chat_path = folder / "chat.jsonl"
    with chat_path.open("w", encoding="utf-8") as f:
        for m in messages_to_store:
            f.write(json.dumps(m.to_dict(), ensure_ascii=False) + "\n")

    created_at = (merge_meta or {}).get("created_at") or _now()
    round_nums = [
        m.parallel_round
        for m in messages
        if m.role == "agent" and m.parallel_round is not None
    ]
    agent_parallel_rounds = max(round_nums) if round_nums else 1
    turns: list[dict[str, Any]] = list(prev_run.get("turns") or [])
    agreements: list[dict[str, Any]] = list(prev_run.get("consensus_agreements") or [])
    if turn_meta:
        turn_ts = str(turn_meta.get("completed_at") or turn_meta.get("ts") or _now())
        agreements = record_consensus_agreement(
            agreements,
            consensus=turn_meta.get("consensus"),
            message_count=len(messages_to_store),
            ts=turn_ts,
        )
    if turn_meta:
        turns.append({**turn_meta, "ts": turn_meta.get("ts") or _now()})
    run_meta: dict[str, Any] = {
        "workflow_id": "room.parallel",
        "run_schema_version": RUN_SCHEMA_VERSION,
        "plan_format_version": PLAN_FORMAT_VERSION,
        "topic": topic,
        "created_at": created_at,
        "agents": agents_used or [a for a in AGENT_IDS],
        "status": turn_meta.get("status", "completed") if turn_meta else "completed",
        "message_count": len(messages_to_store),
        "agent_parallel_rounds": agent_parallel_rounds,
        "turns": turns,
        "actions": list(prev_run.get("actions") or []),
        "approvals": list(prev_run.get("approvals") or []),
        "executions": list(prev_run.get("executions") or []),
        "consensus_agreements": agreements,
    }
    preserve_session_meta_from_prev(run_meta, prev_run)
    if turn_meta:
        if turn_meta.get("turn_lead"):
            run_meta["team_lead"] = turn_meta["turn_lead"]
        if turn_meta.get("turn_leads"):
            run_meta["turn_leads"] = turn_meta["turn_leads"]
    from agent_lab.session_guidance import sync_session_meta

    sync_session_meta(
        run_meta,
        topic=topic,
        messages=messages_to_store,
        plan_md=plan_md,
        permissions=(turn_meta or {}).get("permissions"),
    )
    from agent_lab.room_tasks import (
        auto_claim_tasks_from_turn,
        sync_tasks_after_turn,
        team_lead,
    )

    tm = turn_meta or {}
    sync_tasks_after_turn(
        run_meta,
        messages_to_store,
        human_turn=_human_turn_count(messages_to_store),
        plan_md=plan_md,
        mode=str(tm.get("mode") or "discuss"),
        synthesize=bool(tm.get("synthesize")),
        consensus_mode=bool(tm.get("consensus_mode")),
    )
    auto_claim_tasks_from_turn(
        run_meta,
        messages_to_store,
        lead_agent=team_lead(run_meta),
    )
    if plan_changed and plan_md.strip():
        from agent_lab.plan_provenance import extract_plan_provenance

        from agent_lab.room_tasks import RUN_PLAN_PROVENANCE_KEY

        run_meta[RUN_PLAN_PROVENANCE_KEY] = extract_plan_provenance(plan_md)
    if turn_meta:
        run_meta["last_turn"] = turns[-1]
        for key in (
            "mode",
            "synthesize",
            "permissions",
            "model",
            "latency_ms",
            "request_id",
            "started_at",
            "completed_at",
        ):
            if key in turn_meta:
                run_meta[key] = turn_meta[key]
    if prev_run.get("last_plan_update"):
        run_meta["last_plan_update"] = prev_run["last_plan_update"]
    record_plan_update = bool(
        turn_meta
        and turn_meta.get("mode") == "plan"
        and (
            plan_changed
            or turn_meta.get("plan_trigger") == "consensus_reached"
        )
    )
    if record_plan_update:
        trigger = turn_meta.get("plan_trigger") or (
            "synthesize_only"
            if turn_meta.get("synthesize_only")
            else "plan_turn"
        )
        run_meta["last_plan_update"] = {
            "ts": turn_meta.get("completed_at") or turn_meta.get("ts") or _now(),
            "trigger": trigger,
            "mode": "plan",
            "synthesize_only": bool(
                turn_meta.get("synthesize_only") and trigger == "synthesize_only"
            ),
            "request_id": turn_meta.get("request_id"),
            "started_at": turn_meta.get("started_at"),
            "completed_at": turn_meta.get("completed_at"),
            "agents": turn_meta.get("agents") or agents_used or [],
            "message_count": len(messages),
            "chat_from_line": 1,
            "chat_to_line": len(messages),
            "status": turn_meta.get("status", "completed"),
        }
        summary = turn_meta.get("plan_sync_summary")
        if isinstance(summary, str) and summary.strip():
            run_meta["last_plan_update"]["plan_sync_summary"] = summary.strip()
        if trigger == "consensus_reached":
            for row in reversed(agreements):
                if row.get("excerpt") and not row.get("plan_synced"):
                    run_meta["last_plan_update"]["consensus_excerpt"] = row["excerpt"]
                    break
        synced_at = str(
            turn_meta.get("completed_at") or turn_meta.get("ts") or _now()
        )
        agreements = mark_agreements_plan_synced(
            agreements,
            message_count=len(messages),
            synced_at=synced_at,
        )
        run_meta["consensus_agreements"] = agreements
    (folder / "run.json").write_text(
        json.dumps(run_meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    meta: dict[str, Any] = {
        "topic": topic,
        "created_at": created_at,
        "workflow": "room.parallel",
        "agents": run_meta["agents"],
    }
    if run_meta.get("session_phase"):
        meta["session_phase"] = run_meta["session_phase"]
    if run_meta.get("layout_frozen"):
        meta["layout_frozen"] = True
    if run_meta.get("workspace_preset"):
        meta["workspace_preset"] = run_meta["workspace_preset"]
    if run_meta.get("session_template"):
        meta["session_template"] = run_meta["session_template"]
    binding = run_meta.get("workspace_binding")
    if isinstance(binding, dict) and binding.get("label"):
        meta["workspace_label"] = binding["label"]
    if merge_meta:
        meta = {**merge_meta, **meta, "topic": topic, "agents": run_meta["agents"]}
    (folder / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def save_room_session(
    topic: str,
    messages: list[ChatMessage],
    plan_md: str,
    *,
    base: Path | None = None,
    agents_used: list[str] | None = None,
    turn_meta: dict[str, Any] | None = None,
) -> Path:
    folder = session_dir(topic, base=base or SESSIONS_DIR)
    _write_session_files(
        folder, topic, messages, plan_md, agents_used=agents_used, turn_meta=turn_meta
    )
    return folder


def _peer_metrics_for_messages(messages: list[ChatMessage]) -> dict[str, Any]:
    from agent_lab.room_turn_state import current_turn_slice, peer_turn_metrics

    turn_msgs, _ = current_turn_slice(messages)
    return peer_turn_metrics(turn_msgs)


def _final_turn_state_dict(
    messages: list[ChatMessage],
    *,
    run_meta: dict[str, Any] | None,
    active_agents: list[str],
    consensus_meta: dict[str, Any] | None,
    plan_md: str,
) -> dict[str, Any]:
    if run_meta and run_meta.get("turn_state"):
        return run_meta["turn_state"]  # type: ignore[return-value]
    from agent_lab.room_turn_state import current_turn_slice, derive_turn_state

    turn_msgs, line_base = current_turn_slice(messages)
    return derive_turn_state(
        turn_msgs,
        line_base=line_base,
        active_agents=active_agents,
        consensus=consensus_meta,
        plan_md=plan_md,
    ).to_dict()


def _turn_snapshot(
    *,
    mode: str,
    synthesize: bool,
    agents_used: list[str],
    parallel_rounds: int,
    permissions: dict | None,
    latency_ms: int,
    status: str = "completed",
    synthesize_only: bool = False,
    plan_trigger: str | None = None,
    request_id: str | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    review_mode: bool = False,
    review_advocate: str | None = None,
    context_log: list[dict[str, Any]] | None = None,
    consensus_mode: bool = False,
    consensus: dict[str, Any] | None = None,
    efficiency_mode: bool = False,
    turn_state: dict[str, Any] | None = None,
    turn_profile: str | None = None,
    plan_sync_summary: str | None = None,
    turn_lead: str | None = None,
    turn_leads: dict[str, str] | None = None,
    send_receipt: str | None = None,
    peer_message_count: int | None = None,
    agents_with_r2_reply: list[str] | None = None,
) -> dict[str, Any]:
    from agent_lab.invoke import model_name

    snap: dict[str, Any] = {
        "mode": mode,
        "synthesize": synthesize,
        "agent_parallel_rounds": parallel_rounds,
        "agents": agents_used,
        "permissions": permissions or {},
        "model": model_name(),
        "latency_ms": latency_ms,
        "status": status,
    }
    if context_log:
        snap["context"] = {
            "agents": context_log,
            "payload_chars_total": sum(
                (entry.get("layer_chars") or {}).get("total", 0)
                for entry in context_log
            ),
            "summary": summarize_turn_context(context_log),
        }
        snap["models"] = {
            entry["agent"]: entry.get("model", "")
            for entry in context_log
            if entry.get("agent")
        }
    if synthesize_only:
        snap["synthesize_only"] = True
    if plan_trigger:
        snap["plan_trigger"] = plan_trigger
    if request_id:
        snap["request_id"] = request_id
    if started_at:
        snap["started_at"] = started_at
    if completed_at:
        snap["completed_at"] = completed_at
    if review_mode:
        snap["review_mode"] = True
        if review_advocate:
            snap["review_advocate"] = review_advocate
    if consensus_mode:
        snap["consensus_mode"] = True
        if consensus:
            snap["consensus"] = consensus
    if efficiency_mode:
        snap["efficiency_mode"] = True
    if turn_state:
        snap["turn_state"] = turn_state
    if turn_profile and turn_profile in ("quick", "analyze", "discuss", "review", "free"):
        snap["turn_profile"] = (
            "analyze" if turn_profile == "discuss" else turn_profile
        )
    if plan_sync_summary:
        snap["plan_sync_summary"] = plan_sync_summary
    if turn_lead:
        snap["turn_lead"] = turn_lead
    if turn_leads:
        snap["turn_leads"] = turn_leads
    if send_receipt:
        snap["send_receipt"] = send_receipt
    if peer_message_count is not None:
        snap["peer_message_count"] = peer_message_count
    if agents_with_r2_reply:
        snap["agents_with_r2_reply"] = list(agents_with_r2_reply)
    return snap


def consensus_reached(consensus_meta: dict[str, Any] | None) -> bool:
    """True when free-discuss consensus loop finished with full agreement."""
    return bool(consensus_meta and consensus_meta.get("status") == "reached")


def synthesize_session_plan(
    folder: Path,
    *,
    on_event: OnAgentEvent | None = None,
    permissions: dict | None = None,
    request_id: str | None = None,
    trigger: str = "synthesize_only",
    previous_plan_md: str | None = None,
) -> tuple[str, str]:
    """Re-synthesize plan.md from existing chat without a new agent round."""
    from agent_lab.plan_sync_summary import summarize_plan_changes

    if not folder.is_dir():
        raise FileNotFoundError(f"session not found: {folder}")
    plan_path = folder / "plan.md"
    old_plan = previous_plan_md
    if old_plan is None and plan_path.is_file():
        old_plan = plan_path.read_text(encoding="utf-8")
    if request_id and _find_completed_synthesize(folder, request_id):
        if plan_path.is_file():
            if on_event:
                on_event("scribe_skipped", {"reason": "duplicate_request_id"})
            current = plan_path.read_text(encoding="utf-8")
            return current, summarize_plan_changes(old_plan or "", current)
        raise FileNotFoundError("plan.md not found")
    topic = (folder / "topic.txt").read_text(encoding="utf-8").strip()
    messages = load_session_messages(folder)
    if not messages:
        raise ValueError("no messages to synthesize")
    started_at = _now()
    t0 = time.perf_counter()
    if on_event:
        on_event("scribe_start", {})
    try:
        plan_md = synthesize_plan(topic, messages)
        _emit_plan_actions_validation(plan_md, on_event)
        if on_event:
            on_event("scribe_done", {"chars": len(plan_md)})
    except Exception as e:
        if on_event:
            on_event("scribe_error", {"message": str(e)})
        raise
    plan_sync_summary = summarize_plan_changes(old_plan or "", plan_md)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    completed_at = _now()
    existing_meta: dict[str, Any] = {}
    meta_path = folder / "meta.json"
    if meta_path.is_file():
        try:
            existing_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    agents_used = existing_meta.get("agents") or [a for a in available_agents()]
    _write_session_files(
        folder,
        topic,
        messages,
        plan_md,
        agents_used=agents_used,
        merge_meta={**existing_meta, "topic": topic},
        turn_meta=_turn_snapshot(
            mode="plan",
            synthesize=True,
            agents_used=agents_used,
            parallel_rounds=0,
            permissions=permissions,
            latency_ms=latency_ms,
            synthesize_only=True,
            plan_trigger=trigger,
            request_id=request_id,
            started_at=started_at,
            completed_at=completed_at,
            plan_sync_summary=plan_sync_summary,
            send_receipt="plan_updated",
        ),
    )
    return plan_md, plan_sync_summary


def maybe_auto_scribe_after_consensus(
    folder: Path,
    *,
    consensus_meta: dict[str, Any] | None,
    synthesize: bool,
    cancelled: bool,
    on_event: OnAgentEvent | None = None,
    permissions: dict | None = None,
) -> str | None:
    """After discuss+consensus, auto-scribe plan.md and notify what was reflected."""
    from agent_lab.consensus_agreements import (
        agreement_plan_synced_notice,
        consensus_topic_excerpt,
    )

    if cancelled or synthesize or not consensus_reached(consensus_meta):
        return None

    excerpt = consensus_topic_excerpt(consensus_meta)
    plan_path = folder / "plan.md"
    old_plan = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""

    if on_event:
        on_event("consensus_plan_sync_start", {"excerpt": excerpt})

    try:
        plan_md, summary = synthesize_session_plan(
            folder,
            on_event=on_event,
            permissions=permissions,
            trigger="consensus_reached",
            previous_plan_md=old_plan,
        )
        current_plan = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
        if current_plan != plan_md:
            plan_path.write_text(plan_md, encoding="utf-8")
    except Exception as e:
        if on_event:
            on_event(
                "consensus_plan_sync_failed",
                {"excerpt": excerpt, "message": str(e)},
            )
            on_event(
                "scribe_error",
                {"message": str(e), "auto": True, "excerpt": excerpt},
            )
        return None

    notice = agreement_plan_synced_notice(excerpt, summary)
    if on_event:
        on_event(
            "consensus_plan_synced",
            {
                "excerpt": excerpt,
                "summary": summary,
                "notice": notice,
                "trigger": "consensus_reached",
            },
        )
        from agent_lab.plan_execute import list_plan_actions

        actions_info = list_plan_actions(folder, permissions=permissions)
        recommended = actions_info.get("recommended")
        has_executable = recommended is not None
        action_key = recommended.get("action_key") if recommended else None
        on_event(
            "consensus_dry_run_proposal",
            {
                "excerpt": excerpt,
                "summary": summary,
                "notice": notice,
                "recommended": recommended,
                "has_executable": has_executable,
                "action_key": action_key,
            },
        )
    return plan_md


def continue_room_round(
    folder: Path,
    user_message: str,
    *,
    agents: list[AgentId] | None = None,
    synthesize: bool = False,
    parallel_rounds: int = DEFAULT_AGENT_PARALLEL_ROUNDS,
    on_event: OnAgentEvent | None = None,
    permissions: dict | None = None,
    review_mode: bool = False,
    consensus_mode: bool = False,
    efficiency_mode: bool = False,
    turn_profile: str | None = None,
) -> tuple[list[ChatMessage], str]:
    """Append a user turn + parallel agent replies to an existing session."""
    if not folder.is_dir():
        raise FileNotFoundError(f"session not found: {folder}")
    topic = (folder / "topic.txt").read_text(encoding="utf-8").strip()
    messages = load_session_messages(folder)
    body = user_message.strip()
    att = describe_attachments(folder)
    if att:
        body = f"{body}\n\n---\n\n{att}"
    human_turn_index = _human_turn_count(messages)
    messages.append(ChatMessage(role="user", agent=None, content=body))
    human_turn_num = _human_turn_count(messages)
    active_agents = [a for a in (agents or available_agents())]
    mode = "plan" if synthesize else "discuss"
    review_advocate = (
        _review_advocate(active_agents, human_turn_index)
        if review_mode and active_agents
        else None
    )
    plan_md, run_meta = _session_context(folder)
    from agent_lab.room_team_orchestration import resolve_turn_lead

    resolve_turn_lead(
        run_meta,
        human_turn_num,
        [str(a) for a in active_agents],
        user_message=body,
    )
    run_meta["_active_turn_mode"] = mode
    run_meta["_active_synthesize"] = synthesize
    run_meta["_active_consensus"] = consensus_mode
    if turn_profile:
        tp = (turn_profile or "analyze").strip().lower()
        run_meta["turn_profile"] = "analyze" if tp == "discuss" else tp
    from agent_lab.session_clarifier import build_clarifier_questions

    clarifier_questions = build_clarifier_questions(
        body,
        is_new_session=False,
        human_message_count=human_turn_num,
    )
    if clarifier_questions and on_event:
        on_event("clarifier_prompt", {"questions": clarifier_questions})
    t0 = time.perf_counter()
    context_log: list[dict[str, Any]] = []
    _prepare_team_coordination_before_round(
        folder,
        run_meta,
        active_agents,
        mode=mode,
        synthesize=synthesize,
        consensus_mode=consensus_mode,
    )
    consensus_meta: dict[str, Any] | None = None
    replies: list[ChatMessage] = []
    cancelled = False
    plan_before = (
        (folder / "plan.md").read_text(encoding="utf-8")
        if (folder / "plan.md").is_file()
        else ""
    )
    try:
        if clarifier_questions:
            replies = []
        elif consensus_mode:
            replies, consensus_meta = run_consensus_agent_rounds(
                topic,
                messages,
                agents=agents,
                on_event=on_event,
                permissions=permissions,
                human_turn_index=human_turn_index,
                plan_md=plan_md,
                run_meta=run_meta,
                context_log=context_log,
                efficiency_mode=efficiency_mode,
            )
            parallel_rounds = consensus_meta.get("rounds", 1) if consensus_meta else 1
        else:
            replies = run_agent_rounds(
                topic,
                messages,
                agents=agents,
                parallel_rounds=parallel_rounds,
                on_event=on_event,
                permissions=permissions,
                review_mode=review_mode,
                human_turn_index=human_turn_index,
                plan_md=plan_md,
                run_meta=run_meta,
                context_log=context_log,
                efficiency_mode=efficiency_mode,
            )
    except RoomRunCancelled:
        cancelled = True
    if cancelled or is_cancelled():
        cancelled = True
        if on_event:
            on_event("run_cancelled", {"message": "답변 중지됨"})
    messages.extend(replies)
    plan_md = plan_before
    if synthesize and not cancelled:
        if on_event:
            on_event("scribe_start", {})
        try:
            plan_md = synthesize_plan(topic, messages)
            _emit_plan_actions_validation(plan_md, on_event)
            if on_event:
                on_event("scribe_done", {"chars": len(plan_md)})
        except Exception as e:
            if on_event:
                on_event("scribe_error", {"message": str(e)})
    latency_ms = int((time.perf_counter() - t0) * 1000)
    turn_failed = _agent_turn_failed(replies) or (
        consensus_meta is not None and consensus_meta.get("status") == "failed"
    )
    turn_status = (
        "cancelled"
        if cancelled
        else ("failed" if turn_failed else "completed")
    )
    existing_meta: dict[str, Any] = {}
    meta_path = folder / "meta.json"
    if meta_path.is_file():
        try:
            existing_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    from agent_lab.room_tasks import team_lead
    from agent_lab.room_team_orchestration import resolve_send_receipt, turn_leads_map

    plan_updated = bool(
        synthesize and not cancelled and plan_md and plan_md != plan_before
    )
    peer = _peer_metrics_for_messages(messages)
    send_receipt_val = resolve_send_receipt(
        mode=mode,
        synthesize=synthesize,
        consensus_mode=consensus_mode,
        consensus=consensus_meta,
        plan_updated=plan_updated,
        status=turn_status,
    )
    _write_session_files(
        folder,
        topic,
        messages,
        plan_md,
        agents_used=active_agents,
        merge_meta={**existing_meta, "topic": topic},
        turn_meta=_turn_snapshot(
            mode=mode,
            synthesize=synthesize,
            agents_used=active_agents,
            parallel_rounds=parallel_rounds,
            permissions=permissions,
            latency_ms=latency_ms,
            status=turn_status,
            review_mode=review_mode,
            review_advocate=review_advocate,
            context_log=context_log,
            consensus_mode=consensus_mode,
            consensus=consensus_meta,
            efficiency_mode=efficiency_mode,
            turn_state=_final_turn_state_dict(
                messages,
                run_meta=run_meta,
                active_agents=active_agents,
                consensus_meta=consensus_meta,
                plan_md=plan_md,
            ),
            turn_profile=turn_profile,
            turn_lead=team_lead(run_meta),
            turn_leads=turn_leads_map(run_meta),
            send_receipt=send_receipt_val,
            peer_message_count=int(peer.get("peer_message_count") or 0),
            agents_with_r2_reply=list(peer.get("agents_with_r2_reply") or []),
        ),
    )
    auto_plan = maybe_auto_scribe_after_consensus(
        folder,
        consensus_meta=consensus_meta,
        synthesize=synthesize,
        cancelled=cancelled,
        on_event=on_event,
        permissions=permissions,
    )
    if auto_plan is not None:
        plan_md = auto_plan
    if on_event:
        on_event(
            "complete",
            {
                "session_id": folder.name,
                "path": str(folder),
                "cancelled": cancelled,
                "send_receipt": send_receipt_val,
                "turn_index": max(
                    0,
                    len((_read_run_meta(folder).get("turns") or [])) - 1,
                ),
            },
        )
    return messages, plan_md


def run_room(
    topic: str,
    *,
    agents: list[AgentId] | None = None,
    synthesize: bool = True,
    parallel_rounds: int = DEFAULT_AGENT_PARALLEL_ROUNDS,
    on_event: OnAgentEvent | None = None,
    sessions_base: Path | None = None,
    session_folder: Path | None = None,
    permissions: dict | None = None,
    review_mode: bool = False,
    consensus_mode: bool = False,
    efficiency_mode: bool = False,
    turn_profile: str | None = None,
) -> tuple[Path, list[ChatMessage], str]:
    """Full room flow: user message → parallel agents → optional plan synthesis."""
    from agent_lab.agent_permissions import normalize_agent_permissions

    permissions = normalize_agent_permissions(permissions)
    body = topic.strip()
    if session_folder and session_folder.is_dir():
        att = describe_attachments(session_folder)
        if att:
            body = f"{body}\n\n---\n\n{att}"
    messages: list[ChatMessage] = [
        ChatMessage(role="user", agent=None, content=body)
    ]
    folder: Path | None = None
    if session_folder and session_folder.is_dir():
        folder = session_folder
        if (folder / "topic.txt").is_file():
            topic = (folder / "topic.txt").read_text(encoding="utf-8").strip()
        messages = load_session_messages(folder) + messages

    active_agents = [a for a in (agents or available_agents())]
    human_turn_index = _human_turn_count(messages) - 1
    mode = "plan" if synthesize else "discuss"
    review_advocate = (
        _review_advocate(active_agents, max(0, human_turn_index))
        if review_mode and active_agents
        else None
    )
    plan_md, run_meta = _session_context(folder)
    human_turn_num = max(1, _human_turn_count(messages))
    from agent_lab.room_team_orchestration import resolve_turn_lead

    resolve_turn_lead(
        run_meta,
        human_turn_num,
        [str(a) for a in active_agents],
        user_message=topic,
    )
    run_meta["_active_turn_mode"] = mode
    run_meta["_active_synthesize"] = synthesize
    run_meta["_active_consensus"] = consensus_mode
    if turn_profile:
        tp = (turn_profile or "analyze").strip().lower()
        run_meta["turn_profile"] = "analyze" if tp == "discuss" else tp
    from agent_lab.session_clarifier import build_clarifier_questions

    is_new = folder is None or not (folder / "chat.jsonl").is_file()
    clarifier_questions = build_clarifier_questions(
        body,
        is_new_session=is_new,
        human_message_count=human_turn_num,
    )
    if clarifier_questions and on_event:
        on_event("clarifier_prompt", {"questions": clarifier_questions})
    t0 = time.perf_counter()
    context_log: list[dict[str, Any]] = []
    _prepare_team_coordination_before_round(
        folder,
        run_meta,
        active_agents,
        mode=mode,
        synthesize=synthesize,
        consensus_mode=consensus_mode,
    )
    consensus_meta: dict[str, Any] | None = None
    replies: list[ChatMessage] = []
    cancelled = False
    try:
        if clarifier_questions:
            replies = []
        elif consensus_mode:
            replies, consensus_meta = run_consensus_agent_rounds(
                topic,
                messages,
                agents=agents,
                on_event=on_event,
                permissions=permissions,
                human_turn_index=max(0, human_turn_index),
                plan_md=plan_md,
                run_meta=run_meta,
                context_log=context_log,
                efficiency_mode=efficiency_mode,
            )
            parallel_rounds = consensus_meta.get("rounds", 1) if consensus_meta else 1
        else:
            replies = run_agent_rounds(
                topic,
                messages,
                agents=agents,
                parallel_rounds=parallel_rounds,
                on_event=on_event,
                permissions=permissions,
                review_mode=review_mode,
                human_turn_index=max(0, human_turn_index),
                plan_md=plan_md,
                run_meta=run_meta,
                context_log=context_log,
                efficiency_mode=efficiency_mode,
            )
    except RoomRunCancelled:
        cancelled = True
    if cancelled or is_cancelled():
        cancelled = True
        if on_event:
            on_event("run_cancelled", {"message": "답변 중지됨"})
    messages.extend(replies)

    plan_md = ""
    if synthesize and not cancelled:
        if on_event:
            on_event("scribe_start", {})
        try:
            plan_md = synthesize_plan(topic, messages)
            _emit_plan_actions_validation(plan_md, on_event)
            if on_event:
                on_event("scribe_done", {"chars": len(plan_md)})
        except Exception as e:
            plan_md = f"## Plan synthesis failed\n\n{e}"
            if on_event:
                on_event("scribe_error", {"message": str(e)})

    latency_ms = int((time.perf_counter() - t0) * 1000)
    turn_failed = _agent_turn_failed(replies) or (
        consensus_meta is not None and consensus_meta.get("status") == "failed"
    )
    turn_status = (
        "cancelled"
        if cancelled
        else ("failed" if turn_failed else "completed")
    )
    from agent_lab.room_tasks import team_lead
    from agent_lab.room_team_orchestration import resolve_send_receipt, turn_leads_map

    peer = _peer_metrics_for_messages(messages)
    send_receipt_val = resolve_send_receipt(
        mode=mode,
        synthesize=synthesize,
        consensus_mode=consensus_mode,
        consensus=consensus_meta,
        plan_updated=bool(synthesize and not cancelled and plan_md),
        status=turn_status,
    )
    turn_meta = _turn_snapshot(
        mode=mode,
        synthesize=synthesize,
        agents_used=active_agents,
        parallel_rounds=parallel_rounds,
        permissions=permissions,
        latency_ms=latency_ms,
        status=turn_status,
        review_mode=review_mode,
        review_advocate=review_advocate,
        context_log=context_log,
        consensus_mode=consensus_mode,
        consensus=consensus_meta,
        efficiency_mode=efficiency_mode,
        turn_state=_final_turn_state_dict(
            messages,
            run_meta=run_meta,
            active_agents=active_agents,
            consensus_meta=consensus_meta,
            plan_md=plan_md,
        ),
        turn_profile=turn_profile,
        turn_lead=team_lead(run_meta),
        turn_leads=turn_leads_map(run_meta),
        send_receipt=send_receipt_val,
        peer_message_count=int(peer.get("peer_message_count") or 0),
        agents_with_r2_reply=list(peer.get("agents_with_r2_reply") or []),
    )

    if folder is None:
        folder = save_room_session(
            topic,
            messages,
            plan_md,
            base=sessions_base,
            agents_used=active_agents,
            turn_meta=turn_meta,
        )
    else:
        existing_meta: dict[str, Any] = {}
        if (folder / "meta.json").is_file():
            try:
                existing_meta = json.loads(
                    (folder / "meta.json").read_text(encoding="utf-8")
                )
            except json.JSONDecodeError:
                pass
        _write_session_files(
            folder,
            topic,
            messages,
            plan_md,
            agents_used=active_agents,
            merge_meta=existing_meta,
            turn_meta=turn_meta,
        )
    auto_plan = maybe_auto_scribe_after_consensus(
        folder,
        consensus_meta=consensus_meta,
        synthesize=synthesize,
        cancelled=cancelled,
        on_event=on_event,
        permissions=permissions,
    )
    if auto_plan is not None:
        plan_md = auto_plan
    if on_event:
        on_event(
            "complete",
            {
                "session_id": folder.name,
                "path": str(folder),
                "cancelled": cancelled,
                "send_receipt": send_receipt_val,
                "turn_index": max(
                    0,
                    len((_read_run_meta(folder).get("turns") or [])) - 1,
                ),
            },
        )
    return folder, messages, plan_md
