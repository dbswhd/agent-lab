from __future__ import annotations

from pathlib import Path

from agent_lab.runtime.snapshot import build_runtime_snapshot
from agent_lab.runtime.work_phase import resolve_work_phase


def test_resolve_work_phase_uses_orchestration_when_run_given() -> None:
    run = {
        "plan_workflow": {"enabled": True, "phase": "HUMAN_PENDING"},
        "mission_loop": {"enabled": True, "phase": "DISCUSS"},
    }
    phase = resolve_work_phase(
        mission_enabled=True,
        mission_phase="DISCUSS",
        resume_phase=None,
        plan_workflow_enabled=True,
        plan_workflow_phase="DRAFT",
        has_plan=True,
        has_pending_execution=False,
        has_dry_run_diff=False,
        pending_agreement=False,
        latest_execution=None,
        run=run,
    )
    assert phase == "review_needed"


def test_resolve_work_phase_without_run_uses_standalone() -> None:
    phase = resolve_work_phase(
        mission_enabled=True,
        mission_phase="VERIFY",
        resume_phase=None,
        has_plan=True,
        has_pending_execution=False,
        has_dry_run_diff=False,
        pending_agreement=False,
        latest_execution=None,
        run=None,
    )
    assert phase == "plan_draft"


def test_runtime_snapshot_exposes_orchestration_drift(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text(
        '{"plan_workflow":{"enabled":true,"phase":"CLARIFY"},"mission_loop":{"enabled":true,"phase":"DISCUSS"}}',
        encoding="utf-8",
    )
    snap = build_runtime_snapshot(folder)
    orch = snap["orchestration"]
    assert orch["phase_drift"] is True
    assert orch.get("reconcile_hint")
    assert snap["work_phase"] == "plan_draft"
