from __future__ import annotations

import pytest

from agent_lab.turn_modes import ModeContractError, approval_starts_execute_loop, resolve_mode_contract


def test_quick_contract_slices_to_lead_and_r1() -> None:
    contract = resolve_mode_contract(
        mode="discuss",
        synthesize=False,
        turn_profile="quick",
        agents=["cursor", "codex", "claude"],
        agent_rounds=3,
        review_mode=True,
        consensus_mode=True,
    )
    assert contract.user_mode == "quick"
    assert contract.runtime_turn_profile == "quick"
    assert contract.agents == ["cursor"]
    assert contract.agent_rounds == 1
    assert contract.consensus_mode is False


def test_team_contract_preserves_team_and_allows_plan_only() -> None:
    contract = resolve_mode_contract(
        mode="plan",
        synthesize=True,
        turn_profile="team",
        agents=["cursor", "codex", "claude"],
        agent_rounds=3,
        review_mode=True,
        consensus_mode=True,
    )
    assert contract.user_mode == "team"
    assert contract.runtime_turn_profile == "analyze"
    assert contract.agents == ["cursor", "codex", "claude"]
    assert contract.agent_rounds == 1
    assert contract.consensus_mode is False
    assert contract.plan_intent == "plan_only"
    assert approval_starts_execute_loop({"plan_intent": contract.plan_intent}) is False
    assert approval_starts_execute_loop({"plan_intent": "loop"}) is True
    assert approval_starts_execute_loop({}) is True


def test_loop_without_plan_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "0")
    with pytest.raises(ModeContractError, match="loop requires plan"):
        resolve_mode_contract(
            mode="discuss",
            synthesize=False,
            turn_profile="loop",
            agents=["cursor", "codex", "claude"],
            agent_rounds=1,
            review_mode=False,
            consensus_mode=False,
        )


def test_loop_discuss_allowed_when_turn_policy_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "1")
    contract = resolve_mode_contract(
        mode="discuss",
        synthesize=False,
        turn_profile="loop",
        agents=["cursor", "codex", "claude"],
        agent_rounds=1,
        review_mode=False,
        consensus_mode=False,
    )
    assert contract.user_mode == "loop"
    assert contract.plan_intent == "loop"


def test_verified_legacy_maps_to_loop_not_team() -> None:
    contract = resolve_mode_contract(
        mode="plan",
        synthesize=True,
        turn_profile="verified",
        agents=["cursor", "codex", "claude"],
        agent_rounds=1,
        review_mode=False,
        consensus_mode=False,
    )
    assert contract.user_mode == "loop"
    assert contract.topology == "verified"
    assert contract.runtime_turn_profile == "verified"
    assert contract.plan_intent == "loop"


def test_verified_legacy_without_plan_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "0")
    with pytest.raises(ModeContractError, match="loop requires plan"):
        resolve_mode_contract(
            mode="discuss",
            synthesize=False,
            turn_profile="verified",
            agents=["cursor", "codex", "claude"],
            agent_rounds=1,
            review_mode=False,
            consensus_mode=False,
        )


def test_specialist_legacy_maps_to_loop_topology() -> None:
    contract = resolve_mode_contract(
        mode="plan",
        synthesize=True,
        turn_profile="specialist",
        agents=["cursor", "codex", "claude"],
        agent_rounds=1,
        review_mode=False,
        consensus_mode=False,
    )
    assert contract.user_mode == "loop"
    assert contract.topology == "specialist"
    assert contract.runtime_turn_profile == "specialist"
    assert contract.agent_rounds == 2
