"""Scoped DELEGATE parsing (Phase G3)."""

from __future__ import annotations

from agent_lab.room_delegate import parse_delegate_from_message


def test_parse_delegate_quoted():
    spec = parse_delegate_from_message('DELEGATE codex: "run backtest only"')
    assert spec == {"agent": "codex", "prompt": "run backtest only"}


def test_parse_delegate_unquoted():
    spec = parse_delegate_from_message("prefix\nDELEGATE claude: summarize risks")
    assert spec is not None
    assert spec["agent"] == "claude"
    assert "risks" in spec["prompt"]


def test_parse_delegate_invalid():
    assert parse_delegate_from_message("hello world") is None
    assert parse_delegate_from_message("DELEGATE unknown: x") is None
