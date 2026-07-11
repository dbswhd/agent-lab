from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.human_inbox import inbox_items
from agent_lab.run.meta import read_run_meta
from agent_lab.runtime.orchestration import derive_orchestration_state, stamp_orchestration_on_folder
from agent_lab.runtime.orchestration_reconcile import (
    apply_reconcile_hint,
    maybe_reconcile_orchestration_drift,
    orchestration_drift_reconcile_enabled,
)
from agent_lab.runtime.policy import PolicyEngine


def test_apply_reconcile_mission_advance_when_plan_approved(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "plan.md").write_text(
        "## Goal\n\n1. **검증:** `pytest -q`\n",
        encoding="utf-8",
    )
    run = {
        "plan_workflow": {"enabled": True, "phase": "APPROVED"},
        "mission_loop": {"enabled": True, "phase": "DISCUSS"},
    }
    updated, action = apply_reconcile_hint(
        run,
        folder=folder,
        hint="advance_mission_past_plan_gate",
        plan_substate="APPROVED",
        mission_phase="DISCUSS",
    )
    assert action == "mission_advance_execute_queue"
    assert updated["mission_loop"]["phase"] == "EXECUTE_QUEUE"


def test_apply_reconcile_rewind_mission_to_clarify() -> None:
    run = {
        "plan_workflow": {"enabled": True, "phase": "CLARIFY"},
        "mission_loop": {"enabled": True, "phase": "DISCUSS"},
    }
    updated, action = apply_reconcile_hint(
        run,
        folder=Path("/tmp/unused"),
        hint="advance_plan_substate_or_rewind_mission_to_clarify",
        plan_substate="CLARIFY",
        mission_phase="DISCUSS",
    )
    assert action == "mission_rewind_clarify"
    assert updated["mission_loop"]["phase"] == "CLARIFY"


def test_apply_reconcile_align_plan_to_mission_discuss() -> None:
    run = {
        "plan_workflow": {"enabled": True, "phase": "CLARIFY"},
        "mission_loop": {"enabled": True, "phase": "DISCUSS"},
    }
    updated, action = apply_reconcile_hint(
        run,
        folder=Path("/tmp/unused"),
        hint="align_plan_substate_with_mission_phase",
        plan_substate="CLARIFY",
        mission_phase="DISCUSS",
    )
    assert action == "plan_align_to_mission"
    assert updated["plan_workflow"]["phase"] == "DRAFT"


def test_stamp_orchestration_auto_reconciles_approved_plan_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_ORCHESTRATION_DRIFT_RECONCILE", "1")
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text(
        json.dumps(
            {
                "plan_workflow": {"enabled": True, "phase": "APPROVED"},
                "mission_loop": {"enabled": True, "phase": "DISCUSS"},
            }
        ),
        encoding="utf-8",
    )
    (folder / "plan.md").write_text("## Goal\n\n1. **검증:** `true`\n", encoding="utf-8")

    orch = stamp_orchestration_on_folder(folder)
    run = read_run_meta(folder)

    assert orch["phase_drift"] is False
    assert run["mission_loop"]["phase"] == "EXECUTE_QUEUE"
    assert run.get("orchestration_reconcile") is None


def test_maybe_reconcile_escalates_after_streak(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ORCHESTRATION_DRIFT_RECONCILE", "1")
    monkeypatch.setenv("AGENT_LAB_ORCHESTRATION_DRIFT_ESCALATE_AFTER", "2")
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text(
        json.dumps(
            {
                "plan_workflow": {"enabled": True, "phase": "APPROVED"},
                "mission_loop": {"enabled": True, "phase": "DISCUSS"},
                "orchestration_reconcile": {
                    "drift_reason": "plan_approved_vs_mission_discuss",
                    "streak": 1,
                },
            }
        ),
        encoding="utf-8",
    )

    orch = derive_orchestration_state(read_run_meta(folder))
    assert orch["phase_drift"] is True

    monkeypatch.setattr(
        "agent_lab.runtime.orchestration_reconcile.apply_reconcile_hint",
        lambda *a, **k: (a[0], None),
    )
    out = maybe_reconcile_orchestration_drift(folder, orch=orch)
    assert out is not None
    assert out.get("escalated") is True

    run = read_run_meta(folder)
    pending = [i for i in inbox_items(run) if i.get("source") == "orchestration_drift"]
    assert pending
    assert pending[0]["status"] == "pending"


def test_policy_engine_reconcile_delegate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ORCHESTRATION_DRIFT_RECONCILE", "1")
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text(
        json.dumps(
            {
                "plan_workflow": {"enabled": True, "phase": "CLARIFY"},
                "mission_loop": {"enabled": True, "phase": "DISCUSS"},
            }
        ),
        encoding="utf-8",
    )
    out = PolicyEngine.reconcile_orchestration_drift(folder)
    assert out is not None
    assert out.get("applied") is True
    assert read_run_meta(folder)["mission_loop"]["phase"] == "CLARIFY"


def test_reconcile_disabled_by_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ORCHESTRATION_DRIFT_RECONCILE", "0")
    assert orchestration_drift_reconcile_enabled() is False
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text(
        json.dumps(
            {
                "plan_workflow": {"enabled": True, "phase": "APPROVED"},
                "mission_loop": {"enabled": True, "phase": "DISCUSS"},
            }
        ),
        encoding="utf-8",
    )
    assert maybe_reconcile_orchestration_drift(folder) is None
    assert read_run_meta(folder)["mission_loop"]["phase"] == "DISCUSS"
