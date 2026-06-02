"""Cursor SDK activity line formatting."""

from __future__ import annotations

from types import SimpleNamespace

from agent_lab.cursor_activity import format_conversation_step


def test_thinking_message_never_leaks_raw_text():
    step = SimpleNamespace(
        type="thinkingMessage",
        message=SimpleNamespace(
            text="The user wants me to implement all 10 improvements",
            thinking_duration_ms=None,
        ),
    )
    assert format_conversation_step(step) == "Thought briefly"


def test_thinking_message_uses_duration_when_present():
    step = SimpleNamespace(
        type="thinkingMessage",
        message=SimpleNamespace(text="hidden", thinking_duration_ms=5000),
    )
    assert format_conversation_step(step) == "Thought for 5s"
