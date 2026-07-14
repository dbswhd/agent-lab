from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TopologyKind(StrEnum):
    SINGLE = "single"
    MANAGER_SPECIALISTS = "manager_specialists"
    PEER_QUORUM = "peer_quorum"
    ACTOR_CRITIC = "actor_critic"
    HIERARCHY = "hierarchy"
    BOUNDED_SWARM = "bounded_swarm"


@dataclass(frozen=True, slots=True)
class CoordinationNeed:
    complexity: int
    domain_count: int
    decomposable: bool
    risk: RiskLevel
    evaluation_clear: bool
    time_budget_seconds: int
    cost_budget_usd: float
    available_specialists: int
    manager_bottleneck: bool = False
    exploration: bool = False


@dataclass(frozen=True, slots=True)
class TopologyDecision:
    kind: TopologyKind
    reason: str
    max_agents: int
    fallback: TopologyKind


def choose_topology(need: CoordinationNeed) -> TopologyDecision:
    if (
        need.exploration
        and need.domain_count >= 6
        and need.available_specialists >= 8
        and need.time_budget_seconds >= 300
        and need.cost_budget_usd >= 20
    ):
        return TopologyDecision(
            TopologyKind.BOUNDED_SWARM,
            "large bounded exploration budget",
            1 + need.available_specialists,
            TopologyKind.SINGLE,
        )
    if need.manager_bottleneck and need.complexity >= 7 and need.domain_count >= 4:
        return TopologyDecision(
            TopologyKind.HIERARCHY,
            "measured manager bottleneck",
            1 + need.available_specialists,
            TopologyKind.MANAGER_SPECIALISTS,
        )
    if need.risk is RiskLevel.HIGH and need.available_specialists >= 2:
        return TopologyDecision(
            TopologyKind.PEER_QUORUM,
            "high risk requires independent perspectives",
            min(3, 1 + need.available_specialists),
            TopologyKind.SINGLE,
        )
    if need.decomposable and need.domain_count >= 2 and need.available_specialists >= 2:
        return TopologyDecision(
            TopologyKind.MANAGER_SPECIALISTS,
            "independent domains can be parallelized",
            1 + min(need.available_specialists, need.domain_count),
            TopologyKind.SINGLE,
        )
    if need.evaluation_clear and need.complexity >= 3:
        return TopologyDecision(
            TopologyKind.ACTOR_CRITIC, "evaluation rubric is clearer than generation", 2, TopologyKind.SINGLE
        )
    return TopologyDecision(TopologyKind.SINGLE, "single lead is sufficient", 1, TopologyKind.SINGLE)
