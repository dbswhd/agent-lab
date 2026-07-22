from __future__ import annotations

import pytest

from agent_lab.turn_modes import (
    ModeContractError,
    approval_starts_execute_loop,
    normalize_runtime_turn_profile,
    resolve_mode_contract,
)


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


def test_loop_discuss_is_light_no_consensus(monkeypatch: pytest.MonkeyPatch) -> None:
    """§3.2.1: supervisor discuss must not force consensus multi-round."""
    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "1")
    contract = resolve_mode_contract(
        mode="discuss",
        synthesize=False,
        turn_profile="loop",
        agents=["cursor", "codex"],
        agent_rounds=3,
        review_mode=True,
        consensus_mode=True,
    )
    assert contract.consensus_mode is False
    assert contract.agent_rounds == 1
    assert contract.runtime_turn_profile == "analyze"


def test_loop_discuss_execute_intent_keeps_loop_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Execute-lane dogfood topics must not downgrade to analyze (topic-only composer)."""
    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "1")
    topic = (
        "Makefile x2-lift-dogfood-env echo 갱신 plan action 2개\n"
        "검증: pytest tests/test_ui_handoff_scenarios.py -q\n"
        "dry-run 승인 후 merge, Oracle PASS까지."
    )
    contract = resolve_mode_contract(
        mode="discuss",
        synthesize=False,
        turn_profile="loop",
        agents=["cursor", "codex", "claude"],
        agent_rounds=3,
        review_mode=True,
        consensus_mode=True,
        topic=topic,
    )
    assert contract.runtime_turn_profile == "free"
    assert contract.runtime_turn_profile != "analyze"
    assert contract.plan_intent == "loop"


def test_loop_discuss_build_confirmation_keeps_loop_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """A plain 'implement/build this now' confirmation (no execute-lane vocabulary
    like dry-run/merge/worktree) must still escalate out of light discuss —
    dogfood gap: real file writes shouldn't happen without the consensus gate."""
    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "1")
    topic = (
        "제안한 기본값 그대로 진행해줘 — 거래일 기준 N일, 매월 마지막 거래일 리밸런싱. "
        "바로 구현 + pytest까지 진행해줘."
    )
    contract = resolve_mode_contract(
        mode="discuss",
        synthesize=False,
        turn_profile="loop",
        agents=["cursor", "codex", "claude"],
        agent_rounds=3,
        review_mode=True,
        consensus_mode=True,
        topic=topic,
    )
    assert contract.consensus_mode is True
    assert contract.runtime_turn_profile == "free"
    assert contract.runtime_turn_profile != "analyze"


def test_loop_discuss_pure_question_stays_light(monkeypatch: pytest.MonkeyPatch) -> None:
    """A purely explanatory question about implementation must not escalate —
    only an explicit go-ahead confirmation should."""
    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "1")
    topic = "이 함수를 어떻게 구현하면 좋을지 설명해줘. 아직 코드는 건드리지 마."
    contract = resolve_mode_contract(
        mode="discuss",
        synthesize=False,
        turn_profile="loop",
        agents=["cursor", "codex"],
        agent_rounds=3,
        review_mode=True,
        consensus_mode=True,
        topic=topic,
    )
    assert contract.consensus_mode is False
    assert contract.runtime_turn_profile == "analyze"


def test_loop_plan_keeps_consensus(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = resolve_mode_contract(
        mode="plan",
        synthesize=True,
        turn_profile="loop",
        agents=["cursor", "codex"],
        agent_rounds=1,
        review_mode=False,
        consensus_mode=False,
    )
    assert contract.consensus_mode is True
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


def test_normalize_runtime_turn_profile_ssot() -> None:
    assert normalize_runtime_turn_profile("discuss") == "analyze"
    assert normalize_runtime_turn_profile("loop") == "free"
    assert normalize_runtime_turn_profile("team") == "analyze"
    assert normalize_runtime_turn_profile("quick") == "quick"
    assert normalize_runtime_turn_profile("specialist") == "specialist"
    assert normalize_runtime_turn_profile(None, fallback="free") == "free"
    assert normalize_runtime_turn_profile("unknown", fallback="analyze") == "analyze"
