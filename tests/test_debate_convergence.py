"""Debate convergence gate — interview-style scoring for Room debate pacing."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_lab.consensus_policy import default_consensus_policy
from agent_lab.debate_convergence import (
    debate_convergence_gate_enabled,
    score_debate_convergence,
    should_advance_debate,
    should_advance_endorse,
)


def _msg(agent: str, act: str, *, parallel_round: int = 1):
    return SimpleNamespace(
        role="agent",
        agent=agent,
        content="body",
        envelope={"act": act, "refs": []},
        parallel_round=parallel_round,
    )


def test_gate_default_off(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AGENT_LAB_DEBATE_CONVERGENCE_GATE", raising=False)
    assert debate_convergence_gate_enabled() is False


def test_gate_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_DEBATE_CONVERGENCE_GATE", "1")
    assert debate_convergence_gate_enabled() is True


def test_high_convergence_when_support_and_no_conflicts():
    msgs = [
        _msg("cursor", "PROPOSE", parallel_round=1),
        _msg("codex", "ENDORSE", parallel_round=2),
        _msg("claude", "ENDORSE", parallel_round=2),
    ]
    result = score_debate_convergence(
        msgs,
        active_agents=["cursor", "codex", "claude"],
        run_meta={"objections": []},
        human_turn=1,
    )
    assert result["convergence"] >= 0.75
    assert result["met"] is True


def test_low_convergence_when_recent_challenge():
    msgs = [
        _msg("cursor", "PROPOSE", parallel_round=1),
        _msg("codex", "CHALLENGE", parallel_round=2),
        _msg("claude", "AMEND", parallel_round=2),
    ]
    result = score_debate_convergence(
        msgs,
        active_agents=["cursor", "codex", "claude"],
        run_meta={"objections": []},
        human_turn=1,
    )
    assert result["convergence"] < 0.75
    assert result["met"] is False


def test_open_objections_block_advance(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_DEBATE_CONVERGENCE_GATE", "1")
    result = {"met": True}
    run_meta = {
        "objections": [
            {"id": "o1", "status": "open", "turn": 1, "act": "CHALLENGE", "from": "codex"},
        ]
    }
    ok, reason = should_advance_debate(result, run_meta, human_turn=1, debate_round=2)
    assert ok is False
    assert reason == "open_objections"


def test_should_advance_debate_when_met(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_DEBATE_CONVERGENCE_GATE", "1")
    ok, reason = should_advance_debate({"met": True}, {}, human_turn=1, debate_round=2)
    assert ok is True
    assert reason == "convergence_threshold"


def test_should_advance_endorse_requires_min_endorse(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_DEBATE_CONVERGENCE_GATE", "1")
    policy = default_consensus_policy()
    ok, _ = should_advance_endorse(
        {"met": True},
        {},
        human_turn=1,
        endorse_count=1,
        active_agents=["cursor", "codex", "claude"],
        min_endorse_agents=policy.min_endorse_agents,
    )
    assert ok is False
    ok2, reason2 = should_advance_endorse(
        {"met": True},
        {},
        human_turn=1,
        endorse_count=2,
        active_agents=["cursor", "codex", "claude"],
        min_endorse_agents=policy.min_endorse_agents,
    )
    assert ok2 is True
    assert reason2 == "convergence_threshold"


def test_policy_convergence_exit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_DEBATE_CONVERGENCE_GATE", "1")
    policy = default_consensus_policy()
    ok, reason = policy.should_exit_round(
        consensus_status=None,
        endorse_count=2,
        active_agents=["cursor", "codex", "claude"],
        calls=5,
        max_calls=30,
        rounds=3,
        max_rounds=12,
        convergence_result={"met": True},
        run_meta={},
        human_turn=1,
    )
    assert ok is True
    assert reason == "convergence_threshold"
