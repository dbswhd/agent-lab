from __future__ import annotations

from agent_lab.room.turn_contract import (
    ContractOutcome,
    TurnContractId,
    build_turn_contract,
    contract_runtime_controls,
    derive_route_regrets,
    observe_turn,
    turn_contract_mode,
)


def test_high_risk_semantics_raise_safety_floor_without_exact_keyword() -> None:
    observation = observe_turn(
        "금전 거래 코드에 위험이 없는지 봐줘",
        {"room_preset": "supervisor", "agents": ["cursor", "codex", "claude"]},
    )

    assert observation.risk == "high"
    assert "financial_domain" in observation.evidence

    contract = build_turn_contract(observation)

    assert contract.contract_id is TurnContractId.CRITICAL_REVIEW
    assert contract.safety_floor == "critical_review"


def test_cold_start_defaults_to_standard_for_ambiguous_review() -> None:
    observation = observe_turn(
        "TurnPolicy의 정적성을 검토해봐",
        {"room_preset": "supervisor", "agents": ["cursor", "codex", "claude"]},
    )

    contract = build_turn_contract(observation)

    assert contract.contract_id is TurnContractId.STANDARD_COLLAB
    assert contract.source == "bootstrap"
    assert contract.confidence == "low"


def test_execute_intent_cannot_select_read_only_contract() -> None:
    observation = observe_turn(
        "이 변경을 실제 코드에 반영하고 확인까지 해줘",
        {"room_preset": "supervisor", "agents": ["cursor", "codex"]},
    )

    assert observation.execute_intent is True
    assert build_turn_contract(observation).contract_id is TurnContractId.GUARDED_PLAN


def test_contract_snapshot_is_json_compatible_and_explains_choice() -> None:
    observation = observe_turn(
        "오타 하나만 고쳐줘",
        {"room_preset": "supervisor", "agents": ["cursor", "codex", "claude"]},
    )

    snapshot = build_turn_contract(observation).to_snapshot()

    assert snapshot["contract_id"] == "quick_read"
    assert snapshot["source"] == "bootstrap"
    assert "evidence" in snapshot
    assert "candidates" in snapshot


def test_quick_failure_is_recorded_as_under_routed() -> None:
    assert derive_route_regrets(
        TurnContractId.QUICK_READ.value,
        escalated=True,
        final_verdict="fail",
        repair_attempts=1,
        rounds_used=1,
        execution_present=True,
    ) == ("under_routed",)


def test_guarded_one_round_without_execution_is_only_a_regret_candidate() -> None:
    assert derive_route_regrets(
        TurnContractId.GUARDED_PLAN.value,
        escalated=False,
        final_verdict=None,
        repair_attempts=0,
        rounds_used=1,
        execution_present=False,
    ) == ("over_routed_candidate",)


def test_route_regret_expands_to_clarify_fsm_and_subset_signals() -> None:
    regrets = derive_route_regrets(
        "standard_collab",
        escalated=False,
        final_verdict="pass",
        repair_attempts=0,
        rounds_used=1,
        execution_present=False,
        clarify_no_delta=True,
        fsm_no_action=True,
        subset_escalated=True,
    )
    assert regrets == ("clarify_no_delta", "fsm_no_action", "subset_escalated")


def test_history_is_ignored_until_project_sample_threshold() -> None:
    observation = observe_turn(
        "TurnPolicy의 정적성을 검토해봐",
        {"room_preset": "supervisor", "agents": ["cursor", "codex", "claude"]},
    )
    history: list[ContractOutcome] = [
        {"contract_id": "quick_read", "final_verdict": "pass", "repair_attempts": 0}
        for _ in range(9)
    ]

    contract = build_turn_contract(observation, history=history)

    assert contract.source == "bootstrap"


def test_history_exploitation_adjusts_only_eligible_candidates() -> None:
    observation = observe_turn(
        "TurnPolicy의 정적성을 검토해봐",
        {"room_preset": "supervisor", "agents": ["cursor", "codex", "claude"]},
    )
    history: list[ContractOutcome] = [
        {"contract_id": "standard_collab", "final_verdict": "pass", "repair_attempts": 0}
        for _ in range(10)
    ] + [
        {"contract_id": "quick_read", "final_verdict": "fail", "repair_attempts": 1}
        for _ in range(10)
    ]

    contract = build_turn_contract(observation, history=history)

    assert contract.source == "history"
    assert contract.contract_id is TurnContractId.STANDARD_COLLAB
    assert "history_n=20" in contract.observation.evidence


def test_history_cannot_lower_high_risk_safety_floor() -> None:
    observation = observe_turn(
        "금전 거래 코드에 위험이 없는지 봐줘",
        {"room_preset": "supervisor", "agents": ["cursor", "codex", "claude"]},
    )
    history: list[ContractOutcome] = [
        {"contract_id": "quick_read", "final_verdict": "pass", "repair_attempts": 0}
        for _ in range(20)
    ]

    contract = build_turn_contract(observation, history=history)

    assert contract.contract_id is TurnContractId.CRITICAL_REVIEW
    assert contract.safety_floor is TurnContractId.CRITICAL_REVIEW


def test_deterministic_exploration_uses_unseen_safe_candidate(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_EXPLORE_RATE", "1")
    observation = observe_turn(
        "TurnPolicy의 정적성을 검토해봐",
        {"room_preset": "supervisor", "agents": ["cursor", "codex", "claude"]},
    )
    history: list[ContractOutcome] = [
        {"contract_id": "standard_collab", "final_verdict": "pass", "repair_attempts": 0}
        for _ in range(10)
    ]

    contract = build_turn_contract(observation, history=history)

    assert contract.source == "explore"
    assert contract.contract_id is TurnContractId.CRITICAL_REVIEW


def test_turn_contract_mode_defaults_to_shadow_and_rejects_unknown(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LAB_TURN_CONTRACT_MODE", raising=False)
    assert turn_contract_mode() == "shadow"
    monkeypatch.setenv("AGENT_LAB_TURN_CONTRACT_MODE", "invalid")
    assert turn_contract_mode() == "shadow"


def test_quick_contract_runtime_controls_limit_roster_and_rounds() -> None:
    assert contract_runtime_controls("quick_read") == (1, 1, False)
