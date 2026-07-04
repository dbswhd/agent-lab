from __future__ import annotations

import pytest

from agent_lab.room.turn_policy import (
    TurnPolicyEngine,
    TurnSignals,
    turn_policy_enabled,
)


@pytest.mark.parametrize("turn_policy_flag", ["0", "1"])
def test_fast_casual_send_no_scribe_dual_run(
    monkeypatch: pytest.MonkeyPatch,
    turn_policy_flag: str,
) -> None:
    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", turn_policy_flag)
    monkeypatch.setenv("AGENT_LAB_AUTO_PLAN_SCRIBE", "1")
    assert turn_policy_enabled() is (turn_policy_flag == "1")
    effects = TurnPolicyEngine.resolve(
        TurnSignals(room_preset="fast"),
    )
    assert effects.run_scribe is False
    assert effects.scribe_trigger == "none"
    assert effects.init_plan_workflow is False


@pytest.mark.parametrize("turn_policy_flag", ["0", "1"])
def test_supervisor_first_turn_inits_plan_workflow_dual_run(
    monkeypatch: pytest.MonkeyPatch,
    turn_policy_flag: str,
) -> None:
    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", turn_policy_flag)
    effects = TurnPolicyEngine.resolve(
        TurnSignals(
            room_preset="supervisor",
            supervisor_first_turn=True,
            plan_workflow_active=False,
            plan_workflow_phase="INTAKE",
        ),
    )
    assert effects.init_plan_workflow is True
    assert effects.advance_plan_workflow is True
    assert effects.run_scribe is False


@pytest.mark.parametrize("turn_policy_flag", ["0", "1"])
def test_consensus_reached_with_pending_agreements_scribes_dual_run(
    monkeypatch: pytest.MonkeyPatch,
    turn_policy_flag: str,
) -> None:
    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", turn_policy_flag)
    effects = TurnPolicyEngine.resolve(
        TurnSignals(
            room_preset="supervisor",
            consensus_status="reached",
            pending_agreement_count=2,
        ),
    )
    assert effects.run_scribe is True
    assert effects.scribe_trigger == "consensus_reached"
