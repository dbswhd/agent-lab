"""Codex CLI helpers."""

from __future__ import annotations

from agent_lab.codex_cli import codex_event_label


def test_sandbox_mode_room_defaults_read_only():
    from agent_lab.codex_cli import _sandbox_mode

    assert _sandbox_mode(allow_tools=True, room_turn=True) == "read-only"
    assert _sandbox_mode(allow_tools=True, room_turn=False) == "workspace-write"


def test_room_timeout_default(monkeypatch):
    from agent_lab.codex_cli import _room_max_commands, _timeout_sec

    monkeypatch.delenv("CODEX_ROOM_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("CODEX_TIMEOUT_SEC", raising=False)
    assert _timeout_sec(room_turn=True) is None
    monkeypatch.setenv("CODEX_ROOM_TIMEOUT_SEC", "240")
    assert _timeout_sec(room_turn=True) == 240
    assert _room_max_commands() == 6
    label = codex_event_label(
        {
            "type": "item.started",
            "item": {"type": "command_execution", "command": "ls -la"},
        }
    )
    assert label and "ls" in label


def test_peer_decision_in_bundle():
    from agent_lab.agent_permissions import normalize_agent_permissions
    from agent_lab.context_bundle import build_context_bundle

    bundle = build_context_bundle(
        "topic",
        [],
        "claude",
        permissions=normalize_agent_permissions({}),
    )
    text = bundle.render()
    assert "Peer decision" in text
    assert "Do not punt to Human" in text or "Human" in text


def test_extract_agent_message_from_stream_event():
    from agent_lab.codex_cli import _extract_agent_message, _process_codex_event, CodexRunOutcome

    item = {"type": "agent_message", "text": "  hello room  "}
    assert _extract_agent_message(item) == "hello room"

    outcome = CodexRunOutcome()
    limit_at = _process_codex_event(
        {
            "type": "item.completed",
            "item": {"type": "command_execution", "exit_code": 0},
        },
        on_activity=None,
        max_commands=2,
        outcome=outcome,
        limit_hit_at=None,
    )
    assert outcome.commands_done == 1
    assert limit_at is None

    _process_codex_event(
        {
            "type": "item.completed",
            "item": {"type": "command_execution", "exit_code": 0},
        },
        on_activity=None,
        max_commands=2,
        outcome=outcome,
        limit_hit_at=limit_at,
    )
    assert outcome.limit_hit is True
    assert outcome.commands_done == 2

    _process_codex_event(
        {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "final answer"},
        },
        on_activity=None,
        max_commands=2,
        outcome=outcome,
        limit_hit_at=limit_at,
    )
    assert outcome.streamed_message == "final answer"
