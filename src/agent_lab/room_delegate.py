"""Scoped DELEGATE — single-agent sub-call with artifact (Phase G3)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from agent_lab.agents.registry import AGENT_IDS, AgentId

_DELEGATE_RE = re.compile(
    r"(?:^|\n)\s*DELEGATE\s+(cursor|codex|claude)\s*:\s*"
    r'(?:"([^"]{4,2000})"|([^\n]{4,2000}))',
    re.I | re.M,
)


def parse_delegate_from_message(text: str) -> dict[str, str] | None:
    m = _DELEGATE_RE.search(text or "")
    if not m:
        return None
    agent = m.group(1).strip().lower()
    prompt = (m.group(2) or m.group(3) or "").strip()
    if agent not in AGENT_IDS or len(prompt) < 4:
        return None
    return {"agent": agent, "prompt": prompt}


def run_delegate_turn(
    *,
    topic: str,
    messages: list[Any],
    run_meta: dict[str, Any],
    folder: Path,
    agent: str,
    prompt: str,
    permissions: dict | None,
    on_event: Callable[[str, dict[str, Any]], None] | None = None,
    human_turn: int = 1,
) -> tuple[list[Any], dict[str, Any]]:
    """One agent call; store artifact + peer summary. Replaces full room round."""
    from agent_lab.room import ChatMessage, _call_one_agent, _session_context

    agent_id: AgentId = agent.strip().lower()  # type: ignore[assignment]
    plan_md, _ = _session_context(folder)

    def _emit(typ: str, payload: dict[str, Any]) -> None:
        if on_event:
            on_event(typ, payload)

    _emit("delegate_start", {"agent": agent_id, "prompt": prompt[:200]})
    msg = _call_one_agent(
        agent_id,
        topic=topic,
        thread=messages,
        parallel_round=1,
        permissions=permissions,
        review_mode=False,
        review_advocate=None,
        plan_md=plan_md,
        run_meta=run_meta,
        on_event=on_event,
        extra_follow_up=(
            f"[DELEGATE · scoped task]\n{prompt.strip()}\n\n"
            "이번 호출만 수행하고 결과를 ```artifact 블록 또는 요약으로 반환하세요."
        ),
    )
    from agent_lab.room_artifacts import append_artifact

    body = msg.content or ""
    art = append_artifact(
        run_meta,
        producer=agent_id,
        kind="delegate",
        summary=f"DELEGATE: {prompt[:120]}",
        body=body,
        session_folder=folder,
        human_turn=human_turn,
        parallel_round=1,
        refs=["delegate"],
    )
    peer = ChatMessage(
        role="system",
        agent=None,
        content=(
            f"[delegate · {agent_id}]\n"
            f"task: {prompt[:300]}\n"
            f"artifact: {art.get('id')} — {(art.get('summary') or '')[:200]}"
        ),
        visibility="peer",
        parallel_round=1,
    )
    meta = {
        "agent": agent_id,
        "prompt": prompt,
        "artifact_id": art.get("id"),
        "replaced_full_round": True,
    }
    run_meta["last_delegate"] = meta
    _emit("delegate_done", meta)
    return [msg, peer], meta
