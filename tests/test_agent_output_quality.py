from __future__ import annotations

from agent_lab.room.chat_channels import strip_sdk_internal_monologue
from agent_lab.room.messages import ChatMessage
from agent_lab.room.session_persist import _append_human_turn_synthesis


def test_strip_sdk_internal_monologue() -> None:
    raw = (
        "prepare_turn_policy_before_agent_round...\n"
        "I am ready to act on your request.\n"
        "Actual answer for the human."
    )
    assert "prepare_turn_policy" not in strip_sdk_internal_monologue(raw)
    assert "I am ready to act" not in strip_sdk_internal_monologue(raw)
    assert "Actual answer" in strip_sdk_internal_monologue(raw)


def test_synthesis_lead_uses_turn_meta_not_stale_team_lead() -> None:
    run_meta = {
        "team_lead": "codex",
        "turn_leads": {"1": "cursor", "2": "claude"},
    }
    turn_meta = {"turn_lead": "claude", "human_turn": 2, "turn_profile": "free"}
    messages = [
        ChatMessage(role="user", agent=None, content="topic"),
        ChatMessage(role="agent", agent="cursor", content="peer view"),
        ChatMessage(role="agent", agent="claude", content="review"),
    ]
    out = _append_human_turn_synthesis(messages, run_meta, turn_meta=turn_meta)
    synth = [m for m in out if m.role == "system" and "[human synthesis" in m.content]
    assert synth
    assert "리드: claude" in synth[0].content
