from __future__ import annotations

from pathlib import Path

from agent_lab.plan.workflow import init_plan_workflow_on_plan_send
from agent_lab.plan.workflow_state import plan_workflow_public
from agent_lab.run.meta import read_run_meta
from agent_lab.runtime.orchestration import (
    derive_orchestration_state,
    reconcile_hint_for_drift,
)


def test_init_plan_workflow_stamps_orchestration(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)
    run = read_run_meta(folder)
    assert run["plan_workflow"]["phase"] == "CLARIFY"
    assert run["orchestration"]["phase"] == "CLARIFY"
    assert run["orchestration"]["plan_substate"] == "CLARIFY"
    assert run["orchestration"]["phase_drift"] is False


def test_plan_workflow_public_includes_orchestration() -> None:
    run = {
        "plan_workflow": {"enabled": True, "phase": "DRAFT"},
        "mission_loop": {"enabled": False, "phase": "MISSION_DEFINE"},
    }
    public = plan_workflow_public(run)
    assert public["orchestration"]["phase"] == "DISCUSS"
    assert public["plan_workflow"]["phase"] == "DRAFT"


def test_reconcile_hint_for_clarify_vs_discuss_drift() -> None:
    hint = reconcile_hint_for_drift(
        "plan_substate_clarify_vs_mission_discuss",
        plan_substate="CLARIFY",
        mission_phase="DISCUSS",
    )
    assert hint == "advance_plan_substate_or_rewind_mission_to_clarify"


def test_reconcile_hint_on_derived_state() -> None:
    run = {
        "plan_workflow": {"enabled": True, "phase": "APPROVED"},
        "mission_loop": {"enabled": True, "phase": "DISCUSS"},
    }
    orch = derive_orchestration_state(run)
    assert orch["phase_drift"] is True
    assert orch["reconcile_hint"] == "advance_mission_past_plan_gate"


def test_reset_after_approved_plan_uses_substate_ssot(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text(
        '{"plan_workflow":{"enabled":true,"phase":"APPROVED","plan_hash_at_approval":"abc"}}',
        encoding="utf-8",
    )
    init_plan_workflow_on_plan_send(folder)
    run = read_run_meta(folder)
    assert run["plan_workflow"]["phase"] == "CLARIFY"
    assert "plan_hash_at_approval" not in run["plan_workflow"]
    assert run["orchestration"]["plan_substate"] == "CLARIFY"
