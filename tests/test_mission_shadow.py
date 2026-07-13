from __future__ import annotations

import json
from pathlib import Path

from agent_lab.mission.shadow import (
    ShadowEventKind,
    ShadowObservation,
    build_ordered_parity_report,
    ordered_parity_report,
    shadow_diff,
)
from agent_lab.run.state import RunState

ROOT = Path(__file__).resolve().parents[1]


def _fixture(name: str) -> RunState:
    raw = json.loads((ROOT / "sessions" / "_regression" / name / "run.json").read_text(encoding="utf-8"))
    return RunState.from_raw(raw)


def test_shadow_diff_maps_plan_rejection() -> None:
    before = RunState.from_raw({"mission_loop": {"phase": "PLAN_GATE"}})
    after = _fixture("mission_loop_plan_reject")
    observations = shadow_diff(before, after)
    assert [item.kind for item in observations] == [ShadowEventKind.PLAN_REJECTED]
    assert observations[0].identity == "plan-revision-1"


def test_shadow_diff_maps_merge_and_oracle_pass() -> None:
    observations = shadow_diff(RunState.empty(), _fixture("worktree_merge_ok"))
    kinds = [item.kind for item in observations]
    assert ShadowEventKind.PLAN_APPROVED in kinds
    assert ShadowEventKind.EXECUTION_MERGED in kinds
    assert ShadowEventKind.ORACLE_PASSED in kinds


def test_shadow_diff_maps_repair_failure_and_pass() -> None:
    observations = shadow_diff(RunState.empty(), _fixture("mission_loop_verify_repair"))
    kinds = [item.kind for item in observations]
    assert ShadowEventKind.ORACLE_FAILED in kinds
    assert ShadowEventKind.ORACLE_PASSED in kinds


def test_shadow_diff_maps_pause_and_completed_steps() -> None:
    observations = shadow_diff(RunState.empty(), _fixture("mission_loop_paused"))
    assert ShadowEventKind.MISSION_PAUSED in [item.kind for item in observations]
    partial = shadow_diff(RunState.empty(), _fixture("durable_completed_steps"))
    assert ShadowEventKind.STEP_COMPLETED in [item.kind for item in partial]


def test_shadow_diff_ignores_identical_snapshots() -> None:
    snapshot = _fixture("mission_loop_plan_reject")
    assert shadow_diff(snapshot, snapshot) == ()


def test_ordered_parity_normalizes_repair_event_alias() -> None:
    observations = (
        ShadowObservation(ShadowEventKind.PLAN_APPROVED, "plan-a", "test", "approved"),
        ShadowObservation(ShadowEventKind.ORACLE_FAILED, "execution-a", "test", "failed"),
        ShadowObservation(ShadowEventKind.ORACLE_PASSED, "execution-a", "test", "passed"),
    )

    report = ordered_parity_report(
        observations,
        ("PlanOpened", "PlanApproved", "RepairScheduled", "MergeCommitted", "OraclePassed"),
    )

    assert report.parity is True
    assert report.expected_types == ("PlanApproved", "OracleFailed", "OraclePassed")
    assert report.observed_types == report.expected_types


def test_ordered_parity_reports_order_drift_and_unsupported_observation() -> None:
    observations = (
        ShadowObservation(ShadowEventKind.ORACLE_FAILED, "execution-a", "test", "failed"),
        ShadowObservation(ShadowEventKind.ORACLE_PASSED, "execution-a", "test", "passed"),
        ShadowObservation(ShadowEventKind.STEP_COMPLETED, "step-1", "test", "completed"),
    )

    report = ordered_parity_report(observations, ("OraclePassed", "RepairScheduled"))

    assert report.parity is False
    assert report.ordered_match is False
    assert report.missing_types == ()
    assert report.unsupported_kinds == (ShadowEventKind.STEP_COMPLETED,)


def test_build_ordered_parity_report_uses_legacy_snapshot_diff() -> None:
    before = RunState.from_raw({"mission_loop": {"phase": "PLAN_GATE"}})
    after = _fixture("mission_loop_plan_reject")

    report = build_ordered_parity_report(before, after, ("PlanOpened", "PlanRejected"))

    assert report.parity is True
