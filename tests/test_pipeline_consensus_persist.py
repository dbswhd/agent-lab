"""Pipeline dogfood — Room consensus persisted to run.json for consensus_gate."""

from __future__ import annotations

import json

import pytest

from agent_mocks import patch_call_agent_reply


def _envelope_reply(act: str, body: str) -> str:
    env = json.dumps({"act": act, "refs": [], "confidence": 0.9})
    return f"```agent-envelope\n{env}\n```\n{body}"


def test_run_room_persists_run_level_consensus(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from agent_lab import room
    from agent_lab.consensus_gate import consensus_gate_met

    per_agent: dict[str, int] = {}

    def fake_call_agent(agent, _system, user, **kwargs):
        if kwargs.get("scribe"):
            return "## Plan\n\n- mock\n"
        n = per_agent.get(agent, 0) + 1
        per_agent[agent] = n
        if agent == "cursor" and n == 1:
            return _envelope_reply("PROPOSE", "Use src/auth.py JWT middleware.")
        return _envelope_reply("ENDORSE", "Agreed.")

    patch_call_agent_reply(monkeypatch, fake_call_agent)

    folder, _messages, _plan = room.run_room(
        "JWT path in src/auth.py — pick retry strategy.",
        agents=["cursor", "codex", "claude"],
        synthesize=False,
        sessions_base=tmp_path,
        consensus_mode=True,
    )
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert run["turns"][0]["consensus"]["status"] == "reached"
    assert run["consensus"]["status"] == "reached"
    assert run["consensus"]["endorse_count"] >= 2
    assert consensus_gate_met(run)
    ml = run.get("mission_loop") or {}
    if isinstance(ml.get("consensus"), dict):
        assert ml["consensus"]["status"] == "reached"


def test_consensus_gate_falls_back_to_latest_turn() -> None:
    from agent_lab.consensus_gate import consensus_gate_met

    run = {
        "turns": [
            {"consensus": {"status": "incomplete", "agents_consented": ["cursor"]}},
            {"consensus": {"status": "reached", "agents_consented": ["cursor", "codex"]}},
        ]
    }
    assert consensus_gate_met(run)


def test_best_consensus_for_persist_prefers_reached_turn() -> None:
    from agent_lab.consensus_gate import best_consensus_for_persist

    turns = [
        {"consensus": {"status": "reached", "agents_consented": ["cursor", "codex"]}},
        {"consensus": {"status": "incomplete", "agents_consented": []}},
    ]
    snap = best_consensus_for_persist(turns)
    assert snap is not None
    assert snap["status"] == "reached"
    assert snap["endorse_count"] == 2
