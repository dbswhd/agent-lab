from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypedDict


class TurnContractEvidence(TypedDict):
    candidate_contract_id: str
    applied_contract_id: str
    safety_floor_satisfied: bool
    roster: list[str]
    rounds_used: int
    consensus: bool
    latency_ms: int
    cost_usd: float
    route_regret_signals: list[str]
    shadow_applied_parity: bool
    rollout_mode: str


_CONTRACT_RANK = {
    "quick_read": 0,
    "standard_collab": 1,
    "guarded_plan": 2,
    "critical_review": 3,
}


def _observed_contract(
    contract: Mapping[str, Any],
    *,
    roster_count: int,
    rounds_used: int,
    consensus: bool,
) -> str:
    if consensus or rounds_used >= 2:
        return "critical_review" if contract.get("risk") == "high" else "guarded_plan"
    if roster_count <= 1:
        return "quick_read"
    return "standard_collab"


def build_turn_contract_evidence(
    contract: Mapping[str, Any],
    *,
    agents: Sequence[str],
    rounds_used: int,
    consensus: bool,
    latency_ms: int,
    cost_usd: float,
    route_regrets: Sequence[str] = (),
) -> TurnContractEvidence:
    """Project the candidate and observed runtime route into one ledger record."""
    roster = [str(agent) for agent in agents]
    candidate = str(contract.get("contract_id") or "")
    applied = _observed_contract(
        contract,
        roster_count=len(roster),
        rounds_used=rounds_used,
        consensus=consensus,
    )
    floor = str(contract.get("safety_floor") or "")
    floor_satisfied = _CONTRACT_RANK.get(applied, -1) >= _CONTRACT_RANK.get(floor, 0)
    return {
        "candidate_contract_id": candidate,
        "applied_contract_id": applied,
        "safety_floor_satisfied": floor_satisfied,
        "roster": roster,
        "rounds_used": max(0, rounds_used),
        "consensus": consensus,
        "latency_ms": max(0, latency_ms),
        "cost_usd": max(0.0, cost_usd),
        "route_regret_signals": [str(signal) for signal in route_regrets],
        "shadow_applied_parity": candidate == applied,
        "rollout_mode": str(contract.get("rollout_mode") or ""),
    }
