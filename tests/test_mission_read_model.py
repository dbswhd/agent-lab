from __future__ import annotations

from dataclasses import replace

import pytest

from agent_lab.mission.kernel import GateRecord, MissionState, new_mission
from agent_lab.mission.read_model import (
    MissionOperationalStatus,
    build_legacy_composites,
    build_read_model,
    compute_operational_status,
    plan_phase_from_mission,
    work_phase_from_mission,
)


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


def test_wave_a_work_phase_and_plan_from_mission() -> None:
    drafting = new_mission("m-wp", "ship")
    awaiting = replace(drafting, state=MissionState.AWAITING_PLAN_DECISION)
    ready = replace(
        drafting,
        state=MissionState.READY_TO_EXECUTE,
        approved_plan_hash="h1",
        current_plan_hash="h1",
    )
    verifying = replace(ready, state=MissionState.VERIFYING)

    assert work_phase_from_mission(drafting) == "plan_draft"
    assert work_phase_from_mission(awaiting) == "plan_draft"
    assert work_phase_from_mission(ready) == "execute_pending"
    assert work_phase_from_mission(verifying) == "merge_verify"
    assert plan_phase_from_mission(awaiting) == "HUMAN_PENDING"
    assert plan_phase_from_mission(ready) == "APPROVED"


def test_wave_a_read_model_composites_join_run() -> None:
    mission = replace(
        new_mission("m-c", "ship"),
        state=MissionState.AWAITING_PLAN_DECISION,
        current_plan_hash="ph",
    )
    run = {
        "plan_workflow": {"phase": "HUMAN_PENDING"},
        "human_inbox": [
            {"id": "q1", "kind": "question", "status": "pending", "prompt": "ok?"},
            {"id": "b1", "kind": "build", "status": "pending", "prompt": "go?"},
        ],
        "mission_loop": {"phase": "DISCUSS", "circuit_breaker": True},
    }

    model = build_read_model(mission, legacy_phase="DISCUSS", run=run)

    assert model.plan is not None
    assert model.plan.phase == "HUMAN_PENDING"
    assert model.plan.pending_approval is True
    assert model.work_phase == "plan_draft"
    assert model.mission_overview is not None
    assert model.mission_overview.circuit_breaker is True
    assert model.mission_overview.pending_inbox_count == 2
    assert model.inbox_summary is not None
    assert model.inbox_summary.pending_count == 2
    assert model.inbox_summary.pending_questions == 1
    assert model.inbox_summary.pending_builds == 1
    assert model.inbox_items == ()


def test_build_legacy_composites_for_unmigrated() -> None:
    out = build_legacy_composites(
        {
            "plan_workflow": {"phase": "APPROVED", "plan_hash_at_approval": "z"},
            "mission_loop": {"phase": "EXECUTE", "pause_reason": "budget"},
            "human_inbox": [],
        }
    )
    assert out["plan"]["phase"] == "APPROVED"
    assert out["plan"]["pending_approval"] is False
    assert out["mission_overview"]["paused"] is True
    assert out["work_phase"] in {"execute_pending", "plan_draft", "merge_verify", "review_needed", "done"}
    assert out["inbox_items"] == []
