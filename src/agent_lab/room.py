"""Multi-agent room: Cursor + Codex + Claude in parallel (controlled workflow)."""

from __future__ import annotations

import json
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
MAX_ROUNDS_DEFAULT = 1  # one user topic → one parallel round (+ optional scribe)


@dataclass
class ChatMessage:
    role: str  # user | agent | system
    agent: str | None
    content: str
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "agent": self.agent,
            "content": self.content,
            "ts": self.ts,
        }


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


def _agent_user_payload(
    topic: str,
    messages: list[ChatMessage],
    agent: AgentId,
    *,
    permissions: dict | None = None,
) -> str:
    from agent_lab.agent_permissions import permission_preamble

    thread = format_thread(topic, messages)
    extra = permission_preamble(permissions, agent)
    block = (
        f"{thread}\n"
        f"---\n"
        f"Now respond as {label(agent)} only. Others may have spoken; add your distinct view."
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
    on_event: OnAgentEvent | None = None,
    permissions: dict | None = None,
) -> list[ChatMessage]:
    """Call selected agents in parallel for one round."""
    active = agents or available_agents()
    if not active:
        raise RuntimeError(
            "No agents available. Configure CURSOR_API_KEY, codex login, or ANTHROPIC_API_KEY."
        )
    active = active[:MAX_AGENTS_PER_ROUND]

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
                _agent_user_payload(topic, messages, aid, permissions=permissions),
                permissions=permissions,
            ): aid
            for aid in active
        }
        for fut in as_completed(futures):
            aid = futures[fut]
            _emit("agent_start", {"agent": aid})
            try:
                text = fut.result()
                msg = ChatMessage(role="agent", agent=aid, content=text)
                replies.append(msg)
                _emit(
                    "agent_done",
                    {"agent": aid, "chars": len(text), "content": text},
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


def synthesize_plan(
    topic: str,
    messages: list[ChatMessage],
    backend_agent: AgentId = "claude",
) -> str:
    """Scribe pass using one agent backend."""
    thread = format_thread(topic, messages)
    user = f"{thread}\n\n---\n\nWrite the final plan.md content."
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
        messages.append(
            ChatMessage(
                role=data.get("role", "system"),
                agent=data.get("agent"),
                content=data.get("content", ""),
                ts=data.get("ts", _now()),
            )
        )
    return messages


def _write_session_files(
    folder: Path,
    topic: str,
    messages: list[ChatMessage],
    plan_md: str,
    *,
    agents_used: list[str] | None = None,
    merge_meta: dict[str, Any] | None = None,
) -> None:
    (folder / "topic.txt").write_text(topic.strip() + "\n", encoding="utf-8")
    (folder / "plan.md").write_text(plan_md + "\n", encoding="utf-8")

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
    run_meta = {
        "workflow_id": "room.parallel",
        "topic": topic,
        "created_at": created_at,
        "agents": agents_used or [a for a in AGENT_IDS],
        "status": "completed",
        "message_count": len(messages),
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
) -> Path:
    folder = session_dir(topic, base=base or SESSIONS_DIR)
    _write_session_files(
        folder, topic, messages, plan_md, agents_used=agents_used
    )
    return folder


def continue_room_round(
    folder: Path,
    user_message: str,
    *,
    agents: list[AgentId] | None = None,
    synthesize: bool = False,
    on_event: OnAgentEvent | None = None,
    permissions: dict | None = None,
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
    messages.append(ChatMessage(role="user", agent=None, content=body))
    replies = run_parallel_round(
        topic, messages, agents=agents, on_event=on_event, permissions=permissions
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
        agents_used=[a for a in (agents or available_agents())],
        merge_meta={**existing_meta, "topic": topic},
    )
    return messages, plan_md


def run_room(
    topic: str,
    *,
    agents: list[AgentId] | None = None,
    synthesize: bool = True,
    on_event: OnAgentEvent | None = None,
    sessions_base: Path | None = None,
    session_folder: Path | None = None,
    permissions: dict | None = None,
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

    replies = run_parallel_round(
        topic, messages, agents=agents, on_event=on_event, permissions=permissions
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

    if folder is None:
        folder = save_room_session(
            topic,
            messages,
            plan_md,
            base=sessions_base,
            agents_used=[a for a in (agents or available_agents())],
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
            agents_used=[a for a in (agents or available_agents())],
            merge_meta=existing_meta,
        )
    if on_event:
        on_event("complete", {"session_id": folder.name, "path": str(folder)})
    return folder, messages, plan_md
