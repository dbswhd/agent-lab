"""Central context budget limits (F12 — stdlib only)."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any


def _int_env(key: str, default: int) -> int:
    raw = (os.getenv(key) or "").strip()
    if raw.isdigit():
        return int(raw)
    return default


def _bool_env(key: str, default: bool = False) -> bool:
    raw = (os.getenv(key) or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


@dataclass(frozen=True)
class AgentContextLimits:
    recent_turns: int
    max_thread_chars: int
    max_agreed_items: int
    max_open_items: int
    max_gate_lines: int
    max_status_tags: int
    numbered_context: bool
    warn_budget_pct: int
    critical_budget_pct: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScribeContextLimits:
    recent_turns: int
    max_chars: int
    full_thread: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def agent_context_limits() -> AgentContextLimits:
    return AgentContextLimits(
        recent_turns=_int_env("AGENT_LAB_RECENT_TURNS", 8),
        max_thread_chars=_int_env("AGENT_LAB_MAX_THREAD_CHARS", 96000),
        max_agreed_items=_int_env("AGENT_LAB_MAX_AGREED_ITEMS", 12),
        max_open_items=_int_env("AGENT_LAB_MAX_OPEN_ITEMS", 14),
        max_gate_lines=_int_env("AGENT_LAB_MAX_GATE_LINES", 12),
        max_status_tags=_int_env("AGENT_LAB_MAX_STATUS_TAGS", 16),
        numbered_context=_bool_env("AGENT_LAB_NUMBERED_CONTEXT", True),
        warn_budget_pct=_int_env("AGENT_LAB_CONTEXT_WARN_PCT", 75),
        critical_budget_pct=_int_env("AGENT_LAB_CONTEXT_CRITICAL_PCT", 90),
    )


def scribe_context_limits() -> ScribeContextLimits:
    return ScribeContextLimits(
        recent_turns=_int_env("AGENT_LAB_SCRIBE_RECENT_TURNS", 12),
        max_chars=_int_env("AGENT_LAB_SCRIBE_MAX_CHARS", 120000),
        full_thread=_bool_env("AGENT_LAB_SCRIBE_FULL", False),
    )


@dataclass(frozen=True)
class EfficiencyLimits:
    recent_turns: int
    max_pin_messages: int
    pin_budget_pct: int
    max_agreed_items: int
    max_open_items: int
    max_reply_chars_hint: int
    max_consensus_rounds: int
    max_consensus_calls: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def efficiency_limits() -> EfficiencyLimits:
    return EfficiencyLimits(
        recent_turns=_int_env("AGENT_LAB_EFFICIENCY_RECENT_TURNS", 4),
        max_pin_messages=_int_env("AGENT_LAB_EFFICIENCY_MAX_PIN_MSGS", 8),
        pin_budget_pct=_int_env("AGENT_LAB_EFFICIENCY_PIN_BUDGET_PCT", 50),
        max_agreed_items=_int_env("AGENT_LAB_EFFICIENCY_MAX_AGREED", 6),
        max_open_items=_int_env("AGENT_LAB_EFFICIENCY_MAX_OPEN", 6),
        max_reply_chars_hint=_int_env("AGENT_LAB_EFFICIENCY_REPLY_HINT", 800),
        max_consensus_rounds=_int_env("AGENT_LAB_EFFICIENCY_CONSENSUS_ROUNDS", 8),
        max_consensus_calls=_int_env("AGENT_LAB_EFFICIENCY_CONSENSUS_CALLS", 20),
    )


def efficiency_mode_default() -> bool:
    return _bool_env("AGENT_LAB_EFFICIENCY", False)


def trim_level(
    *,
    budget_pct: float,
    turns_omitted: int,
    chars_omitted: int,
    limits: AgentContextLimits | None = None,
) -> str:
    lim = limits or agent_context_limits()
    if budget_pct >= lim.critical_budget_pct or chars_omitted > 10:
        return "critical"
    if budget_pct >= lim.warn_budget_pct or turns_omitted > 0 or chars_omitted > 0:
        return "warn"
    return "ok"
