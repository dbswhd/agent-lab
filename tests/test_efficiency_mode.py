"""Efficiency mode: pin cap, slim consensus bundle, tighter limits."""

from __future__ import annotations

from dataclasses import dataclass

from agent_lab.context_bundle import build_context_bundle, build_slim_consensus_bundle
from agent_lab.context_limits import efficiency_limits
from agent_lab.room_context import cap_pinned_messages, prepare_recent_messages


@dataclass
class _Msg:
    role: str
    agent: str | None
    content: str
    parallel_round: int | None = None


def test_cap_pinned_keeps_human_and_newest_agents():
    human = _Msg("user", None, "question")
    agents = [_Msg("agent", "claude", "a" * 30000, 1) for _ in range(5)]
    pinned = [human, *agents]
    capped, dropped = cap_pinned_messages(
        pinned, max_messages=3, max_chars=50000
    )
    assert human in capped
    assert dropped >= 2
    assert len(capped) <= 3


def test_prepare_recent_efficiency_uses_fewer_turns():
    msgs: list[_Msg] = []
    for i in range(10):
        msgs.append(_Msg("user", None, f"human {i}"))
        msgs.append(_Msg("agent", "codex", f"reply {i}", 1))
    eff_turns = efficiency_limits().recent_turns
    _, turns_std, _, _ = prepare_recent_messages(
        msgs, max_turns=8, efficiency_mode=False
    )
    _, turns_eff, _, _ = prepare_recent_messages(msgs, efficiency_mode=True)
    assert turns_eff >= turns_std
    assert eff_turns <= 8


def test_efficiency_bundle_adds_guidance():
    human = _Msg("user", None, "hello")
    messages = [human, _Msg("agent", "codex", "hi", 1)]
    bundle = build_context_bundle(
        "topic",
        messages,
        "cursor",
        efficiency_mode=True,
    )
    text = bundle.render()
    assert "효율 모드" in text
    assert bundle.meta.efficiency_mode is True


def test_slim_consensus_omits_full_recent_block():
    human = _Msg("user", None, "long " * 500)
    old = _Msg("user", None, "old turn")
    messages = [old, _Msg("agent", "claude", "old reply", 1), human]
    bundle = build_slim_consensus_bundle("topic", messages, "codex")
    text = bundle.render()
    assert bundle.meta.slim_context is True
    assert "[최근 N턴]" not in text
    assert "이번 Human 질문" in text
    assert len(text) < len(human.content) + 8000
