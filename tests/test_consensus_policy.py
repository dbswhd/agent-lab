"""Tests for consensus_policy rules."""

from __future__ import annotations

from agent_lab.consensus_policy import ConsensusPolicy, default_consensus_policy


def test_default_policy_values() -> None:
    policy = default_consensus_policy()
    assert policy.min_endorse_agents == 2
    assert policy.allow_recombination_after_consensus is False
    assert policy.max_block_rounds_before_escalate == 4


def test_should_exit_round_reached() -> None:
    policy = ConsensusPolicy(
        min_endorse_agents=2,
        allow_recombination_after_consensus=False,
        max_block_rounds_before_escalate=2,
    )
    exited, reason = policy.should_exit_round(
        consensus_status="reached",
        endorse_count=0,
        active_agents=["a", "b"],
        calls=10,
        max_calls=20,
        rounds=5,
        max_rounds=10,
    )
    assert exited is True
    assert reason == "consensus_reached"


def test_should_exit_round_endorse_cap() -> None:
    policy = ConsensusPolicy(
        min_endorse_agents=3,
        allow_recombination_after_consensus=False,
        max_block_rounds_before_escalate=1,
    )
    exited, reason = policy.should_exit_round(
        consensus_status=None,
        endorse_count=3,
        active_agents=["a", "b", "c"],
        calls=2,
        max_calls=20,
        rounds=1,
        max_rounds=10,
    )
    assert exited is True
    assert reason == "endorse_threshold"
