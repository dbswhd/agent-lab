"""G004 — role allocation + degradation-aware consensus floor/solo (3/2/1 transitions)."""

from __future__ import annotations


def test_allocate_roles_three_agents() -> None:
    from agent_lab.consensus_gate import allocate_roles

    roles = allocate_roles(["cursor", "codex", "claude"])
    assert roles == {"cursor": "propose", "codex": "endorse", "claude": "synthesize"}


def test_allocate_roles_two_agents() -> None:
    from agent_lab.consensus_gate import allocate_roles

    roles = allocate_roles(["codex", "claude"])
    assert roles == {"codex": "propose", "claude": "endorse"}


def test_allocate_roles_one_agent() -> None:
    from agent_lab.consensus_gate import allocate_roles

    assert allocate_roles(["local"]) == {"local": "propose"}


def test_allocate_roles_live_ids_not_static() -> None:
    from agent_lab.consensus_gate import allocate_roles

    # Substituted roster (kimi in a seat) gets roles by live id, not default names.
    roles = allocate_roles(["codex", "claude", "kimi"])
    assert roles["kimi"] == "synthesize"
    assert "cursor" not in roles


def test_allocate_roles_extra_agents_endorse() -> None:
    from agent_lab.consensus_gate import allocate_roles

    roles = allocate_roles(["a", "b", "c", "d", "e"])
    assert roles["d"] == "scribe"
    assert roles["e"] == "endorse"


def test_effective_consensus_three() -> None:
    from agent_lab.consensus_gate import effective_consensus

    eff = effective_consensus(["cursor", "codex", "claude"])
    assert eff["mode"] == "consensus"
    assert eff["consensus_enabled"] is True
    assert eff["floor"] == 2
    assert eff["required_endorsements"] == 2


def test_effective_consensus_two_floor() -> None:
    from agent_lab.consensus_gate import effective_consensus

    eff = effective_consensus(["codex", "claude"])
    assert eff["mode"] == "consensus"
    # anchor author does not self-endorse → max reachable = n-1 = 1 (matches runtime)
    assert eff["required_endorsements"] == 1


def test_effective_consensus_one_solo() -> None:
    from agent_lab.consensus_gate import effective_consensus

    eff = effective_consensus(["local"])
    assert eff["mode"] == "solo"
    assert eff["consensus_enabled"] is False
    assert eff["required_endorsements"] == 0


def test_effective_consensus_zero_none() -> None:
    from agent_lab.consensus_gate import effective_consensus

    eff = effective_consensus([])
    assert eff["mode"] == "none"
    assert eff["consensus_enabled"] is False
