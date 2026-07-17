from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

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


@pytest.fixture(autouse=True)
def _clear_dual_write_process_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep dual-write tests hermetic when the developer shell has cohort soak env."""
    monkeypatch.delenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", raising=False)
    monkeypatch.delenv("AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY", raising=False)
    monkeypatch.delenv("AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY", raising=False)
    monkeypatch.delenv("AGENT_LAB_MISSION_EXECUTION_WRITE_AUTHORITY", raising=False)


def _session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "session-1"
    folder.mkdir()
    (folder / "plan.md").write_text("# Plan\n\n- ship", encoding="utf-8")
    (folder / "run.json").write_text('{"plan_workflow":{"enabled":true,"phase":"HUMAN_PENDING"}}', encoding="utf-8")
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", folder.name)
    return folder


def test_session_helper_restores_cohort_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", raising=False)
    with monkeypatch.context() as scoped:
        folder = _session(tmp_path, scoped)
        assert os.environ["AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS"] == folder.name
    assert "AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS" not in os.environ


def test_plan_bridge_is_opt_in_and_idempotent(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    first = mirror_plan_approval(folder, goal="ship")
    second = mirror_plan_approval(folder, goal="ship")
    assert first["mirrored"] is True
    assert second["mirrored"] is True
    assert MissionApplication(folder, "ship").load().version == 2


def test_plan_bridge_respects_session_cohort_allowlist(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", "other-session, another-session")

    result = mirror_plan_approval(folder, goal="ship")

    assert result["enabled"] is True
    assert result["mirrored"] is False
    assert result["reason"] == "cohort_not_selected"
    assert not (folder / ".agent-lab" / "mission-events.jsonl").exists()


def test_plan_bridge_mirrors_allowlisted_session(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", folder.name)

    result = mirror_plan_approval(folder, goal="ship")

    assert result["mirrored"] is True


def test_inbox_bridge_resolves_awaiting_human(tmp_path: Path, monkeypatch) -> None:
    """The pre-execution BlockExecution/AWAITING_HUMAN mechanism is untouched —
    mirror_inbox_resolution still resolves it when Mission happens to be there."""
    folder = _session(tmp_path, monkeypatch)
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
    docs/redesign-2026-07/evidence/execution-gate-design-draft-2026-07-13.md.
    """
    folder = _session(tmp_path, monkeypatch)
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
    folder = _session(tmp_path, monkeypatch)
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
    folder = _session(tmp_path, monkeypatch)
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
    folder = _session(tmp_path, monkeypatch)
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
    folder = _session(tmp_path, monkeypatch)
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
    folder = _session(tmp_path, monkeypatch)
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
    folder = _session(tmp_path, monkeypatch)
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


def test_merge_conflict_approve_opens_gate_for_pending_inbox(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", folder.name)
    mirror_plan_approval(folder, goal="ship")

    from agent_lab.human_inbox import append_inbox_item, new_inbox_item, pending_inbox_items
    from agent_lab.run.meta import patch_run_meta, read_run_meta

    item = new_inbox_item(
        kind="question",
        source="mission_circuit_break",
        prompt="Structural execution failure: merge conflict: src/app.py",
        summary="mission circuit_breaker: structural_execution_failure",
    )

    def _seed(run: dict[str, Any]) -> dict[str, Any]:
        return append_inbox_item(run, item)

    patch_run_meta(folder, _seed)
    assert pending_inbox_items(read_run_meta(folder))

    result = mirror_execution_transition(
        folder,
        execution={"id": "exec-1", "status": "merge_conflict", "merge": {"status": "conflict"}},
        phase="approve",
    )

    mission = MissionApplication(folder, "ship").load()
    assert result["mirrored"] is True
    assert item["id"] in {g.gate_id for g in mission.open_gates}
    assert result.get("merge_conflict_inbox", {}).get("opened_gate_ids") == [item["id"]]


def test_merge_confirm_resolves_merge_conflict_inbox(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", folder.name)
    application = MissionApplication(folder, "ship")
    application.approve_plan()

    from agent_lab.human_inbox import append_inbox_item, new_inbox_item, pending_inbox_items
    from agent_lab.mission.kernel import ApproveDiff, MarkDiffReady, StartExecution
    from agent_lab.run.meta import patch_run_meta, read_run_meta

    item = new_inbox_item(
        kind="question",
        source="mission_circuit_break",
        prompt="Structural execution failure: merge conflict: src/app.py",
        summary="mission circuit_breaker: structural_execution_failure",
    )

    def _seed(run: dict[str, Any]) -> dict[str, Any]:
        run = append_inbox_item(run, item)
        ml = run.setdefault("mission_loop", {})
        ml["enabled"] = True
        ml["circuit_breaker"] = True
        ml["phase"] = "MISSION_PAUSED"
        run["mission_loop"] = ml
        return run

    patch_run_meta(folder, _seed)
    repo = application.repository
    repo.dispatch(StartExecution(), idempotency_key="exec-1:start")
    repo.dispatch(MarkDiffReady(), idempotency_key="exec-1:diff-ready")
    repo.dispatch(ApproveDiff(), idempotency_key="exec-1:diff-approve")
    mirror_inbox_creation(folder, item_id=item["id"], kind="question", reason="merge conflict")

    result = mirror_execution_transition(
        folder,
        execution={
            "id": "exec-1",
            "status": "merged",
            "merge": {"status": "merged", "commit_sha": "resolved123"},
        },
        phase="merge",
    )

    mission = application.load()
    assert result["mirrored"] is True
    assert not pending_inbox_items(read_run_meta(folder))
    assert item["id"] not in {g.gate_id for g in mission.open_gates}
    assert mission.merged_commit_sha == "resolved123"
    assert result.get("merge_conflict_inbox", {}).get("closed_item_ids") == [item["id"]]


def test_merge_confirm_closes_orphan_gate_without_legacy_inbox(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", folder.name)
    application = MissionApplication(folder, "ship")
    application.approve_plan()
    gate_id = "inbox-orphan-gate"
    mirror_inbox_creation(
        folder, item_id=gate_id, kind="question", reason="mission circuit_breaker: structural_execution_failure"
    )
    assert {g.gate_id for g in application.load().open_gates} == {gate_id}

    result = mirror_execution_transition(
        folder,
        execution={
            "id": "exec-1",
            "status": "merged",
            "merge": {"status": "merged", "commit_sha": "resolved123"},
        },
        phase="merge",
    )

    mission = application.load()
    assert result["mirrored"] is True
    assert mission.open_gates == ()
    assert gate_id in (result.get("merge_conflict_inbox") or {}).get("closed_item_ids", [])


def test_plan_write_authority_requires_dual_write(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY", "1")
    monkeypatch.delenv("AGENT_LAB_MISSION_DUAL_WRITE", raising=False)

    from agent_lab.mission.dual_write import plan_write_authority_enabled

    assert plan_write_authority_enabled(folder) is False


def test_plan_write_authority_off_keeps_legacy_first_mirror(tmp_path: Path, monkeypatch) -> None:
    """Authority OFF: legacy approve writes phase first; mirror still works."""
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.delenv("AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY", raising=False)

    from agent_lab.plan.workflow_approval import approve_plan
    from agent_lab.mission.dual_write import mirror_plan_approval, plan_write_authority_enabled

    assert plan_write_authority_enabled(folder) is False
    result = approve_plan(folder, goal="ship")
    assert result["plan_workflow"]["phase"] == "APPROVED"
    bridge = mirror_plan_approval(folder, goal="ship")
    assert bridge["mirrored"] is True
    assert bridge["operation"] == "plan_approve"


def test_plan_write_authority_on_mission_first_then_side_effects(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY", "1")

    from agent_lab.mission.dual_write import commit_plan_approval, plan_write_authority_enabled

    assert plan_write_authority_enabled(folder) is False
    commit = commit_plan_approval(folder, goal="ship")
    assert commit["mirrored"] is False
    assert commit["reason"] == "plan_write_authority_disabled"


def test_plan_write_authority_commit_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY", "1")

    from agent_lab.mission.dual_write import commit_plan_approval

    first = commit_plan_approval(folder, goal="ship")
    second = commit_plan_approval(folder, goal="ship")
    assert first["mirrored"] is False
    assert second["mirrored"] is False
    assert first["reason"] == "plan_write_authority_disabled"
    assert second["reason"] == "plan_write_authority_disabled"


def test_plan_write_authority_reject_honors_refine(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY", "1")

    from agent_lab.plan.workflow_approval import reject_plan_with_mission_authority

    with pytest.raises(ValueError, match="plan write authority is not enabled"):
        reject_plan_with_mission_authority(folder, note="narrow scope", target_phase="REFINE")


def test_plan_write_authority_off_reject_mirror_still_clarify(tmp_path: Path, monkeypatch) -> None:
    """Dual-write-only rejection continues to project CLARIFY (characterization)."""
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.delenv("AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY", raising=False)

    from agent_lab.plan.workflow_approval import reject_plan

    pw = reject_plan(folder, note="needs scope", target_phase="REFINE")
    assert pw["phase"] == "REFINE"
    result = mirror_plan_rejection(folder, note="needs scope", goal="ship")
    assert result["mirrored"] is True
    # Mirror re-projects to CLARIFY — existing dual-write behavior.
    assert read_run_meta(folder)["plan_workflow"]["phase"] == "CLARIFY"


def test_plan_write_authority_rollback_via_flag_off(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY", "1")

    from agent_lab.mission.dual_write import plan_write_authority_enabled

    assert plan_write_authority_enabled(folder) is False
    monkeypatch.delenv("AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY", raising=False)
    assert plan_write_authority_enabled(folder) is False


def test_inbox_write_authority_requires_dual_write(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY", "1")
    monkeypatch.delenv("AGENT_LAB_MISSION_DUAL_WRITE", raising=False)

    from agent_lab.mission.dual_write import inbox_write_authority_enabled

    assert inbox_write_authority_enabled(folder) is False


def test_inbox_write_authority_off_keeps_legacy_first_mirror(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.delenv("AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY", raising=False)

    MissionApplication(folder, "ship").approve_plan()
    item = create_inbox_item(folder, kind="question", source="test", prompt="legacy first?")
    mission = MissionApplication(folder, "ship").load()
    assert {g.gate_id for g in mission.open_gates} == {item["id"]}

    resolve_inbox_item(folder, item["id"], decision="yes", append_chat=False)
    result = mirror_inbox_resolution(folder, item_id=item["id"], answer="yes")
    assert result["mirrored"] is True
    assert result["operation"] == "inbox_resolve"
    assert MissionApplication(folder, "ship").load().open_gates == ()


def test_inbox_write_authority_on_mission_first(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY", "1")

    from agent_lab.mission.dual_write import commit_inbox_resolution

    MissionApplication(folder, "ship").approve_plan()
    # create_inbox_item commits OpenExecutionGate before run.json append when authority on.
    item = create_inbox_item(folder, kind="question", source="test", prompt="authority first?")
    mission = MissionApplication(folder, "ship").load()
    assert {g.gate_id for g in mission.open_gates} == {item["id"]}
    assert any(i.get("id") == item["id"] for i in read_run_meta(folder).get("human_inbox") or [])

    bridge = commit_inbox_resolution(folder, item_id=item["id"], answer="ship it")
    assert bridge["mirrored"] is False
    assert bridge["reason"] == "inbox_write_authority_disabled"
    resolve_inbox_item(folder, item["id"], decision="ship it", append_chat=False)
    assert mirror_inbox_resolution(folder, item_id=item["id"], answer="ship it")["mirrored"] is True
    assert MissionApplication(folder, "ship").load().open_gates == ()
    pending = [i for i in read_run_meta(folder).get("human_inbox") or [] if i.get("status") == "pending"]
    assert pending == []


def test_inbox_write_authority_commit_open_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY", "1")

    from agent_lab.mission.dual_write import commit_inbox_creation, mirror_inbox_creation

    MissionApplication(folder, "ship").approve_plan()
    item_id = "inbox-authority-idem"
    first = commit_inbox_creation(folder, item_id=item_id, kind="question", reason="once")
    second = commit_inbox_creation(folder, item_id=item_id, kind="question", reason="once")
    assert first["mirrored"] is False
    assert second["mirrored"] is False
    assert first["reason"] == "inbox_write_authority_disabled"
    assert second["reason"] == "inbox_write_authority_disabled"
    assert mirror_inbox_creation(folder, item_id=item_id, kind="question", reason="once")["mirrored"] is True
    mission = MissionApplication(folder, "ship").load()
    assert len(mission.open_gates) == 1
    assert mission.open_gates[0].gate_id == item_id


def test_inbox_write_authority_rollback_via_flag_off(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY", "1")

    from agent_lab.mission.dual_write import inbox_write_authority_enabled

    assert inbox_write_authority_enabled(folder) is False
    monkeypatch.delenv("AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY", raising=False)
    assert inbox_write_authority_enabled(folder) is False


def test_supersede_closes_open_execution_gates(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY", "1")

    from agent_lab.human_inbox import supersede_pending_inbox

    MissionApplication(folder, "ship").approve_plan()
    item = create_inbox_item(folder, kind="question", source="test", prompt="stale?")
    assert {g.gate_id for g in MissionApplication(folder, "ship").load().open_gates} == {item["id"]}
    count = supersede_pending_inbox(folder, human_turn_id=2)
    assert count == 1
    assert MissionApplication(folder, "ship").load().open_gates == ()


def test_sync_open_gates_for_harvested_items(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY", "1")

    from agent_lab.human_inbox import append_inbox_item, new_inbox_item
    from agent_lab.mission.dual_write import sync_open_gates_for_inbox_items
    from agent_lab.run.meta import patch_run_meta

    MissionApplication(folder, "ship").approve_plan()
    item = new_inbox_item(kind="question", source="orchestrator", prompt="harvested?")
    patch_run_meta(folder, lambda run: append_inbox_item(run, item))
    opened = sync_open_gates_for_inbox_items(folder, [item], reason="harvest")
    assert opened == [item["id"]]
    assert {g.gate_id for g in MissionApplication(folder, "ship").load().open_gates} == {item["id"]}


def test_execution_write_authority_commit_approve(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_EXECUTION_WRITE_AUTHORITY", "1")

    from agent_lab.mission.dual_write import (
        commit_execution_transition,
        execution_write_authority_enabled,
        mirror_execution_transition,
    )

    assert execution_write_authority_enabled(folder) is False
    MissionApplication(folder, "ship").approve_plan()
    commit = commit_execution_transition(
        folder,
        execution={"id": "exec-1", "status": "approved"},
        phase="approve",
    )
    assert commit["mirrored"] is False
    result = mirror_execution_transition(
        folder,
        execution={"id": "exec-1", "status": "approved"},
        phase="approve",
    )
    assert result["mirrored"] is True
    assert MissionApplication(folder, "ship").load().state is MissionState.VERIFYING


def test_execution_write_authority_reject_stays_legacy_only(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_EXECUTION_WRITE_AUTHORITY", "1")

    from agent_lab.mission.dual_write import commit_execution_transition

    MissionApplication(folder, "ship").approve_plan()
    result = commit_execution_transition(
        folder,
        execution={"id": "exec-1", "status": "rejected"},
        phase="reject",
    )
    assert result["mirrored"] is False
    assert result["reason"] == "execution_write_authority_disabled"
    assert MissionApplication(folder, "ship").load().state is MissionState.READY_TO_EXECUTE
