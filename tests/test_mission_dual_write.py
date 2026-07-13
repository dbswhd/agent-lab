from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agent_lab.human_inbox import create_inbox_item, resolve_inbox_item
from agent_lab.mission.dual_write import (
    mirror_inbox_creation,
    mirror_inbox_resolution,
    mirror_execution_transition,
    mirror_plan_approval,
    mirror_plan_rejection,
)
from agent_lab.mission.application import MissionApplication
from agent_lab.mission.kernel import BlockExecution, MissionState
from agent_lab.mission.scheduler_shadow import enqueue_scheduler_shadow_candidates
from agent_lab.mission.activity_queue import ActivityQueue, QueueState, QueuedActivity
from agent_lab.mission.recovery import RecoveryAction, SideEffectState
from agent_lab.run.meta import read_run_meta


def _session(tmp_path: Path) -> Path:
    folder = tmp_path / "session-1"
    folder.mkdir()
    (folder / "plan.md").write_text("# Plan\n\n- ship", encoding="utf-8")
    (folder / "run.json").write_text('{"plan_workflow":{"enabled":true,"phase":"HUMAN_PENDING"}}', encoding="utf-8")
    return folder


def test_plan_bridge_is_opt_in_and_idempotent(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    first = mirror_plan_approval(folder, goal="ship")
    second = mirror_plan_approval(folder, goal="ship")
    assert first["mirrored"] is True
    assert second["mirrored"] is True
    assert MissionApplication(folder, "ship").load().version == 2


def test_plan_bridge_respects_session_cohort_allowlist(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", "other-session, another-session")

    result = mirror_plan_approval(folder, goal="ship")

    assert result["enabled"] is True
    assert result["mirrored"] is False
    assert result["reason"] == "cohort_not_selected"
    assert not (folder / ".agent-lab" / "mission-events.jsonl").exists()


def test_plan_bridge_mirrors_allowlisted_session(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", folder.name)

    result = mirror_plan_approval(folder, goal="ship")

    assert result["mirrored"] is True


def test_inbox_bridge_resolves_awaiting_human(tmp_path: Path, monkeypatch) -> None:
    """The pre-execution BlockExecution/AWAITING_HUMAN mechanism is untouched —
    mirror_inbox_resolution still resolves it when Mission happens to be there."""
    folder = _session(tmp_path)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    MissionApplication(folder, "ship").approve_plan()
    MissionApplication(folder, "ship").repository.dispatch(BlockExecution("hold"))
    item = create_inbox_item(folder, kind="question", source="test", prompt="resume")
    resolve_inbox_item(folder, item["id"], decision="yes", append_chat=False)
    result = mirror_inbox_resolution(folder, item_id=item["id"], answer="yes")
    assert result["mirrored"] is True
    assert MissionApplication(folder, "ship").load().state is MissionState.READY_TO_EXECUTE


def test_inbox_creation_bridge_opens_gate_without_changing_state(tmp_path: Path, monkeypatch) -> None:
    """The actual production path: create_inbox_item alone (no manual kernel dispatch)
    must open an execution gate, regardless of Mission's current state — the original
    gap was that inbox creation had no dual-write hook at all. See
    docs/redesign-2026-07/execution-gate-design-draft-2026-07-13.md.
    """
    folder = _session(tmp_path)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    application = MissionApplication(folder, "ship")
    application.approve_plan()
    assert application.load().state is MissionState.READY_TO_EXECUTE

    item = create_inbox_item(folder, kind="question", source="test", prompt="proceed?")

    mission = application.load()
    assert mission.state is MissionState.READY_TO_EXECUTE  # unchanged — gates are observational
    assert len(mission.open_gates) == 1
    assert mission.open_gates[0].gate_id == item["id"]

    # A stray re-call for the same item is idempotent, not an error.
    result = mirror_inbox_creation(folder, item_id=item["id"], kind="question")
    assert result["mirrored"] is True
    assert result["open_gate_count"] == 1


def test_inbox_creation_bridge_opens_gate_from_drafting_state_too(tmp_path: Path, monkeypatch) -> None:
    """Unlike the old BlockExecution-based bridge, this is not limited to
    READY_TO_EXECUTE — the entire point of the redesign."""
    folder = _session(tmp_path)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    MissionApplication(folder, "ship").reject_plan("needs more scope")  # journal exists, state DRAFTING

    item = create_inbox_item(folder, kind="question", source="test", prompt="proceed?")

    mission = MissionApplication(folder, "ship").load()
    assert mission.state is MissionState.DRAFTING
    assert len(mission.open_gates) == 1
    assert mission.open_gates[0].gate_id == item["id"]
    assert mission.open_gates[0].opened_at_state is MissionState.DRAFTING


def test_inbox_creation_bridge_opens_gate_mid_execution(tmp_path: Path, monkeypatch) -> None:
    """The primary motivating case: most real inbox items (merge_gate.py,
    autonomy_inbox.py, room/retry.py) fire while Mission is EXECUTING, not
    READY_TO_EXECUTE. This used to always no-op; now it mirrors."""
    folder = _session(tmp_path)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    from agent_lab.mission.kernel import StartExecution

    application = MissionApplication(folder, "ship")
    application.approve_plan()
    application.repository.dispatch(StartExecution())
    assert application.load().state is MissionState.EXECUTING

    item = create_inbox_item(folder, kind="question", source="test", prompt="which approach?")

    mission = application.load()
    assert mission.state is MissionState.EXECUTING  # unchanged
    assert {g.gate_id for g in mission.open_gates} == {item["id"]}

    resolve_inbox_item(folder, item["id"], decision="yes", append_chat=False)
    result = mirror_inbox_resolution(folder, item_id=item["id"], answer="yes")
    assert result["mirrored"] is True
    mission = application.load()
    assert mission.state is MissionState.EXECUTING  # still unchanged
    assert mission.open_gates == ()


def test_full_inbox_pause_resume_lifecycle_without_manual_mission_setup(tmp_path: Path, monkeypatch) -> None:
    """End-to-end: plan approve -> a real inbox question fires -> it gets resolved,
    driven entirely through the production functions (mirror_plan_approval,
    create_inbox_item, mirror_inbox_resolution) with no direct kernel dispatch.
    """
    folder = _session(tmp_path)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    mirror_plan_approval(folder, goal="ship")
    item = create_inbox_item(folder, kind="question", source="test", prompt="proceed?")
    assert len(MissionApplication(folder, "ship").load().open_gates) == 1

    resolve_inbox_item(folder, item["id"], decision="yes", append_chat=False)
    result = mirror_inbox_resolution(folder, item_id=item["id"], answer="yes")

    assert result["mirrored"] is True
    mission = MissionApplication(folder, "ship").load()
    assert mission.state is MissionState.READY_TO_EXECUTE
    assert mission.open_gates == ()


def test_rejection_bridge_projects_clarify(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    result = mirror_plan_rejection(folder, note="needs scope", goal="ship")
    assert result["mirrored"] is True
    assert read_run_meta(folder)["plan_workflow"]["phase"] == "CLARIFY"


def test_scheduler_shadow_enqueue_is_idempotent(tmp_path: Path) -> None:
    folder = tmp_path / "session-1"
    folder.mkdir()
    (folder / "run.json").write_text(
        '{"schedules":[{"id":"daily","cron":"* * * * *","pre_approved_at":"2026-07-01T00:00:00Z","enabled":true}]}',
        encoding="utf-8",
    )
    now = datetime(2026, 7, 13, 12, 30, tzinfo=timezone.utc)
    first = enqueue_scheduler_shadow_candidates(tmp_path, now=now)
    second = enqueue_scheduler_shadow_candidates(tmp_path, now=now)
    assert first.queue_parity is True
    assert second.queue_parity is True


def test_committed_side_effect_is_completed_after_restart_recovery(tmp_path: Path) -> None:
    queue = ActivityQueue.for_session(tmp_path)
    queue.enqueue(QueuedActivity("crash-1", "mission-1", "execute", 1, "crash-key"))
    claimed = queue.claim_next("worker-a", now=10.0, ttl_s=5.0)
    assert claimed is not None
    queue.record_side_effect("crash-1", "worker-a", claimed.lease.token, SideEffectState.COMMITTED)
    decisions = ActivityQueue.for_session(tmp_path).recover(now=15.0)
    assert decisions[0].action is RecoveryAction.COMPLETE
    assert ActivityQueue.for_session(tmp_path).snapshot()[0].state is QueueState.COMPLETED


def test_execute_approve_mirrors_merge_commit_without_advancing_oracle(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    application = MissionApplication(folder, "ship")
    application.approve_plan()
    result = mirror_execution_transition(
        folder,
        execution={"id": "exec-1", "status": "merged", "merge": {"commit_sha": "abc123"}},
        phase="approve",
    )
    mission = application.load()
    assert result["mirrored"] is True
    assert mission.state is MissionState.VERIFYING
    assert mission.merged_commit_sha == "abc123"


def test_execute_reverify_mirrors_repair_attempt_before_final_oracle(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    application = MissionApplication(folder, "ship")
    application.approve_plan()
    mirror_execution_transition(
        folder,
        execution={"id": "exec-1", "status": "merged", "merge": {"commit_sha": "base123"}},
        phase="approve",
    )
    result = mirror_execution_transition(
        folder,
        execution={
            "id": "exec-1",
            "status": "merged",
            "merge": {"commit_sha": "repair-merge-123"},
            "oracle": {"verdict": "pass", "detail": "repaired"},
            "repair_history": [
                {
                    "attempt": 1,
                    "exec_commit_sha": "repair-commit-123",
                    "oracle_before": {"verdict": "fail", "detail": "missing marker"},
                }
            ],
        },
        phase="oracle",
    )
    mission = application.load()
    assert result["mirrored"] is True
    assert mission.state is MissionState.SUCCEEDED
    assert mission.repair_attempt == 1
    assert mission.merged_commit_sha == "repair-commit-123"
