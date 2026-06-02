"""Scribe synthesize_plan input uses agent summaries (H1)."""

from __future__ import annotations

from unittest.mock import patch

from agent_lab.room import ChatMessage, synthesize_plan
from agent_lab.room_scribe_enrichment import (
    extract_agent_turn_summaries,
    format_scribe_agent_summaries_block,
)


def test_summaries_exclude_long_verbatim_body():
    long_body = "x" * 2000 + "\n- bullet one\n- bullet two"
    msgs = [
        ChatMessage(role="user", agent=None, content="topic"),
        ChatMessage(
            role="agent",
            agent="codex",
            content=f"```agent-envelope\n{{\"act\": \"CHALLENGE\", \"refs\": [\"plan_action:1\"]}}\n```\n{long_body}",
            envelope={"act": "CHALLENGE", "refs": ["plan_action:1"]},
        ),
    ]
    rows = extract_agent_turn_summaries(msgs)
    assert len(rows) == 1
    assert rows[0].get("act") == "CHALLENGE"
    text = rows[0].get("text") or ""
    assert "x" * 500 not in text
    assert "CHALLENGE" in text


def test_block_challenge_captured_in_summary():
    msgs = [
        ChatMessage(role="user", agent=None, content="q"),
        ChatMessage(
            role="agent",
            agent="claude",
            content="```agent-envelope\n{\"act\": \"BLOCK\", \"refs\": [\"plan_action:2\"]}\n```\n수치 근거 없음",
            envelope={"act": "BLOCK", "refs": ["plan_action:2"]},
        ),
    ]
    block = format_scribe_agent_summaries_block(msgs)
    assert "BLOCK" in block
    assert "plan_action:2" in block
    assert "L2" in block


@patch("agent_lab.room.call_agent", return_value="# plan")
def test_synthesize_plan_user_payload_uses_summaries(mock_call):
    msgs = [
        ChatMessage(role="user", agent=None, content="build feature"),
        ChatMessage(role="agent", agent="codex", content="verify tests first"),
        ChatMessage(
            role="agent",
            agent="claude",
            content="risk: scope creep",
        ),
    ]
    synthesize_plan("my topic", msgs, run_meta={})
    assert mock_call.called
    user_payload = mock_call.call_args[0][2]
    assert "Agent summaries" in user_payload
    assert "Full verbatim agent replies omitted" in user_payload
    assert "Numbered conversation (fallback" not in user_payload
    assert "verify tests" in user_payload or "Codex" in user_payload


@patch("agent_lab.room.call_agent", return_value="# plan")
def test_synthesize_plan_fallback_without_agent_replies(mock_call):
    msgs = [ChatMessage(role="user", agent=None, content="solo human")]
    synthesize_plan("topic", msgs, run_meta={})
    user_payload = mock_call.call_args[0][2]
    assert "fallback" in user_payload.lower() or "Numbered conversation" in user_payload
