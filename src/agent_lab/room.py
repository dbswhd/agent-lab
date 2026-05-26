"""Multi-agent room: Cursor + Codex + Claude in parallel (controlled workflow)."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent_lab.agents.prompts import ROOM_SCRIBE
from agent_lab.agents.registry import AGENT_IDS, AgentId, available_agents, call_agent, label
from agent_lab.attachments import describe_attachments
from agent_lab.session import SESSIONS_DIR, session_dir

MAX_AGENTS_PER_ROUND = 3
MAX_AGENT_PARALLEL_ROUNDS = 4  # per human message
DEFAULT_AGENT_PARALLEL_ROUNDS = 2  # round 1 → all reply; round 2+ see prior agent messages


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


def _agent_user_payload(
    topic: str,
    messages: list[ChatMessage],
    agent: AgentId,
    *,
    permissions: dict | None = None,
    parallel_round: int = 1,
    review_mode: bool = False,
    review_advocate: AgentId | None = None,
) -> str:
    from agent_lab.agent_permissions import permission_preamble

    thread = format_thread(topic, messages)
    extra = permission_preamble(permissions, agent)
    has_peer_agents = any(m.role == "agent" and m.agent and m.agent != agent for m in messages)
    block = (
        f"{thread}\n"
        f"---\n"
        f"Now respond as {label(agent)} only. Others may have spoken; add your distinct view."
    )
    if has_peer_agents:
        block = (
            f"{block}\n"
            "This is a follow-up in the same turn: read what the other assistants said above. "
            "Reply to them directly — name at least one (Cursor, Codex, or Claude) and respond "
            "to a specific point they made. Write at least 2 sentences; do not skip this turn. "
            "Do not repeat your earlier intro or restate the whole thread.\n"
            "If any claim from round 1 rests on a weak or unverified assumption, name one explicitly. "
            "Do not agree by default — include at least one risk or counterexample if relevant."
        )
        if review_mode and parallel_round >= 2 and review_advocate:
            if agent == review_advocate:
                block = (
                    f"{block}\n"
                    "[쟁점 검토 모드 — 반박 담당]\n"
                    "1라운드에서 나온 주장 중 가장 약한 가정 하나를 선택해 명시적으로 반박하라.\n"
                    "단순 동의+보완은 금지. 반박 근거가 없으면 "
                    '"검증 필요: {이유}" 형식으로 표시.'
                )
            else:
                block = (
                    f"{block}\n"
                    f"[쟁점 검토 모드 — 방어/검토]\n"
                    f"{label(review_advocate)}의 반박을 받아, 해당 약점을 인정하거나 "
                    "반론 근거를 제시하라."
                )
        elif parallel_round >= 2:
            block = (
                f"{block}\n"
                "1라운드에서 나온 주장 중 가장 약하거나 검증되지 않은 가정이 있다면 "
                "하나를 명시적으로 짚어라.\n"
                "동의만 하지 말고, 리스크나 반례가 있으면 한 문장이라도 포함할 것."
            )
    if extra:
        block = f"{block}\n\n{extra}"
    return block


OnAgentEvent = Callable[[str, dict[str, Any]], None]
# event types: agent_start, agent_done, agent_error


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
) -> list[ChatMessage]:
    """Call selected agents in parallel for one round."""
    active = agents or available_agents()
    if not active:
        raise RuntimeError(
            "No agents available. Configure CURSOR_API_KEY, codex login, or claude login."
        )
    active = active[:MAX_AGENTS_PER_ROUND]
    review_advocate = (
        _review_advocate(active, human_turn_index) if review_mode else None
    )

    replies: list[ChatMessage] = []

    def _emit(typ: str, payload: dict[str, Any]) -> None:
        if on_event:
            on_event(typ, payload)

    with ThreadPoolExecutor(max_workers=len(active)) as pool:
        futures = {
            pool.submit(
                call_agent,
                aid,
                "",
                _agent_user_payload(
                    topic,
                    messages,
                    aid,
                    permissions=permissions,
                    parallel_round=parallel_round,
                    review_mode=review_mode,
                    review_advocate=review_advocate,
                ),
                permissions=permissions,
            ): aid
            for aid in active
        }
        for fut in as_completed(futures):
            aid = futures[fut]
            _emit("agent_start", {"agent": aid, "round": parallel_round})
            try:
                text = fut.result()
                msg = ChatMessage(
                    role="agent",
                    agent=aid,
                    content=text,
                    parallel_round=parallel_round,
                )
                replies.append(msg)
                _emit(
                    "agent_done",
                    {
                        "agent": aid,
                        "chars": len(text),
                        "content": text,
                        "round": parallel_round,
                    },
                )
            except Exception as e:
                _emit("agent_error", {"agent": aid, "message": str(e)})
                replies.append(
                    ChatMessage(
                        role="system",
                        agent=aid,
                        content=f"[{label(aid)} error] {e}",
                    )
                )
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
) -> list[ChatMessage]:
    """Run multiple parallel waves; later waves see earlier agents' replies in the thread."""
    n = max(1, min(parallel_rounds, MAX_AGENT_PARALLEL_ROUNDS))
    all_replies: list[ChatMessage] = []
    for r in range(1, n + 1):
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
        )
        all_replies.extend(batch)
    return all_replies


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
    backend_agent: AgentId = "claude",
) -> str:
    """Scribe pass using one agent backend."""
    numbered = format_thread_numbered(messages)
    user = (
        f"Human topic:\n{topic.strip()}\n\n"
        f"---\n\nNumbered conversation (use L{{n}} as chat.jsonl#L{{n}} refs):\n\n"
        f"{numbered}\n\n---\n\nWrite the final plan.md content."
    )
    return call_agent(backend_agent, ROOM_SCRIBE, user)


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
        "topic": topic,
        "created_at": created_at,
        "agents": agents_used or [a for a in AGENT_IDS],
        "status": turn_meta.get("status", "completed") if turn_meta else "completed",
        "message_count": len(messages),
        "agent_parallel_rounds": agent_parallel_rounds,
        "turns": turns,
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
    t0 = time.perf_counter()
    replies = run_agent_rounds(
        topic,
        messages,
        agents=agents,
        parallel_rounds=parallel_rounds,
        on_event=on_event,
        permissions=permissions,
        review_mode=review_mode,
        human_turn_index=human_turn_index,
    )
    messages.extend(replies)
    plan_md = ""
    if (folder / "plan.md").is_file():
        plan_md = (folder / "plan.md").read_text(encoding="utf-8")
    if synthesize:
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
            review_mode=review_mode,
            review_advocate=review_advocate,
        ),
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
    t0 = time.perf_counter()
    replies = run_agent_rounds(
        topic,
        messages,
        agents=agents,
        parallel_rounds=parallel_rounds,
        on_event=on_event,
        permissions=permissions,
        review_mode=review_mode,
        human_turn_index=max(0, human_turn_index),
    )
    messages.extend(replies)

    plan_md = ""
    if synthesize:
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
        review_mode=review_mode,
        review_advocate=review_advocate,
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
        on_event("complete", {"session_id": folder.name, "path": str(folder)})
    return folder, messages, plan_md
