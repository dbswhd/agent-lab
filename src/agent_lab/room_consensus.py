"""Free-discuss consensus helpers (「이의 없습니다」)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from agent_lab.agents.registry import AgentId, label
from agent_lab.room_context import (
    is_no_objection_response,
    is_pass_response,
    is_pure_no_objection,
)

DEFAULT_MAX_CONSENSUS_ROUNDS = 12
DEFAULT_MAX_CONSENSUS_CALLS = 30

NO_OBJECTION_LINE = "이의 없습니다"


def max_consensus_rounds() -> int:
    raw = os.getenv("AGENT_LAB_MAX_CONSENSUS_ROUNDS", "").strip()
    if raw.isdigit():
        return max(1, int(raw))
    return DEFAULT_MAX_CONSENSUS_ROUNDS


def max_consensus_calls() -> int:
    raw = os.getenv("AGENT_LAB_MAX_CONSENSUS_CALLS", "").strip()
    if raw.isdigit():
        return max(3, int(raw))
    return DEFAULT_MAX_CONSENSUS_CALLS


def consensus_caps(*, efficiency_mode: bool = False) -> tuple[int, int]:
    """(max_rounds, max_calls) for consensus loop."""
    if efficiency_mode:
        from agent_lab.context_limits import efficiency_limits

        eff = efficiency_limits()
        return eff.max_consensus_rounds, eff.max_consensus_calls
    return max_consensus_rounds(), max_consensus_calls()


@dataclass
class ConsensusAnchor:
    agent: AgentId
    excerpt: str
    parallel_round: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "excerpt": self.excerpt,
            "parallel_round": self.parallel_round,
        }


def is_substantive_reply(text: str) -> bool:
    if not (text or "").strip():
        return False
    if is_pass_response(text) or is_pure_no_objection(text):
        return False
    return True


def _anchor_excerpt(content: str, *, max_len: int = 280) -> str:
    body = (content or "").strip()
    if not body:
        return ""
    first = body.splitlines()[0].strip()
    if len(first) >= 40:
        return first[:max_len]
    compact = " ".join(body.split())
    if len(compact) > max_len:
        return compact[: max_len - 1] + "…"
    return compact


def pick_anchor(
    turn_messages: list[Any],
    active_agents: list[AgentId],
) -> ConsensusAnchor | None:
    """Latest substantive agent reply in the current human turn."""
    active = set(active_agents)
    for m in reversed(turn_messages):
        if m.role != "agent" or not m.agent or m.agent not in active:
            continue
        if not is_substantive_reply(m.content):
            continue
        excerpt = _anchor_excerpt(m.content)
        if not excerpt:
            continue
        return ConsensusAnchor(
            agent=m.agent,
            excerpt=excerpt,
            parallel_round=m.parallel_round or 1,
        )
    return None


def consensus_follow_up(anchor: ConsensusAnchor) -> str:
    return (
        f"[자유 토론 · 합의 확인]\n"
        f"현재 제안 — **{label(anchor.agent)}**:\n"
        f"「{anchor.excerpt}」\n\n"
        f"이 제안에 **추가 제안·수정·리스크가 전혀 없고** 그대로 받아들일 때만, "
        f"응답 **첫 줄에만** 정확히 `{NO_OBJECTION_LINE}` 를 쓰세요. "
        f"동의하면서 보완·`[PROPOSED: …]`·단계를 덧붙이려면 `{NO_OBJECTION_LINE}` 를 쓰지 말고 "
        "수정안을 구체적으로 쓰세요 (새 앵커 라운드로 이어집니다)."
    )
