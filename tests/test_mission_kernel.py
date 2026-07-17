from __future__ import annotations

import pytest

from agent_lab.mission.kernel import (
    ApproveDiff,
    ApprovePlan,
    BlockExecution,
    CloseExecutionGate,
    MarkDiffReady,
    Mission,
    MissionEvent,
    MissionState,
    MissionTransitionError,
    OpenExecutionGate,
    OpenPlan,
    OracleVerdict,
    RecordOracle,
    RecordMerge,
    RejectPlan,
    ResolveBlock,
    StartExecution,
    apply_event,
    decide,
    new_mission,
)


def test_plan_rejection_returns_to_drafting() -> None:
    mission = new_mission("m-1", "refactor auth")
    submitted = decide(mission, OpenPlan("hash-1"))
    mission = apply_event(mission, submitted[0])
    rejected = decide(mission, RejectPlan("verify field is vague"))
    mission = apply_event(mission, rejected[0])
    assert mission.state is MissionState.DRAFTING


def test_plan_hash_change_invalidates_previous_approval() -> None:
    mission = new_mission("m-1", "refactor auth")
    for command in (OpenPlan("hash-1"), ApprovePlan("hash-1")):
        mission = apply_event(mission, decide(mission, command)[0])
    mission = apply_event(mission, decide(mission, OpenPlan("hash-2"))[0])
    assert mission.state is MissionState.AWAITING_PLAN_DECISION
    assert mission.approved_plan_hash is None


def test_block_rejects_execution_until_resolved() -> None:
    mission = new_mission("m-1", "refactor auth")
    for command in (OpenPlan("hash-1"), ApprovePlan("hash-1")):
        mission = apply_event(mission, decide(mission, command)[0])
    mission = apply_event(mission, decide(mission, BlockExecution("open objection"))[0])
    with pytest.raises(MissionTransitionError):
        decide(mission, StartExecution())
    mission = apply_event(mission, decide(mission, ResolveBlock())[0])
    assert mission.state is MissionState.READY_TO_EXECUTE


def test_oracle_failure_enters_repair_and_pass_completes() -> None:
    mission = new_mission("m-1", "refactor auth")
    for command in (
        OpenPlan("hash-1"),
        ApprovePlan("hash-1"),
        StartExecution(),
        MarkDiffReady(),
        ApproveDiff(),
        RecordMerge("sha-1"),
    ):
        mission = apply_event(mission, decide(mission, command)[0])
    for event in decide(mission, RecordOracle(OracleVerdict.FAIL, "tests red")):
        mission = apply_event(mission, event)
    assert mission.state is MissionState.REPAIRING
    for command in (MarkDiffReady(), ApproveDiff(), RecordMerge("sha-2")):
        mission = apply_event(mission, decide(mission, command)[0])
    mission = apply_event(mission, decide(mission, RecordOracle(OracleVerdict.PASS, "tests green"))[0])
    assert mission.state is MissionState.SUCCEEDED


def test_apply_preserves_immutable_mission_shape() -> None:
    mission = new_mission("m-1", "refactor auth")
    next_mission = apply_event(mission, decide(mission, OpenPlan("hash-1"))[0])
    assert isinstance(mission, Mission)
    assert mission.state is MissionState.DRAFTING
    assert next_mission.state is MissionState.AWAITING_PLAN_DECISION


def test_stale_expected_version_is_rejected() -> None:
    mission = new_mission("m-1", "refactor auth")
    mission = apply_event(mission, decide(mission, OpenPlan("hash-1"))[0])
    with pytest.raises(MissionTransitionError, match="expected version 0"):
        decide(mission, ApprovePlan("hash-1"), expected_version=0)


def test_repair_cap_emits_terminal_oracle_failure() -> None:
    mission = new_mission("m-1", "refactor auth")
    for command in (
        OpenPlan("hash-1"),
        ApprovePlan("hash-1"),
        StartExecution(),
        MarkDiffReady(),
        ApproveDiff(),
        RecordMerge("sha-1"),
    ):
        mission = apply_event(mission, decide(mission, command)[0])
    for _ in range(3):
        for event in decide(mission, RecordOracle(OracleVerdict.FAIL, "tests red")):
            mission = apply_event(mission, event)
        if mission.state is MissionState.REPAIRING:
            for command in (MarkDiffReady(), ApproveDiff(), RecordMerge(f"sha-{mission.repair_attempt + 1}")):
                mission = apply_event(mission, decide(mission, command)[0])
    assert mission.state is MissionState.FAILED
    assert mission.repair_attempt == mission.max_repair_attempts


def test_event_stream_replay_is_deterministic() -> None:
    initial = new_mission("m-1", "refactor auth")
    commands = (OpenPlan("hash-1"), ApprovePlan("hash-1"))
    source = initial
    events: list[MissionEvent] = []
    for command in commands:
        batch = decide(source, command)
        events.extend(batch)
        for event in batch:
            source = apply_event(source, event)
    first = initial
    second = initial
    for event in events:
        first = apply_event(first, event)
        second = apply_event(second, event)
    assert first == second


def test_oracle_requires_a_recorded_merge() -> None:
    mission = new_mission("m-4", "verify merge")
    for command in (OpenPlan("hash-1"), ApprovePlan("hash-1"), StartExecution(), MarkDiffReady(), ApproveDiff()):
        mission = apply_event(mission, decide(mission, command)[0])
    with pytest.raises(MissionTransitionError, match="merge must be recorded"):
        decide(mission, RecordOracle(OracleVerdict.PASS, "green"))


def test_execution_gate_opens_from_any_state_without_changing_state() -> None:
    mission = new_mission("m-5", "gate anywhere")
    for command in (OpenPlan("hash-1"), ApprovePlan("hash-1"), StartExecution()):
        mission = apply_event(mission, decide(mission, command)[0])
    assert mission.state is MissionState.EXECUTING

    mission = apply_event(mission, decide(mission, OpenExecutionGate("gate-1", "question", "need input"))[0])

    assert mission.state is MissionState.EXECUTING  # unchanged
    assert len(mission.open_gates) == 1
    record = mission.open_gates[0]
    assert record.gate_id == "gate-1"
    assert record.kind == "question"
    assert record.reason == "need input"
    assert record.opened_at_state is MissionState.EXECUTING


def test_execution_gate_open_is_idempotent() -> None:
    mission = new_mission("m-6", "idempotent open")
    events = decide(mission, OpenExecutionGate("gate-1", "question", "first"))
    mission = apply_event(mission, events[0])
    again = decide(mission, OpenExecutionGate("gate-1", "question", "duplicate"))
    assert again == ()  # no-op, no duplicate event
    assert len(mission.open_gates) == 1
    assert mission.open_gates[0].reason == "first"  # original record untouched


def test_execution_gate_close_is_idempotent() -> None:
    mission = new_mission("m-7", "idempotent close")
    mission = apply_event(mission, decide(mission, OpenExecutionGate("gate-1"))[0])
    mission = apply_event(mission, decide(mission, CloseExecutionGate("gate-1"))[0])
    assert mission.open_gates == ()
    again = decide(mission, CloseExecutionGate("gate-1"))
    assert again == ()  # already closed — no-op
    never_opened = decide(mission, CloseExecutionGate("gate-never-opened"))
    assert never_opened == ()


def test_multiple_execution_gates_can_be_open_simultaneously() -> None:
    mission = new_mission("m-8", "multi gate")
    mission = apply_event(mission, decide(mission, OpenExecutionGate("gate-a", "question", "a"))[0])
    mission = apply_event(mission, decide(mission, OpenExecutionGate("gate-b", "build", "b"))[0])
    assert {g.gate_id for g in mission.open_gates} == {"gate-a", "gate-b"}

    mission = apply_event(mission, decide(mission, CloseExecutionGate("gate-a"))[0])
    assert {g.gate_id for g in mission.open_gates} == {"gate-b"}


def test_execution_gate_independent_of_block_execution() -> None:
    """OpenExecutionGate must not interact with the unrelated blocked/AWAITING_HUMAN gate."""
    mission = new_mission("m-9", "independent")
    for command in (OpenPlan("hash-1"), ApprovePlan("hash-1")):
        mission = apply_event(mission, decide(mission, command)[0])
    assert mission.state is MissionState.READY_TO_EXECUTE

    mission = apply_event(mission, decide(mission, OpenExecutionGate("gate-1"))[0])
    assert mission.state is MissionState.READY_TO_EXECUTE
    assert mission.blocked is False
    # StartExecution is still allowed — an open execution gate does not block it.
    mission = apply_event(mission, decide(mission, StartExecution())[0])
    assert mission.state is MissionState.EXECUTING
    assert len(mission.open_gates) == 1  # gate persists independently of state
