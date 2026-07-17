from __future__ import annotations

import json
from pathlib import Path
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
from app.server.routers.mission_read_model import _payload


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
    assert [item["id"] for item in model.inbox_items] == ["q1", "b1"]


def test_read_model_paused_uses_canonical_mission_and_circuit_state() -> None:
    awaiting_human = replace(new_mission("m-paused-state", "ship"), state=MissionState.AWAITING_HUMAN)
    circuit_paused = replace(new_mission("m-circuit", "ship"), state=MissionState.EXECUTING)
    terminal = replace(new_mission("m-terminal-circuit", "ship"), state=MissionState.SUCCEEDED)

    assert build_read_model(awaiting_human).mission_overview is not None
    assert build_read_model(awaiting_human).mission_overview.paused is True
    assert (
        build_read_model(
            circuit_paused,
            run={"mission_loop": {"circuit_breaker": True}},
        ).mission_overview.paused
        is True
    )
    assert (
        build_read_model(
            terminal,
            run={"mission_loop": {"circuit_breaker": True, "pause_reason": "late"}},
        ).mission_overview.paused
        is False
    )


def test_read_model_join_includes_unrelated_inbox_rows() -> None:
    mission = replace(
        new_mission("m-extra", "ship"),
        state=MissionState.EXECUTING,
        open_gates=(GateRecord("gate-1", "question", "pick", MissionState.EXECUTING),),
    )

    model = build_read_model(
        mission,
        run={
            "human_inbox": [
                {"id": "gate-1", "kind": "question", "status": "pending", "prompt": "Pick"},
                {"id": "extra", "kind": "question", "status": "pending", "prompt": "Unrelated row"},
            ]
        },
    )

    assert [item["id"] for item in model.inbox_items] == ["gate-1", "extra"]
    assert model.inbox_summary is not None
    assert model.inbox_summary.pending_count == 2
    gate_item = next(item for item in model.inbox_items if item["id"] == "gate-1")
    assert gate_item.get("mission_gate_status") == "open_gate"
    extra_item = next(item for item in model.inbox_items if item["id"] == "extra")
    assert extra_item.get("mission_gate_status") == "unrelated"


def test_read_model_joins_open_gates_to_full_rows_in_gate_order() -> None:
    mission = replace(
        new_mission("m-join", "ship"),
        state=MissionState.EXECUTING,
        open_gates=(
            GateRecord("gate-b", "build", "go", MissionState.EXECUTING),
            GateRecord("gate-a", "question", "pick", MissionState.EXECUTING),
        ),
    )
    run = {
        "human_inbox": [
            {
                "id": "gate-a",
                "kind": "question",
                "status": "pending",
                "prompt": "Pick one",
                "options": [{"id": "one", "label": "One"}],
            },
            {
                "id": "gate-b",
                "kind": "build",
                "status": "pending",
                "prompt": "Build it?",
                "options": [],
            },
        ]
    }

    model = build_read_model(mission, run=run)

    assert [item["id"] for item in model.inbox_items] == ["gate-b", "gate-a"]
    assert model.inbox_items[1]["prompt"] == "Pick one"
    assert model.inbox_items[1]["options"] == [{"id": "one", "label": "One"}]
    assert model.inbox_summary is not None
    assert model.inbox_summary.pending_count == 2


def test_read_model_join_uses_first_duplicate_and_non_actionable_placeholders() -> None:
    mission = replace(
        new_mission("m-edges", "ship"),
        state=MissionState.EXECUTING,
        open_gates=(
            GateRecord("dup", "question", "pick", MissionState.EXECUTING),
            GateRecord("missing", "build", "go", MissionState.EXECUTING),
            GateRecord("stale", "question", "old", MissionState.EXECUTING),
        ),
    )
    run = {
        "human_inbox": [
            {"id": "stale", "kind": "question", "status": "resolved", "prompt": "Old"},
            {"id": "dup", "kind": "question", "status": "pending", "prompt": "First", "options": [{"label": "A"}]},
            {"id": "dup", "kind": "question", "status": "pending", "prompt": "Second", "options": [{"label": "B"}]},
        ]
    }

    model = build_read_model(mission, run=run)

    assert [item["id"] for item in model.inbox_items] == ["dup", "missing", "stale"]
    assert model.inbox_items[0]["prompt"] == "First"
    assert model.inbox_items[1]["actionable"] is False
    assert model.inbox_items[1]["status"] == "pending"
    assert model.inbox_items[2]["actionable"] is False
    assert model.inbox_items[2]["status"] == "resolved"
    assert model.inbox_summary is not None
    assert model.inbox_summary.pending_count == 1
    assert model.inbox_summary.pending_questions == 1


def test_terminal_open_gate_is_visible_but_not_actionable() -> None:
    mission = replace(
        new_mission("m-terminal", "ship"),
        state=MissionState.SUCCEEDED,
        open_gates=(GateRecord("gate-terminal", "question", "late", MissionState.EXECUTING),),
    )
    model = build_read_model(
        mission,
        run={"human_inbox": [{"id": "gate-terminal", "kind": "question", "status": "pending", "prompt": "Late?"}]},
    )

    assert model.inbox_items[0]["prompt"] == "Late?"
    assert model.inbox_items[0]["actionable"] is False
    assert model.inbox_items[0]["mission_gate_status"] == "terminal_orphan"
    assert model.inbox_summary is not None
    assert model.inbox_summary.pending_count == 0


def test_missing_row_placeholder_preserves_gate_reason() -> None:
    mission = replace(
        new_mission("m-missing-reason", "ship"),
        state=MissionState.EXECUTING,
        open_gates=(GateRecord("gate-missing", "question", "Need approval", MissionState.EXECUTING),),
    )

    model = build_read_model(mission, run={"human_inbox": []})

    assert model.inbox_items == (
        {
            "id": "gate-missing",
            "kind": "question",
            "status": "pending",
            "prompt": "Human inbox item unavailable",
            "options": [],
            "reason": "Need approval",
            "actionable": False,
            "mission_gate_status": "missing_row",
        },
    )
    assert model.inbox_summary is not None
    assert model.inbox_summary.pending_count == 0


def test_terminal_precedence_marks_missing_and_matched_gates_review_only() -> None:
    mission = replace(
        new_mission("m-terminal-mixed", "ship"),
        state=MissionState.CANCELLED,
        open_gates=(
            GateRecord("gate-missing", "question", "No row", MissionState.EXECUTING),
            GateRecord("gate-present", "question", "Late row", MissionState.EXECUTING),
        ),
    )

    model = build_read_model(
        mission,
        run={"human_inbox": [{"id": "gate-present", "kind": "question", "status": "pending", "prompt": "Late?"}]},
    )

    assert [item["mission_gate_status"] for item in model.inbox_items] == [
        "terminal_orphan",
        "terminal_orphan",
    ]
    assert all(item["actionable"] is False for item in model.inbox_items)
    assert model.inbox_summary is not None
    assert model.inbox_summary.pending_count == 0


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


def _make_test_folder(tmp_path: Path, journal_lines: int = 0) -> Path:
    """Seed a session folder with a structurally-valid journal of N events.

    Events must decode as real ``StoredEvent`` records (sequence/event_id/
    event_type/payload) — ``_expected_event_cursor`` now parses the journal
    via ``MissionJournal`` instead of counting raw lines.
    """
    folder = tmp_path / "session-1"
    journal_folder = folder / ".agent-lab"
    journal_folder.mkdir(parents=True)
    journal = journal_folder / "mission-events.jsonl"
    records = [
        json.dumps(
            {
                "event_id": f"evt-{i}",
                "sequence": i,
                "event_type": "PlanOpened",
                "payload": {},
                "schema_version": 1,
            }
        )
        for i in range(1, journal_lines + 1)
    ]
    journal.write_text("\n".join(records), encoding="utf-8")
    return folder


def test_payload_integrity_ok_requires_non_negative_event_cursor(tmp_path: Path) -> None:
    mission = new_mission("m-cursor", "ship")
    folder = _make_test_folder(tmp_path)
    # new_mission has version 0 and an empty journal, so event_cursor 0 matches.
    model = build_read_model(mission)
    payload = _payload("session-1", model, legacy_phase=None, folder=folder, run=None)
    assert payload["source"] == "mission_journal"

    # Simulate a negative event_cursor by replacing it in the model.
    bad_model = replace(model, event_cursor=-1)
    bad_payload = _payload("session-1", bad_model, legacy_phase=None, folder=folder, run=None)
    assert bad_payload["source"] == "legacy"


def test_payload_integrity_ok_matches_event_cursor_to_journal_line_count(tmp_path: Path) -> None:
    mission = new_mission("m-cursor", "ship")
    folder = _make_test_folder(tmp_path, journal_lines=2)
    model = build_read_model(mission)
    # Default model event_cursor == mission.version == 0, but journal has 2 lines.
    payload = _payload("session-1", model, legacy_phase=None, folder=folder, run=None)
    assert payload["source"] == "legacy"

    # Bump the model event_cursor to match the journal line count.
    matched_model = replace(model, event_cursor=2, version=2)
    payload = _payload("session-1", matched_model, legacy_phase=None, folder=folder, run=None)
    assert payload["source"] == "mission_journal"
    assert payload["event_cursor"] == 2


def test_payload_integrity_ok_cross_checks_run_event_cursor_when_present(tmp_path: Path) -> None:
    mission = new_mission("m-cursor", "ship")
    folder = _make_test_folder(tmp_path, journal_lines=1)
    model = replace(build_read_model(mission), event_cursor=1, version=1)
    payload = _payload("session-1", model, legacy_phase=None, folder=folder, run=None)
    assert payload["source"] == "mission_journal"

    # A run dict with a different cursor should trigger fail-closed.
    run = {"mission_loop": {"event_cursor": 5}}
    payload = _payload("session-1", model, legacy_phase=None, folder=folder, run=run)
    assert payload["source"] == "legacy"


def test_payload_integrity_ok_allows_missing_run_event_cursor(tmp_path: Path) -> None:
    mission = new_mission("m-cursor", "ship")
    folder = _make_test_folder(tmp_path, journal_lines=0)
    model = build_read_model(mission)
    run = {"mission_loop": {}}
    payload = _payload("session-1", model, legacy_phase=None, folder=folder, run=run)
    assert payload["source"] == "mission_journal"


def test_expected_event_cursor_counts_batch_record_events_not_lines(tmp_path: Path) -> None:
    """Regression: a single ``record_type: batch`` line holds >1 event.

    Counting physical lines undercounts the cursor for any multi-event
    dispatch (e.g. ``MissionRepository.decide_plan``), which used to
    permanently fail the payload closed to legacy even though the journal and
    model agreed on ``event_cursor``.
    """
    from app.server.routers.mission_read_model import _expected_event_cursor

    folder = tmp_path / "session-batch"
    journal_folder = folder / ".agent-lab"
    journal_folder.mkdir(parents=True)
    journal = journal_folder / "mission-events.jsonl"
    batch_record = {
        "record_type": "batch",
        "batch_id": "batch-1",
        "events": [
            {
                "event_id": "evt-1",
                "sequence": 1,
                "event_type": "PlanOpened",
                "payload": {},
                "schema_version": 1,
            },
            {
                "event_id": "evt-2",
                "sequence": 2,
                "event_type": "PlanApproved",
                "payload": {},
                "schema_version": 1,
            },
        ],
    }
    journal.write_text(json.dumps(batch_record), encoding="utf-8")

    assert _expected_event_cursor(folder) == 2

    mission = new_mission("m-cursor", "ship")
    model = replace(build_read_model(mission), event_cursor=2, version=2)
    payload = _payload("session-batch", model, legacy_phase=None, folder=folder, run=None)
    assert payload["source"] == "mission_journal"
    assert payload["event_cursor"] == 2
