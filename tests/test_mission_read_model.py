from __future__ import annotations

from dataclasses import replace

from agent_lab.mission.kernel import MissionState, new_mission
from agent_lab.mission.read_model import build_read_model


def test_read_model_exposes_user_action_without_leaking_fsm() -> None:
    mission = new_mission("m-1", "ship it")

    model = build_read_model(mission, legacy_phase="DISCUSS")

    assert model.mission_id == "m-1"
    assert model.state is MissionState.DRAFTING
    assert model.next_action == "draft_plan"
    assert model.event_cursor == 0
    assert model.legacy_phase == "DISCUSS"


def test_read_model_maps_terminal_and_waiting_states() -> None:
    mission = new_mission("m-2", "ship it")

    waiting = build_read_model(replace(mission, state=MissionState.AWAITING_HUMAN))
    done = build_read_model(replace(mission, state=MissionState.SUCCEEDED))

    assert waiting.next_action == "answer_human"
    assert done.next_action == "view_result"
