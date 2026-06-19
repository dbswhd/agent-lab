"""Consensus round N-of-M policy and skip/exit rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConsensusPolicy:
    min_endorse_agents: int
    allow_recombination_after_consensus: bool
    max_block_rounds_before_escalate: int

    def should_exit_round(
        self,
        *,
        consensus_status: str | None,
        endorse_count: int,
        active_agents: list[str],
        calls: int,
        max_calls: int,
        rounds: int,
        max_rounds: int,
    ) -> tuple[bool, str | None]:
        if consensus_status == "reached":
            return True, "consensus_reached"
        if endorse_count >= self.min_endorse_agents:
            return True, "endorse_threshold"
        if rounds >= max_rounds:
            return True, "round_cap"
        if calls >= max_calls:
            return True, "call_cap"
        return False, None

    def should_skip_recombination(
        self,
        *,
        consensus_status: str | None,
        substantive_proposers: int,
        rounds: int,
    ) -> tuple[bool, str | None]:
        if not self.allow_recombination_after_consensus and consensus_status == "reached":
            return True, "consensus_already_reached"
        if substantive_proposers < self.min_endorse_agents:
            return True, "insufficient_proposers"
        if rounds >= self.max_block_rounds_before_escalate:
            return True, "max_block_rounds"
        return False, None


def default_consensus_policy() -> ConsensusPolicy:
    return ConsensusPolicy(
        min_endorse_agents=2,
        allow_recombination_after_consensus=False,
        max_block_rounds_before_escalate=4,
    )
