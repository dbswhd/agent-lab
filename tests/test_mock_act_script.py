"""Scripted mock envelope acts (AGENT_LAB_MOCK_ACT_SCRIPT) — P1 infra."""

from __future__ import annotations

import json
from pathlib import Path

from agent_lab.agent.envelope import parse_agent_response_v2
from agent_lab.agents.registry import (
    call_agent,
    call_agent_reply,
    reset_mock_act_script_cursors,
)


def _write_script(tmp_path: Path, script: dict) -> Path:
    path = tmp_path / "acts.json"
    path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
    return path


def test_scripted_mock_follows_sequence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    script = {
        "cursor": [
            {"act": "PROPOSE", "refs": [], "body": "sqlite 제안"},
            {"act": "AMEND", "refs": ["L2"], "body": "retry 추가"},
        ],
    }
    monkeypatch.setenv("AGENT_LAB_MOCK_ACT_SCRIPT", str(_write_script(tmp_path, script)))
    reset_mock_act_script_cursors()

    first = call_agent_reply("cursor", "sys", "topic")
    assert first.structured_envelope is not None
    assert first.structured_envelope["act"] == "PROPOSE"
    assert "sqlite 제안" in first.text

    second = call_agent_reply("cursor", "sys", "topic")
    assert second.structured_envelope is not None
    assert second.structured_envelope["act"] == "AMEND"
    assert second.structured_envelope["refs"] == ["L2"]


def test_scripted_mock_endorse_fallback_when_exhausted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    script = {"codex": [{"act": "CHALLENGE", "body": "이 가정은 약합니다"}]}
    monkeypatch.setenv("AGENT_LAB_MOCK_ACT_SCRIPT", str(_write_script(tmp_path, script)))
    reset_mock_act_script_cursors()

    first = call_agent_reply("codex", "sys", "topic")
    assert first.structured_envelope is not None
    assert first.structured_envelope["act"] == "CHALLENGE"

    second = call_agent_reply("codex", "sys", "topic")
    assert second.structured_envelope is not None
    assert second.structured_envelope["act"] == "ENDORSE"


def test_scripted_mock_unlisted_agent_uses_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.delenv("AGENT_LAB_MOCK_STRUCTURED_ENVELOPE", raising=False)
    script = {"cursor": [{"act": "PROPOSE"}]}
    monkeypatch.setenv("AGENT_LAB_MOCK_ACT_SCRIPT", str(_write_script(tmp_path, script)))
    reset_mock_act_script_cursors()

    reply = call_agent("claude", "sys", "topic")
    assert reply.startswith("[mock:Claude] ACK")


def test_scripted_mock_parses_as_envelope(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    script = {"claude": [{"act": "BLOCK", "refs": ["plan_action:1"], "body": "보안 위험"}]}
    monkeypatch.setenv("AGENT_LAB_MOCK_ACT_SCRIPT", str(_write_script(tmp_path, script)))
    reset_mock_act_script_cursors()

    reply = call_agent_reply("claude", "sys", "topic")
    parsed = parse_agent_response_v2(reply.text, structured=reply.structured_envelope)
    assert parsed.envelope is not None
    assert parsed.envelope.act == "BLOCK"
    assert parsed.envelope.refs == ["plan_action:1"]
    assert "보안 위험" in parsed.body
