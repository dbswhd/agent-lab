"""Trading Mission token/cost caps — env defaults, turn_budget seeding, telemetry rollup."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agent_lab.mission_board import get_turn_budget, refresh_turn_budget
from agent_lab.run_meta import patch_run_meta, read_run_meta


def _int_env(key: str, default: int) -> int:
    raw = (os.getenv(key) or "").strip()
    if raw.isdigit():
        return int(raw)
    return default


@dataclass(frozen=True)
class TradingMissionBudget:
    """v1 proposal session caps (plan §Phase 3)."""

    max_discuss_rounds: int = 2
    max_parallel_rounds: int = 1
    max_agent_calls_per_human_turn: int = 9
    codex_shell_per_turn: int = 6
    recent_context_turns: int = 2
    max_proposal_retries: int = 1
    codex_room_timeout_sec: int = 600

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def trading_mission_budget() -> TradingMissionBudget:
    return TradingMissionBudget(
        max_discuss_rounds=_int_env("AGENT_LAB_TRADING_DISCUSS_ROUNDS", 2),
        max_parallel_rounds=_int_env("AGENT_LAB_TRADING_PARALLEL_ROUNDS", 1),
        max_agent_calls_per_human_turn=_int_env(
            "AGENT_LAB_TRADING_AGENT_CALLS_CAP", 9
        ),
        codex_shell_per_turn=_int_env("CODEX_ROOM_MAX_COMMANDS", 6),
        recent_context_turns=_int_env("AGENT_LAB_TRADING_RECENT_TURNS", 2),
        max_proposal_retries=_int_env("AGENT_LAB_TRADING_PROPOSAL_RETRIES", 1),
        codex_room_timeout_sec=_int_env("CODEX_ROOM_TIMEOUT_SEC", 600),
    )


def apply_trading_mission_budget_env(
    budget: TradingMissionBudget | None = None,
) -> TradingMissionBudget:
    """Set process env defaults for trading mission (only when unset)."""
    b = budget or trading_mission_budget()

    if not (os.getenv("CODEX_ROOM_MAX_COMMANDS") or "").strip():
        os.environ["CODEX_ROOM_MAX_COMMANDS"] = str(b.codex_shell_per_turn)
    if not (os.getenv("AGENT_LAB_RECENT_TURNS") or "").strip():
        os.environ["AGENT_LAB_RECENT_TURNS"] = str(b.recent_context_turns)
    if not (os.getenv("AGENT_LAB_TRADING_DISCUSS_ROUNDS") or "").strip():
        os.environ["AGENT_LAB_TRADING_DISCUSS_ROUNDS"] = str(b.max_discuss_rounds)
    if not (os.getenv("CODEX_ROOM_TIMEOUT_SEC") or "").strip():
        os.environ["CODEX_ROOM_TIMEOUT_SEC"] = str(b.codex_room_timeout_sec)
    if not (os.getenv("CODEX_TIMEOUT_SEC") or "").strip():
        os.environ["CODEX_TIMEOUT_SEC"] = str(b.codex_room_timeout_sec)

    return b


def resolve_parallel_rounds(requested: int, budget: TradingMissionBudget | None = None) -> int:
    cap = (budget or trading_mission_budget()).max_parallel_rounds
    return max(1, min(int(requested or 1), cap))


def seed_turn_budget_caps(
    session_folder: Path,
    budget: TradingMissionBudget | None = None,
) -> dict[str, Any]:
    """Persist trading caps on run.json turn_budget for UI/telemetry."""
    b = budget or trading_mission_budget()

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        tb = get_turn_budget(run)
        caps = dict(tb.get("caps") or {})
        caps["agent_calls_per_human_turn"] = b.max_agent_calls_per_human_turn
        caps["codex_shell_per_turn"] = b.codex_shell_per_turn
        tb["caps"] = caps
        run["trading_mission_budget"] = b.to_dict()
        run["turn_budget"] = refresh_turn_budget({**run, "turn_budget": tb})
        return run

    patch_run_meta(session_folder, _patch)
    return read_run_meta(session_folder).get("turn_budget") or {}


def turn_budget_telemetry(run: dict[str, Any] | None) -> dict[str, Any]:
    """Extract budget counters for mission_telemetry / token_log."""
    tb = get_turn_budget(run)
    caps = tb.get("caps") if isinstance(tb.get("caps"), dict) else {}
    counters = tb.get("counters") if isinstance(tb.get("counters"), dict) else {}
    mission_budget = (run or {}).get("trading_mission_budget")
    return {
        "budget_pct": tb.get("budget_pct"),
        "budget_overflow": tb.get("overflow"),
        "agent_calls_used": counters.get("agent_calls_per_human_turn"),
        "agent_calls_cap": caps.get("agent_calls_per_human_turn"),
        "codex_shell_used": counters.get("codex_shell_per_turn"),
        "codex_shell_cap": caps.get("codex_shell_per_turn"),
        "caps": caps,
        "trading_mission_budget": mission_budget
        if isinstance(mission_budget, dict)
        else None,
    }
