"""Room identity for kimi_work Loop discuss/consensus peer."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.agent.permissions import permission_preamble
from agent_lab.agents.prompts import KIMI_WORK_ROOM
from agent_lab.context.bundle import build_context_bundle
from agent_lab.room import ChatMessage
from agent_lab.room.context import AGENT_CONNECT_HINT, agent_tool_rules


def test_kimi_work_connect_hint_and_tool_rules() -> None:
    assert "kimi_work" in AGENT_CONNECT_HINT
    assert "Work peer" in AGENT_CONNECT_HINT["kimi_work"]
    rules = agent_tool_rules("kimi_work")
    assert "ask_human" in rules
    assert "Discuss 턴" in rules


def test_kimi_work_permission_preamble_discuss() -> None:
    block = permission_preamble({"_discuss_mode": True}, "kimi_work")
    assert "Kimi Work runtime" in block
    assert "Discuss 턴" in block


def test_context_bundle_includes_kimi_work_hints() -> None:
    from agent_lab.agent.permissions import permission_preamble

    bundle = build_context_bundle(
        "topic",
        [ChatMessage(role="user", agent=None, content="hi")],
        "kimi_work",
        run_meta={"agents": ["kimi_work", "cursor"]},
        permissions={"_discuss_mode": True},
        permission_lines=permission_preamble({"_discuss_mode": True}, "kimi_work"),
    )
    payload = bundle.render()
    assert AGENT_CONNECT_HINT["kimi_work"][:20] in payload
    assert "Kimi Work tools" in payload
    assert "Kimi Work runtime" in payload


def test_kimi_work_provider_uses_room_system(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.kimi import work_provider as kwp

    captured: dict[str, str] = {}

    def _fake_send_turn(**kwargs: object) -> str:
        captured["system"] = str(kwargs.get("system") or "")
        return "ok"

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setattr(kwp, "send_turn", _fake_send_turn)
    kwp.respond("", "hello", session_folder=tmp_path)
    assert "Kimi Work" in captured.get("system", "")
    assert KIMI_WORK_ROOM.strip()[:40] in captured.get("system", "")


def test_kimi_work_provider_envelope_mirror_on_system(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.kimi import work_provider as kwp

    captured: dict[str, str] = {}

    def _fake_send_turn(**kwargs: object) -> str:
        captured["system"] = str(kwargs.get("system") or "")
        return '{"act":"ENDORSE","refs":[],"confidence":0.9}'

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setattr(kwp, "send_turn", _fake_send_turn)
    kwp.respond("", "probe", session_folder=tmp_path, request_structured_envelope=True)
    system = captured.get("system", "")
    assert "Structured envelope" in system
    assert "Loop consensus envelope" in system
