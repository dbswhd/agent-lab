from __future__ import annotations

from agent_lab.mission.topology import (
    CoordinationNeed,
    RiskLevel,
    TopologyKind,
    choose_topology,
)


def test_simple_low_risk_work_uses_single_lead() -> None:
    decision = choose_topology(CoordinationNeed(1, 1, False, RiskLevel.LOW, True, 30, 1.0, 0))
    assert decision.kind is TopologyKind.SINGLE
    assert decision.max_agents == 1


def test_independent_domains_use_specialists() -> None:
    decision = choose_topology(CoordinationNeed(4, 3, True, RiskLevel.MEDIUM, True, 120, 5.0, 2))
    assert decision.kind is TopologyKind.MANAGER_SPECIALISTS
    assert decision.max_agents == 3


def test_high_risk_design_with_clear_rubric_uses_peer_quorum() -> None:
    decision = choose_topology(CoordinationNeed(4, 2, True, RiskLevel.HIGH, False, 120, 10.0, 2))
    assert decision.kind is TopologyKind.PEER_QUORUM


def test_high_risk_without_independent_seats_falls_back_to_single() -> None:
    decision = choose_topology(CoordinationNeed(4, 2, True, RiskLevel.HIGH, False, 120, 10.0, 0))
    assert decision.kind is TopologyKind.SINGLE
    assert decision.max_agents == 1


def test_clear_evaluation_prefers_actor_critic() -> None:
    decision = choose_topology(CoordinationNeed(3, 1, False, RiskLevel.MEDIUM, True, 120, 4.0, 1))
    assert decision.kind is TopologyKind.ACTOR_CRITIC


def test_hierarchy_requires_measured_manager_bottleneck() -> None:
    decision = choose_topology(CoordinationNeed(8, 5, True, RiskLevel.MEDIUM, False, 300, 20.0, 6, manager_bottleneck=True))
    assert decision.kind is TopologyKind.HIERARCHY


def test_swarm_requires_explicit_large_exploration_budget() -> None:
    decision = choose_topology(CoordinationNeed(10, 8, True, RiskLevel.LOW, False, 600, 30.0, 12, exploration=True))
    assert decision.kind is TopologyKind.BOUNDED_SWARM
