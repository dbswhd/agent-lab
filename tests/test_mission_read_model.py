from __future__ import annotations

from dataclasses import replace

import pytest

from agent_lab.mission.kernel import GateRecord, MissionState, new_mission
from agent_lab.mission.read_model import MissionOperationalStatus, build_read_model, compute_operational_status


def test_read_model_exposes_user_action_without_leaking_fsm() -> None:
    mission = new_mission("m-1", "ship it")

    model = build_read_model(mission, legacy_phase="DISCUSS")

    assert model.mission_id == "m-1"
    assert model.state is MissionState.DRAFTING
    assert model.next_action == "draft_plan"
    assert model.event_cursor == 0
    assert model.legacy_phase == "DISCUSS"
    assert model.operational_status is MissionOperationalStatus.PLANNING
    assert model.open_execution_gates == ()


def test_read_model_maps_terminal_and_waiting_states() -> None:
    mission = new_mission("m-2", "ship it")

    waiting = build_read_model(replace(mission, state=MissionState.AWAITING_HUMAN))
    done = build_read_model(replace(mission, state=MissionState.SUCCEEDED))

    assert waiting.next_action == "answer_human"
    assert done.next_action == "view_result"


_GATE = GateRecord("gate-1", "question", "why", MissionState.EXECUTING)


@pytest.mark.parametrize(
    ("state", "open_gates", "expected"),
    [
        (MissionState.SUCCEEDED, (), MissionOperationalStatus.COMPLETED),
        (MissionState.FAILED, (), MissionOperationalStatus.FAILED),
        (MissionState.CANCELLED, (), MissionOperationalStatus.CANCELLED),
        (MissionState.SUCCEEDED, (_GATE,), MissionOperationalStatus.COMPLETED),  # terminal wins even w/ orphaned gate
        (MissionState.AWAITING_PLAN_DECISION, (), MissionOperationalStatus.WAITING_FOR_HUMAN),
        (MissionState.AWAITING_DIFF_DECISION, (), MissionOperationalStatus.WAITING_FOR_HUMAN),
        (MissionState.AWAITING_HUMAN, (), MissionOperationalStatus.WAITING_FOR_HUMAN),
        (MissionState.EXECUTING, (_GATE,), MissionOperationalStatus.WAITING_FOR_HUMAN),  # gate-sourced
        (MissionState.VERIFYING, (_GATE,), MissionOperationalStatus.WAITING_FOR_HUMAN),
        (MissionState.REPAIRING, (_GATE,), MissionOperationalStatus.WAITING_FOR_HUMAN),
        (MissionState.EXECUTING, (), MissionOperationalStatus.RUNNING),
        (MissionState.VERIFYING, (), MissionOperationalStatus.RUNNING),
        (MissionState.REPAIRING, (), MissionOperationalStatus.RUNNING),
        (MissionState.READY_TO_EXECUTE, (), MissionOperationalStatus.READY),
        (MissionState.DRAFTING, (), MissionOperationalStatus.PLANNING),
    ],
)
def test_compute_operational_status_priority_table(state, open_gates, expected) -> None:
    mission = replace(new_mission("m-3", "ship it"), state=state, open_gates=open_gates)
    assert compute_operational_status(mission) is expected


def test_operational_status_never_reaches_paused() -> None:
    """PAUSED is reserved for a future signal — nothing currently produces it."""
    for state in MissionState:
        for gates in ((), (_GATE,)):
            mission = replace(new_mission("m-4", "ship it"), state=state, open_gates=gates)
            assert compute_operational_status(mission) is not MissionOperationalStatus.PAUSED


def test_read_model_exposes_open_gate_summaries_without_reason() -> None:
    mission = replace(
        new_mission("m-5", "ship it"),
        state=MissionState.EXECUTING,
        open_gates=(GateRecord("gate-1", "question", "sensitive prompt text", MissionState.EXECUTING),),
    )

    model = build_read_model(mission)

    assert model.operational_status is MissionOperationalStatus.WAITING_FOR_HUMAN
    assert len(model.open_execution_gates) == 1
    assert model.open_execution_gates[0].gate_id == "gate-1"
    assert model.open_execution_gates[0].kind == "question"
    assert not hasattr(model.open_execution_gates[0], "reason")  # deliberately not exposed via the API summary
