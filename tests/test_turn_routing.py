"""Tests for room/turn_routing.py — shared route wiring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_mocks import patch_call_agent_reply

from agent_lab.room.turn_routing import bootstrap_turn_route, prepare_turn_routing, refresh_routing_after_escalation
from agent_lab.topic_router import escalate_route


def _clear_router_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "AGENT_LAB_TOPIC_ROUTER",
        "AGENT_LAB_DEBATE_ROUNDS",
        "AGENT_LAB_MAX_CONSENSUS_ROUNDS",
        "AGENT_LAB_MAX_CONSENSUS_CALLS",
        "AGENT_LAB_CLARIFIER_MIN_CHARS",
        "AGENT_LAB_CLARIFIER",
    ):
        monkeypatch.delenv(key, raising=False)


def _envelope_reply(act: str, body: str) -> str:
    env = json.dumps({"act": act, "refs": [], "confidence": 0.9})
    return f"```agent-envelope\n{env}\n```\n{body}"


@pytest.fixture
def run_meta() -> dict:
    return {
        "turn_profile": "analyze",
        "room_preset": "supervisor",
        "session_template": "general",
    }


def test_prepare_turn_routing_sets_roles_and_topology(monkeypatch, run_meta):
    monkeypatch.setenv("AGENT_LAB_TOPIC_ROUTER", "1")
    monkeypatch.setenv("AGENT_LAB_ROOM_ROLES", "1")
    topic = (
        "로그인 API 구현해줘 — FastAPI 엔드포인트와 JWT 토큰 검증 로직을 추가해야 합니다."
    )
    result = prepare_turn_routing(
        topic,
        run_meta,
        ["cursor", "codex", "claude"],
        min_agents=1,
    )
    assert result.route.topology == "producer_reviewer"
    assert run_meta.get("_turn_topology") == "producer_reviewer"
    assert run_meta.get("_turn_roles")
    assert "task_type" in (run_meta.get("_turn_category") or {})


def test_refresh_routing_after_escalation_reassigns_roles(monkeypatch, run_meta):
    monkeypatch.setenv("AGENT_LAB_TOPIC_ROUTER", "1")
    monkeypatch.setenv("AGENT_LAB_ROOM_ROLES", "1")
    topic = "[cat:quick] rename typo"
    route = bootstrap_turn_route(topic, run_meta)
    assert route.category == "quick"
    run_meta["_turn_roles"] = {}
    escalated = escalate_route(route, act="CHALLENGE")
    assert escalated.category != "quick"
    refresh_routing_after_escalation(
        escalated,
        run_meta,
        ["cursor", "codex", "claude"],
        topic=topic,
    )
    assert run_meta.get("_turn_roles")


def test_parallel_discuss_persists_topology_and_roles(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Discuss-only (consensus_mode=False) uses prepare_turn_routing and persists category/roles."""
    from agent_lab import room

    _clear_router_env(monkeypatch)
    monkeypatch.setenv("AGENT_LAB_TOPIC_ROUTER", "1")
    monkeypatch.setenv("AGENT_LAB_ROOM_ROLES", "1")
    per_agent: dict[str, int] = {}

    def fake_call_agent(agent, _system, user, **kwargs):
        if kwargs.get("scribe"):
            return "## Plan\n\n- mock\n"
        n = per_agent.get(agent, 0) + 1
        per_agent[agent] = n
        return _envelope_reply("PROPOSE", f"{agent} reply round {n}")

    patch_call_agent_reply(monkeypatch, fake_call_agent)

    topic = (
        "로그인 API 구현해줘 — FastAPI 엔드포인트와 JWT 토큰 검증 로직을 추가해야 합니다."
    )
    folder, _messages, _plan = room.run_room(
        topic,
        agents=["cursor", "codex", "claude"],
        synthesize=False,
        sessions_base=tmp_path,
        consensus_mode=False,
        parallel_rounds=1,
    )
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    turn = run["turns"][0]
    category = turn.get("category") or {}
    assert category.get("topology") == "producer_reviewer"
    assert turn.get("roles")
    assert turn["roles"].get("cursor") == "executor"
