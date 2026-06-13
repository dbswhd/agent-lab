"""Tests for Trading Mission token budget caps."""

from __future__ import annotations

import json
import os
from pathlib import Path

from agent_lab.trading_mission.token_budget import (
    TradingMissionBudget,
    apply_trading_mission_budget_env,
    resolve_parallel_rounds,
    seed_turn_budget_caps,
    trading_mission_budget,
    turn_budget_telemetry,
)
from agent_lab.trading_mission.telemetry import build_mission_telemetry


def test_trading_mission_budget_defaults():
    b = trading_mission_budget()
    assert b.max_discuss_rounds == 2
    assert b.codex_shell_per_turn == 6
    assert b.recent_context_turns == 2
    assert b.codex_room_timeout_sec == 600


def test_apply_budget_env_sets_only_when_unset(monkeypatch):
    monkeypatch.delenv("CODEX_ROOM_MAX_COMMANDS", raising=False)
    monkeypatch.delenv("AGENT_LAB_RECENT_TURNS", raising=False)
    monkeypatch.delenv("CODEX_ROOM_TIMEOUT_SEC", raising=False)
    apply_trading_mission_budget_env(
        TradingMissionBudget(codex_shell_per_turn=4, recent_context_turns=2, codex_room_timeout_sec=300)
    )
    assert os.environ["CODEX_ROOM_MAX_COMMANDS"] == "4"
    assert os.environ["AGENT_LAB_RECENT_TURNS"] == "2"
    assert os.environ["CODEX_ROOM_TIMEOUT_SEC"] == "300"


def test_apply_budget_env_respects_existing(monkeypatch):
    monkeypatch.setenv("CODEX_ROOM_MAX_COMMANDS", "9")
    apply_trading_mission_budget_env()
    assert os.environ["CODEX_ROOM_MAX_COMMANDS"] == "9"


def test_resolve_parallel_rounds_caps():
    b = TradingMissionBudget(max_parallel_rounds=1)
    assert resolve_parallel_rounds(3, b) == 1
    assert resolve_parallel_rounds(0, b) == 1


def test_seed_turn_budget_caps(tmp_path: Path):
    session = tmp_path / "sess-budget"
    session.mkdir()
    (session / "run.json").write_text("{}", encoding="utf-8")
    seed_turn_budget_caps(
        session,
        TradingMissionBudget(
            max_agent_calls_per_human_turn=7,
            codex_shell_per_turn=5,
        ),
    )
    run = json.loads((session / "run.json").read_text(encoding="utf-8"))
    assert run["turn_budget"]["caps"]["agent_calls_per_human_turn"] == 7
    assert run["turn_budget"]["caps"]["codex_shell_per_turn"] == 5
    assert run["trading_mission_budget"]["codex_shell_per_turn"] == 5


def test_build_mission_telemetry_includes_budget(tmp_path: Path):
    session = tmp_path / "sess-tel-budget"
    session.mkdir()
    (session / "plan.md").write_text("## 합의\n- discuss_rounds_used: 1\n", encoding="utf-8")
    (session / "run.json").write_text(
        json.dumps(
            {
                "turn_budget": {
                    "caps": {"agent_calls_per_human_turn": 9, "codex_shell_per_turn": 6},
                    "counters": {"agent_calls_per_human_turn": 3, "codex_shell_per_turn": 2},
                    "budget_pct": 33,
                    "overflow": None,
                },
                "trading_mission_budget": {"max_discuss_rounds": 2},
            }
        ),
        encoding="utf-8",
    )
    tel = build_mission_telemetry(session, mission_kind="trading_premarket")
    assert tel["budget_pct"] == 33
    assert tel["agent_calls_used"] == 3
    assert tel["codex_shell_used"] == 2


def test_turn_budget_telemetry_empty():
    assert turn_budget_telemetry({})["agent_calls_used"] == 0
