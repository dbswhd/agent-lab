from __future__ import annotations

from pathlib import Path
from dataclasses import replace

from agent_lab.mission.application import MissionApplication
from agent_lab.mission.application import project_mission_loop_status
from agent_lab.mission.kernel import MissionState, OpenPlan, new_mission
from agent_lab.mission.plan_bridge import PlanApprovalDecision
from agent_lab.mission.repository import MissionRepository
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.run.state import RunState


def _session(tmp_path: Path) -> Path:
    folder = tmp_path / "session"
    folder.mkdir()
    (folder / "plan.md").write_text("# Plan\n\nship it\n", encoding="utf-8")
    (folder / "run.json").write_text(
        '{"plan_workflow":{"enabled":true,"phase":"HUMAN_PENDING"}}',
        encoding="utf-8",
    )
    return folder


def test_baseline_plan_approval_keeps_journal_and_plan_projection(tmp_path: Path) -> None:
    folder = _session(tmp_path)

    mission = MissionApplication(folder, "ship it").approve_plan()
    run = read_run_meta(folder)

    assert mission.state is MissionState.READY_TO_EXECUTE
    assert mission.version == 2
    assert run["plan_workflow"]["phase"] == "APPROVED"
    assert run["plan_workflow"]["plan_hash_at_approval"] == mission.approved_plan_hash


def test_projection_exposes_only_thin_status_fields() -> None:
    projection = project_mission_loop_status(new_mission("m-1", "ship"), {})

    assert set(projection) == {
        "phase",
        "enabled",
        "autonomous_segment",
        "pause_reason",
        "circuit_breaker",
        "circuit_breaker_reason",
        "work_phase",
        "projection_error_count",
    }
    assert not {"pending_action_indices", "current_action_index", "action_repair_counts"} & set(projection)


def test_projection_covers_mission_transition_states() -> None:
    mission = new_mission("m-2", "ship")
    expected = {
        MissionState.DRAFTING: ("DISCUSS", "plan_draft"),
        MissionState.AWAITING_PLAN_DECISION: ("PLAN_GATE", "plan_draft"),
        MissionState.READY_TO_EXECUTE: ("EXECUTE_QUEUE", "execute_pending"),
        MissionState.EXECUTING: ("DRY_RUN", "execute_pending"),
        MissionState.AWAITING_DIFF_DECISION: ("MERGE_REVIEW", "review_needed"),
        MissionState.VERIFYING: ("VERIFY", "merge_verify"),
        MissionState.REPAIRING: ("REPAIR", "merge_verify"),
        MissionState.AWAITING_HUMAN: ("MISSION_PAUSED", "review_needed"),
        MissionState.SUCCEEDED: ("MISSION_DONE", "done"),
        MissionState.FAILED: ("MISSION_DONE", "done"),
        MissionState.CANCELLED: ("MISSION_DONE", "done"),
    }

    for state, (phase, work_phase) in expected.items():
        run = {"mission_loop": {"phase": "DISCUSS"}} if state is MissionState.DRAFTING else {}
        projection = project_mission_loop_status(replace(mission, state=state), run)
        assert projection["phase"] == phase
        assert projection["work_phase"] == work_phase


def test_projection_preserves_pause_circuit_and_autonomous_shape() -> None:
    mission = replace(new_mission("m-3", "ship"), state=MissionState.READY_TO_EXECUTE)
    run = {
        "mission_loop": {
            "enabled": True,
            "phase": "DISCUSS",
            "autonomous_segment": {"active": True, "started_at": "t0"},
            "pause_reason": "operator_pause",
            "circuit_breaker": True,
            "circuit_breaker_reason": "budget",
        }
    }

    projection = project_mission_loop_status(mission, run)

    assert projection["phase"] == "MISSION_PAUSED"
    assert projection["enabled"] is True
    assert projection["autonomous_segment"] == {"active": True}
    assert projection["pause_reason"] == "operator_pause"
    assert projection["circuit_breaker"] is True
    assert projection["circuit_breaker_reason"] == "budget"


def test_projection_unknown_legacy_phase_is_safe_and_counted() -> None:
    run = {"mission_loop": {"phase": "UNKNOWN_PHASE", "projection_error_count": 2}}

    projection = project_mission_loop_status(new_mission("m-4", "ship"), run)

    assert projection["phase"] == "DISCUSS"
    assert projection["work_phase"] == "plan_draft"
    assert projection["projection_error_count"] == 3


def test_repository_transition_patches_only_compatibility_status(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    (folder / "run.json").write_text(
        '{"plan_workflow":{"enabled":true,"phase":"HUMAN_PENDING"},'
        '"mission_loop":{"enabled":true,"pending_action_indices":[7],'
        '"current_action_index":7,"autonomous_segment":{"active":true,"started_at":"t0"}}}',
        encoding="utf-8",
    )

    mission = MissionApplication(folder, "ship it").approve_plan()
    mission_loop = read_run_meta(folder)["mission_loop"]

    assert mission.state is MissionState.READY_TO_EXECUTE
    assert mission_loop["phase"] == "EXECUTE_QUEUE"
    assert mission_loop["work_phase"] == "execute_pending"
    assert mission_loop["enabled"] is True
    assert mission_loop["autonomous_segment"]["active"] is True
    assert mission_loop["autonomous_segment"]["started_at"] == "t0"
    assert mission_loop["pending_action_indices"] == [7]
    assert mission_loop["current_action_index"] == 7


def test_idempotent_dispatch_reapplies_projection_to_stale_run(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    journal = folder / ".agent-lab" / "mission-events.jsonl"
    repository = MissionRepository(journal, folder.name, "ship it")
    first = repository.dispatch(OpenPlan("plan-hash"), idempotency_key="open-plan")
    assert first.state is MissionState.AWAITING_PLAN_DECISION

    def stale(run: RunState) -> RunState:
        mission_loop = dict(run.get("mission_loop") or {})
        mission_loop["phase"] = "DISCUSS"
        mission_loop["work_phase"] = "plan_draft"
        run["mission_loop"] = mission_loop
        return run

    patch_run_meta(folder, stale)

    restored = repository.dispatch(OpenPlan("plan-hash"), idempotency_key="open-plan")
    projected = read_run_meta(folder)["mission_loop"]

    assert restored == first
    assert projected["phase"] == "PLAN_GATE"
    assert projected["work_phase"] == "plan_draft"


def test_decide_plan_reapplies_projection_before_noop_batch(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path)
    journal = folder / ".agent-lab" / "mission-events.jsonl"
    repository = MissionRepository(journal, folder.name, "ship it")
    monkeypatch.setattr(
        "agent_lab.mission.repository.plan_decision_events",
        lambda *_args: (),
    )

    def stale(run: RunState) -> RunState:
        run["mission_loop"] = {"phase": "DISCUSS", "work_phase": "plan_draft"}
        return run

    patch_run_meta(folder, stale)

    restored = repository.decide_plan("# Plan\n\nship it", PlanApprovalDecision(True))
    projected = read_run_meta(folder)["mission_loop"]

    assert restored.state is MissionState.DRAFTING
    assert projected["phase"] == "DISCUSS"
    assert projected["work_phase"] == "plan_draft"


def test_duplicate_approval_reapplies_projection_to_stale_run(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    application = MissionApplication(folder, "ship it")
    first = application.approve_plan()

    def stale(run: RunState) -> RunState:
        mission_loop = dict(run.get("mission_loop") or {})
        mission_loop["phase"] = "DISCUSS"
        mission_loop["work_phase"] = "plan_draft"
        run["mission_loop"] = mission_loop
        return run

    patch_run_meta(folder, stale)

    duplicate = application.approve_plan()
    projected = read_run_meta(folder)["mission_loop"]

    assert duplicate == first
    assert projected["phase"] == "EXECUTE_QUEUE"
    assert projected["work_phase"] == "execute_pending"
