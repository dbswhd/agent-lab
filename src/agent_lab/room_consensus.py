"""Free-discuss consensus helpers (「이의 없습니다」)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from agent_lab.agents.registry import AgentId, label
from agent_lab.agent_envelope import classify_consensus_reply, envelope_act
from agent_lab.room_context import (
    is_no_objection_response,
    is_pass_response,
    is_pure_no_objection,
)

DEFAULT_MAX_CONSENSUS_ROUNDS = 12
DEFAULT_MAX_CONSENSUS_CALLS = 30
DEFAULT_DEBATE_ROUNDS = 4  # R2..R5 (review → expand ×2) before endorse loop

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


def max_debate_round_count(*, efficiency_mode: bool = False) -> int:
    """How many rounds after R1 to run debate (R2..R1+N). 0 = skip debate."""
    if efficiency_mode:
        return min(2, _int_env("AGENT_LAB_EFFICIENCY_DEBATE_ROUNDS", 2))
    raw = os.getenv("AGENT_LAB_DEBATE_ROUNDS", "").strip()
    if raw.isdigit():
        return max(0, int(raw))
    return DEFAULT_DEBATE_ROUNDS


def debate_round_last(*, efficiency_mode: bool = False) -> int:
    """Last parallel_round index in debate phase (inclusive). 1 = no debate."""
    count = max_debate_round_count(efficiency_mode=efficiency_mode)
    if count <= 0:
        return 1
    return min(1 + count, max_consensus_rounds())


def debate_review_round(parallel_round: int) -> bool:
    """R2,R4,… = 반박·재검증; R3,R5,… = 이어가기·확장."""
    return parallel_round >= 2 and parallel_round % 2 == 0


def _int_env(key: str, default: int) -> int:
    raw = (os.getenv(key) or "").strip()
    if raw.isdigit():
        return int(raw)
    return default


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


def is_substantive_reply(
    text: str,
    envelope: dict[str, Any] | None = None,
) -> bool:
    """Prefer envelope act; fall back to phrase heuristics."""
    act = envelope_act(envelope)
    if act in ("ENDORSE", "PASS"):
        return False
    if act in ("PROPOSE", "AMEND", "CHALLENGE", "BLOCK"):
        return True
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
        env = getattr(m, "envelope", None)
        if not is_substantive_reply(m.content, env if isinstance(env, dict) else None):
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


def consensus_follow_up(
    anchor: ConsensusAnchor,
    *,
    open_task_refs: list[str] | None = None,
) -> str:
    task_line = ""
    if open_task_refs:
        joined = ", ".join(open_task_refs[:8])
        task_line = (
            f"\n열린 **작업**에도 동의하면 envelope `refs`에 task id를 넣으세요 "
            f"(예: {joined}).\n"
        )
    return (
        f"[자유 토론 · 합의 확인]\n"
        f"현재 제안 — **{label(anchor.agent)}**:\n"
        f"「{anchor.excerpt}」\n\n"
        f"완전 동의(`act: ENDORSE`)는 추가 제안·리스크·`[PROPOSED:]` 없을 때만. "
        f"보완이 있으면 `act: AMEND` 로 수정안을 쓰세요 (새 앵커 라운드). "
        f"`ENDORSE`/`PASS` 본문은 1줄로 짧게 (fence JSON 필수). "
        f"레거시: envelope 없이면 첫 줄만 `{NO_OBJECTION_LINE}` 도 허용."
        f"{task_line}"
    )


def consensus_reply_verdict(
    text: str,
    envelope: dict | None = None,
) -> str:
    """Return endorse | pass | substantive | neutral for consensus loop."""
    return classify_consensus_reply(text, envelope)
