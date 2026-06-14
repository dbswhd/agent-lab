"""Codex CLI helpers."""

from __future__ import annotations

from pathlib import Path

import pytest


from agent_lab.codex_cli import codex_event_label


def test_sandbox_mode_room_defaults_read_only():
    from agent_lab.codex_cli import _sandbox_mode

    assert _sandbox_mode(allow_tools=True, room_turn=True) == "read-only"
    assert _sandbox_mode(allow_tools=True, room_turn=False) == "workspace-write"


def test_room_timeout_default(monkeypatch):
    from agent_lab.codex_cli import (
        _idle_timeout_sec,
        _room_max_commands,
        _timeout_sec,
    )

    monkeypatch.delenv("CODEX_ROOM_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("CODEX_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("CODEX_ROOM_IDLE_TIMEOUT_SEC", raising=False)
    assert _timeout_sec(room_turn=True) is None
    assert _idle_timeout_sec(room_turn=True) == 600
    assert _idle_timeout_sec(room_turn=False) is None
    monkeypatch.setenv("CODEX_ROOM_TIMEOUT_SEC", "240")
    assert _timeout_sec(room_turn=True) == 240
    monkeypatch.setenv("CODEX_ROOM_IDLE_TIMEOUT_SEC", "0")
    assert _idle_timeout_sec(room_turn=True) is None
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


def test_codex_mcp_tool_call_event_labels():
    started = codex_event_label(
        {
            "type": "item.started",
            "item": {
                "type": "mcp_tool_call",
                "server": "agent-lab-inbox",
                "tool": "ask_human",
                "status": "in_progress",
            },
        }
    )
    assert started == "Human Inbox: question"

    completed = codex_event_label(
        {
            "type": "item.completed",
            "item": {
                "type": "mcp_tool_call",
                "server": "agent-lab-inbox",
                "tool": "propose_build",
                "status": "completed",
            },
        }
    )
    assert completed == "Human Inbox: GO decision"

    failed = codex_event_label(
        {
            "type": "item.completed",
            "item": {
                "type": "mcp_tool_call",
                "tool": "search",
                "server": "docs",
                "status": "failed",
                "error": {"message": "tool timeout"},
            },
        }
    )
    assert failed == "MCP failed: tool timeout"


def test_build_cmd_includes_inbox_mcp_overrides(tmp_path: Path):
    from agent_lab.codex_cli import _build_cmd
    from agent_lab.cursor_inbox_mcp import build_codex_inbox_mcp_config_args

    session_folder = tmp_path / "sess"
    session_folder.mkdir()
    overrides = build_codex_inbox_mcp_config_args(session_folder)
    cmd = _build_cmd(
        codex="/usr/bin/codex",
        cwd="/tmp/ws",
        out_path="/tmp/out.txt",
        allow_tools=True,
        room_turn=False,
        stream_json=True,
        config_overrides=overrides,
    )
    assert "--json" in cmd
    assert "agent_lab.inbox_mcp_server" in " ".join(cmd)


def test_run_codex_idle_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from agent_lab import codex_cli

    hang = tmp_path / "hang.sh"
    hang.write_text("#!/bin/sh\nsleep 120\n", encoding="utf-8")
    hang.chmod(0o755)
    monkeypatch.setenv("CODEX_ROOM_IDLE_TIMEOUT_SEC", "2")
    monkeypatch.setattr(
        "agent_lab.run_control.register_child_process",
        lambda _proc: None,
    )
    monkeypatch.setattr(
        "agent_lab.run_control.unregister_child_process",
        lambda _proc: None,
    )
    monkeypatch.setattr("agent_lab.run_control.is_cancelled", lambda: False)

    with pytest.raises(RuntimeError, match="no JSONL/stderr activity"):
        codex_cli._run_codex(
            [str(hang), "-"],
            "prompt",
            on_activity=None,
            timeout=None,
            room_turn=True,
        )


def test_run_codex_drains_stderr_while_waiting(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from agent_lab import codex_cli

    script = tmp_path / "stderr_flood.sh"
    script.write_text(
        "#!/bin/sh\n"
        "i=0\n"
        'while [ "$i" -lt 400 ]; do\n'
        '  echo "progress $i" >&2\n'
        "  i=$((i+1))\n"
        "done\n"
        'echo \'{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}\'\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("CODEX_ROOM_IDLE_TIMEOUT_SEC", "30")
    monkeypatch.setattr(
        "agent_lab.run_control.register_child_process",
        lambda _proc: None,
    )
    monkeypatch.setattr(
        "agent_lab.run_control.unregister_child_process",
        lambda _proc: None,
    )
    monkeypatch.setattr("agent_lab.run_control.is_cancelled", lambda: False)

    outcome = codex_cli._run_codex(
        [str(script), "-"],
        "prompt",
        on_activity=None,
        timeout=None,
        room_turn=True,
    )
    assert outcome.streamed_message == "ok"
    assert "progress" in outcome.stderr
    assert outcome.json_events == 1
