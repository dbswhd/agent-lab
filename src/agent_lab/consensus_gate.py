"""Consensus gate for AGENT_LAB_PIPELINE (CONSENSUS mode).

Reuses the existing ConsensusPolicy plus the Room's consensus signal to decide whether the Room
reached consensus before plan.md may be finalized (DISCUSS -> PLAN_GATE). This module is read-only
over the Room's consensus state — the multi-agent debate engine (room_consensus_rounds) is
unchanged; consensus rounds are the source of truth, not a 1:1 agent->role mapping.
"""
from __future__ import annotations

from typing import Any


def _consensus_signal(run: dict[str, Any]) -> dict[str, Any]:
    """Best-effort run-level consensus snapshot: {status|consensus_status, endorse_count}."""
    for key in ("consensus", "consensus_state"):
        candidate = run.get(key)
        if isinstance(candidate, dict):
            return candidate
    ml = run.get("mission_loop")
    if isinstance(ml, dict) and isinstance(ml.get("consensus"), dict):
        return ml["consensus"]
    return {}


def consensus_gate_met(run: dict[str, Any]) -> bool:
    """True when the Room reached consensus (status reached OR endorse >= policy threshold).

    Conservative: absent/ambiguous signal => not met, so plan.md stays gated until the Room's
    consensus rounds record agreement.
    """
    from agent_lab.consensus_policy import default_consensus_policy

    signal = _consensus_signal(run)
    status = signal.get("status") or signal.get("consensus_status")
    if status == "reached":
        return True
    policy = default_consensus_policy()
    try:
        endorse = int(signal.get("endorse_count") or 0)
    except (TypeError, ValueError):
        endorse = 0
    return endorse >= policy.min_endorse_agents
