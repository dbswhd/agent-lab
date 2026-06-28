"""Fast preset guidance — no peer consensus theater."""

from __future__ import annotations

from agent_lab.reply_policy import build_guidance_parts, resolve_reply_policy
from agent_lab.room.context import FAST_TURN_GUIDANCE, agent_tool_rules


def test_quick_profile_skips_peer_coordination_guidance() -> None:
    policy = resolve_reply_policy(turn_profile="quick")
    assert policy.inject_coordination is False
    assert policy.inject_peer_decision is False
    assert policy.inject_conversation is False


def test_fast_session_injects_fast_turn_guidance() -> None:
    policy = resolve_reply_policy(turn_profile="quick")
    parts = build_guidance_parts(policy, run_meta={"room_preset": "fast"})
    assert any(FAST_TURN_GUIDANCE.strip() in p for p in parts)


def test_kimi_fast_tool_rules() -> None:
    rules = agent_tool_rules("kimi_work", {"room_preset": "fast"})
    assert "Fast solo" in rules
    assert "No `[PROPOSED:]`" in rules
    assert agent_tool_rules("kimi_work", {"room_preset": "supervisor"}) != rules
