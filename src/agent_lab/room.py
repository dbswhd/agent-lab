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
from agent_lab.room_context import is_no_objection_response, is_pass_response
from agent_lab.room_consensus import (
    consensus_caps,
    consensus_follow_up,
    is_substantive_reply,
    pick_anchor,
)
from agent_lab.run_control import RoomRunCancelled, check_cancelled, is_cancelled
from agent_lab.session import SESSIONS_DIR, session_dir

MAX_AGENTS_PER_ROUND = 3
MAX_AGENT_PARALLEL_ROUNDS = 4  # per human message
DEFAULT_AGENT_PARALLEL_ROUNDS = 1  # discuss default; use 2+ for review / peer debate
RUN_SCHEMA_VERSION = 1
PLAN_FORMAT_VERSION = 0  # bump to 1 when scribe action atomization lands
# Review round 2+: sequential pipeline (matches web ROOM_MODEL_AGENT_ORDER).
REVIEW_ROUND2_ORDER: tuple[AgentId, ...] = ("claude", "codex", "cursor")


@dataclass
class ChatMessage:
    role: str  # user | agent | system
    agent: str | None
    content: str
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    parallel_round: int | None = None  # 1..N within one human turn

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "role": self.role,
            "agent": self.agent,
            "content": self.content,
            "ts": self.ts,
        }
        if self.parallel_round is not None:
            d["parallel_round"] = self.parallel_round
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
) -> list[AgentId]:
    if review_mode and parallel_round >= 2:
        return [a for a in REVIEW_ROUND2_ORDER if a in agents]
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
# event types: agent_start, agent_activity, agent_done, agent_error


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
        if extra_follow_up.strip():
            payload = f"{payload}\n\n{extra_follow_up.strip()}"
        context_meta = bundle.meta.to_dict()
        context_meta["model"] = model_label(aid)
        if context_log is not None:
            context_log.append(context_meta)
        text = call_agent(
            aid,
            "",
            payload,
            permissions=permissions,
            on_activity=_activity if aid == "cursor" else None,
        )
        msg = ChatMessage(
            role="agent",
            agent=aid,
            content=text,
            parallel_round=parallel_round,
        )
        _emit(
            "agent_done",
            {
                "agent": aid,
                "chars": len(text),
                "content": text,
                "round": parallel_round,
                "pass": is_pass_response(text),
                "no_objection": is_no_objection_response(text),
                "context_meta": context_meta,
            },
        )
        return msg
    except Exception as e:
        _emit("agent_error", {"agent": aid, "message": str(e)})
        return ChatMessage(
            role="system",
            agent=aid,
            content=f"[{label(aid)} error] {e}",
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

        if len(active) < 2:
            return all_replies, None

        working = messages + all_replies
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
        parallel_round = 2

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
            follow = consensus_follow_up(anchor)
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
                text = msg.content or ""
                if is_no_objection_response(text) or is_pass_response(text):
                    pending.discard(aid)
                    consented.append(aid)
                elif is_substantive_reply(text):
                    new_anchor = pick_anchor(_current_turn_messages(thread), active)
                    if new_anchor:
                        anchor = new_anchor
                        pending = {a for a in active if a != anchor.agent}
                        consented = []
                    else:
                        pending.discard(aid)

            if not pending:
                max_r = max((m.parallel_round or 1) for m in all_replies)
                meta = {
                    "status": "reached",
                    "anchor": anchor.to_dict(),
                    "rounds": max_r,
                    "agents_consented": consented,
                    "calls": calls,
                }
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
        active, review_mode=review_mode, parallel_round=parallel_round
    )
    review_advocate = (
        _review_advocate(active, human_turn_index) if review_mode else None
    )

    check_cancelled()
    replies: list[ChatMessage] = []
    sequential = parallel_round >= 2

    if sequential:
        thread = list(messages)
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


def load_session_messages(folder: Path) -> list[ChatMessage]:
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
        messages.append(
            ChatMessage(
                role=data.get("role", "system"),
                agent=data.get("agent"),
                content=data.get("content", ""),
                ts=data.get("ts", _now()),
                parallel_round=int(pr) if pr is not None else None,
            )
        )
    return messages


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

    transcript_lines = [f"# Room transcript\n\n**Topic:** {topic}\n"]
    for m in messages:
        if m.role == "user":
            transcript_lines.append(f"## Human\n\n{m.content}")
        elif m.role == "agent" and m.agent:
            transcript_lines.append(f"## {label(m.agent)}\n\n{m.content}")
        else:
            transcript_lines.append(f"## System\n\n{m.content}")
    (folder / "transcript.md").write_text(
        "\n\n".join(transcript_lines) + "\n", encoding="utf-8"
    )

    chat_path = folder / "chat.jsonl"
    with chat_path.open("w", encoding="utf-8") as f:
        for m in messages:
            f.write(json.dumps(m.to_dict(), ensure_ascii=False) + "\n")

    created_at = (merge_meta or {}).get("created_at") or _now()
    round_nums = [
        m.parallel_round
        for m in messages
        if m.role == "agent" and m.parallel_round is not None
    ]
    agent_parallel_rounds = max(round_nums) if round_nums else 1
    prev_run = _read_run_meta(folder)
    turns: list[dict[str, Any]] = list(prev_run.get("turns") or [])
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
        "message_count": len(messages),
        "agent_parallel_rounds": agent_parallel_rounds,
        "turns": turns,
        "actions": [],
        "approvals": [],
        "executions": [],
    }
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
    if plan_changed and turn_meta and turn_meta.get("mode") == "plan":
        trigger = (
            "synthesize_only"
            if turn_meta.get("synthesize_only")
            else "plan_turn"
        )
        run_meta["last_plan_update"] = {
            "ts": turn_meta.get("completed_at") or turn_meta.get("ts") or _now(),
            "trigger": trigger,
            "mode": "plan",
            "synthesize_only": bool(turn_meta.get("synthesize_only")),
            "request_id": turn_meta.get("request_id"),
            "started_at": turn_meta.get("started_at"),
            "completed_at": turn_meta.get("completed_at"),
            "agents": turn_meta.get("agents") or agents_used or [],
            "message_count": len(messages),
            "chat_from_line": 1,
            "chat_to_line": len(messages),
            "status": turn_meta.get("status", "completed"),
        }
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
    request_id: str | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    review_mode: bool = False,
    review_advocate: str | None = None,
    context_log: list[dict[str, Any]] | None = None,
    consensus_mode: bool = False,
    consensus: dict[str, Any] | None = None,
    efficiency_mode: bool = False,
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
    return snap


def synthesize_session_plan(
    folder: Path,
    *,
    on_event: OnAgentEvent | None = None,
    permissions: dict | None = None,
    request_id: str | None = None,
) -> str:
    """Re-synthesize plan.md from existing chat without a new agent round."""
    if not folder.is_dir():
        raise FileNotFoundError(f"session not found: {folder}")
    if request_id and _find_completed_synthesize(folder, request_id):
        plan_path = folder / "plan.md"
        if plan_path.is_file():
            if on_event:
                on_event("scribe_skipped", {"reason": "duplicate_request_id"})
            return plan_path.read_text(encoding="utf-8")
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
        if on_event:
            on_event("scribe_done", {"chars": len(plan_md)})
    except Exception as e:
        if on_event:
            on_event("scribe_error", {"message": str(e)})
        raise
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
            request_id=request_id,
            started_at=started_at,
            completed_at=completed_at,
        ),
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
    active_agents = [a for a in (agents or available_agents())]
    mode = "plan" if synthesize else "discuss"
    review_advocate = (
        _review_advocate(active_agents, human_turn_index)
        if review_mode and active_agents
        else None
    )
    plan_md, run_meta = _session_context(folder)
    t0 = time.perf_counter()
    context_log: list[dict[str, Any]] = []
    consensus_meta: dict[str, Any] | None = None
    replies: list[ChatMessage] = []
    cancelled = False
    try:
        if consensus_mode:
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
    plan_md = ""
    if (folder / "plan.md").is_file():
        plan_md = (folder / "plan.md").read_text(encoding="utf-8")
    if synthesize and not cancelled:
        if on_event:
            on_event("scribe_start", {})
        try:
            plan_md = synthesize_plan(topic, messages)
            if on_event:
                on_event("scribe_done", {"chars": len(plan_md)})
        except Exception as e:
            if on_event:
                on_event("scribe_error", {"message": str(e)})
    latency_ms = int((time.perf_counter() - t0) * 1000)
    existing_meta: dict[str, Any] = {}
    meta_path = folder / "meta.json"
    if meta_path.is_file():
        try:
            existing_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
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
            status="cancelled" if cancelled else "completed",
            review_mode=review_mode,
            review_advocate=review_advocate,
            context_log=context_log,
            consensus_mode=consensus_mode,
            consensus=consensus_meta,
            efficiency_mode=efficiency_mode,
        ),
    )
    if on_event:
        on_event(
            "complete",
            {
                "session_id": folder.name,
                "path": str(folder),
                "cancelled": cancelled,
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
) -> tuple[Path, list[ChatMessage], str]:
    """Full room flow: user message → parallel agents → optional plan synthesis."""
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
    t0 = time.perf_counter()
    context_log: list[dict[str, Any]] = []
    consensus_meta: dict[str, Any] | None = None
    replies: list[ChatMessage] = []
    cancelled = False
    try:
        if consensus_mode:
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
            if on_event:
                on_event("scribe_done", {"chars": len(plan_md)})
        except Exception as e:
            plan_md = f"## Plan synthesis failed\n\n{e}"
            if on_event:
                on_event("scribe_error", {"message": str(e)})

    latency_ms = int((time.perf_counter() - t0) * 1000)
    turn_meta = _turn_snapshot(
        mode=mode,
        synthesize=synthesize,
        agents_used=active_agents,
        parallel_rounds=parallel_rounds,
        permissions=permissions,
        latency_ms=latency_ms,
        status="cancelled" if cancelled else "completed",
        review_mode=review_mode,
        review_advocate=review_advocate,
        context_log=context_log,
        consensus_mode=consensus_mode,
        consensus=consensus_meta,
        efficiency_mode=efficiency_mode,
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
    if on_event:
        on_event(
            "complete",
            {
                "session_id": folder.name,
                "path": str(folder),
                "cancelled": cancelled,
            },
        )
    return folder, messages, plan_md
