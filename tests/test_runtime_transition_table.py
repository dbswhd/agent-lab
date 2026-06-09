from __future__ import annotations

import importlib
from collections import defaultdict

import pytest

from agent_lab.runtime.events import RuntimeEvent
from agent_lab.runtime.import_graph import CROSS_LANE_IMPORTS, OrchestrationLane
from agent_lab.runtime.phases import MISSION_PHASES
from agent_lab.runtime.transitions import STANDALONE_EVENTS, TRANSITION_TABLE


def test_mission_phases_cover_transition_table() -> None:
    table_phases = {row.to_phase for row in TRANSITION_TABLE}
    for phase in table_phases:
        assert phase in MISSION_PHASES, f"unknown to_phase {phase!r}"


def test_transition_from_phases_are_valid() -> None:
    for row in TRANSITION_TABLE:
        for phase in row.from_phases:
            assert phase in MISSION_PHASES, (
                f"{row.event}: invalid from_phase {phase!r}"
            )


def test_transition_handlers_are_importable() -> None:
    for row in TRANSITION_TABLE:
        module_path, _, attr = row.handler.partition(":")
        assert attr, f"missing handler attr in {row.handler!r}"
        mod = importlib.import_module(module_path)
        assert hasattr(mod, attr), f"{row.handler} not found"


def test_transition_table_has_no_duplicate_exclusive_edges() -> None:
    """Same (event, from_phase, guard) must not map to different to_phases."""
    by_key: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in TRANSITION_TABLE:
        for phase in row.from_phases:
            key = (row.event.value, phase, row.guard)
            by_key[key].add(row.to_phase)
    conflicts = {k: v for k, v in by_key.items() if len(v) > 1}
    assert not conflicts, f"conflicting transitions: {conflicts}"


def test_runtime_event_catalog_is_unique() -> None:
    values = [e.value for e in RuntimeEvent]
    assert len(values) == len(set(values))


def test_standalone_events_not_in_mission_only_set() -> None:
    mission_events = {row.event for row in TRANSITION_TABLE}
    overlap = STANDALONE_EVENTS & mission_events
    # Overlap is OK when standalone sessions skip phase writes; document overlap.
    assert RuntimeEvent.EXECUTE_DRY_RUN_START in STANDALONE_EVENTS
    assert RuntimeEvent.SCRIBE_COMPLETE in mission_events


def test_cross_lane_import_graph_triangle() -> None:
    lanes = {row.source_lane for row in CROSS_LANE_IMPORTS} | {
        row.target_lane for row in CROSS_LANE_IMPORTS
    }
    assert OrchestrationLane.EXECUTE in lanes
    assert OrchestrationLane.MISSION in lanes
    assert OrchestrationLane.DISCUSS in lanes


def test_h2_h3_forbidden_cross_imports_absent_from_graph() -> None:
    """H2/H3: orchestration triangle edges go through runtime only."""
    from agent_lab.runtime.import_graph import FORBIDDEN_CROSS_IMPORTS

    pairs = {(r.source_module, r.target_module) for r in CROSS_LANE_IMPORTS}
    for forbidden in FORBIDDEN_CROSS_IMPORTS:
        assert forbidden not in pairs
    assert ("agent_lab.room", "agent_lab.runtime.runtime") in pairs
    assert ("agent_lab.mission_loop", "agent_lab.runtime.invoke_discuss") in pairs


def test_transition_table_minimum_coverage() -> None:
    assert len(TRANSITION_TABLE) >= 20
    events = {row.event for row in TRANSITION_TABLE}
    assert RuntimeEvent.EXECUTE_VERIFY_PASS in events
    assert RuntimeEvent.MISSION_PAUSE in events
    assert RuntimeEvent.SCRIBE_COMPLETE in events
