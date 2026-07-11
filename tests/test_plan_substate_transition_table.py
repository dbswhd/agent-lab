from __future__ import annotations

import importlib

from agent_lab.plan.workflow_state import MCP_ADVANCE_TARGETS, PLAN_FSM_ORDER
from agent_lab.runtime.events import RuntimeEvent
from agent_lab.runtime.import_graph import OrchestrationLane
from agent_lab.runtime.transitions import (
    PLAN_SUBSTATE_TRANSITION_TABLE,
    plan_substate_transition_rows_for,
    transition_entry_reason,
)


def test_plan_substate_table_uses_plan_lane() -> None:
    assert PLAN_SUBSTATE_TRANSITION_TABLE
    assert all(row.lane == OrchestrationLane.PLAN for row in PLAN_SUBSTATE_TRANSITION_TABLE)


def test_plan_substate_phases_are_plan_fsm_order() -> None:
    allowed = set(PLAN_FSM_ORDER)
    for row in PLAN_SUBSTATE_TRANSITION_TABLE:
        for phase in row.from_phases:
            assert phase in allowed, f"invalid from_phase {phase!r}"
        assert row.to_phase in allowed, f"invalid to_phase {row.to_phase!r}"


def test_plan_advance_edges_are_forward_only() -> None:
    order = list(PLAN_FSM_ORDER)
    for row in PLAN_SUBSTATE_TRANSITION_TABLE:
        if row.event != RuntimeEvent.PLAN_WORKFLOW_ADVANCE:
            continue
        for from_phase in row.from_phases:
            assert order.index(row.to_phase) > order.index(from_phase)


def test_plan_substate_handlers_importable() -> None:
    for row in PLAN_SUBSTATE_TRANSITION_TABLE:
        module_path, _, attr = row.handler.partition(":")
        mod = importlib.import_module(module_path)
        assert hasattr(mod, attr), row.handler


def test_plan_tick_allowed_from_clarify() -> None:
    run = {"plan_workflow": {"enabled": True, "phase": "CLARIFY"}}
    allowed, reason, phase, rows = transition_entry_reason(run, RuntimeEvent.PLAN_WORKFLOW_TICK)
    assert allowed is True
    assert reason == "plan_substate_table"
    assert phase == "CLARIFY"
    assert rows


def test_plan_advance_clarify_to_draft_allowed() -> None:
    run = {"plan_workflow": {"enabled": True, "phase": "CLARIFY"}}
    allowed, reason, phase, rows = transition_entry_reason(
        run,
        RuntimeEvent.PLAN_WORKFLOW_ADVANCE,
        {"target_phase": "DRAFT"},
    )
    assert allowed is True
    assert reason == "plan_substate_table"
    assert phase == "CLARIFY"
    assert rows[0].to_phase == "DRAFT"


def test_plan_advance_backward_blocked() -> None:
    run = {"plan_workflow": {"enabled": True, "phase": "DRAFT"}}
    allowed, reason, phase, _rows = transition_entry_reason(
        run,
        RuntimeEvent.PLAN_WORKFLOW_ADVANCE,
        {"target_phase": "CLARIFY"},
    )
    assert allowed is False
    assert reason == "forward advance only"
    assert phase == "DRAFT"


def test_plan_advance_row_lookup_matches_table() -> None:
    rows = plan_substate_transition_rows_for(
        RuntimeEvent.PLAN_WORKFLOW_ADVANCE,
        "CLARIFY",
        to_phase="DRAFT",
    )
    assert len(rows) == 1
    assert rows[0].to_phase == "DRAFT"
    assert rows[0].from_phases == frozenset({"CLARIFY"})


def test_plan_tick_blocked_when_approved() -> None:
    run = {"plan_workflow": {"enabled": True, "phase": "APPROVED"}}
    allowed, reason, phase, rows = transition_entry_reason(run, RuntimeEvent.PLAN_WORKFLOW_TICK)
    assert allowed is False
    assert reason == "plan_workflow_approved"
    assert phase == "APPROVED"
    assert rows == ()


def test_mcp_advance_targets_covered_by_table() -> None:
    advance_targets = {
        row.to_phase for row in PLAN_SUBSTATE_TRANSITION_TABLE if row.event == RuntimeEvent.PLAN_WORKFLOW_ADVANCE
    }
    assert MCP_ADVANCE_TARGETS <= advance_targets
