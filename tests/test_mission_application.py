from __future__ import annotations

from pathlib import Path

from agent_lab.mission.application import MissionApplication
from agent_lab.mission.kernel import BlockExecution, MissionState
from agent_lab.human_inbox import create_inbox_item
from agent_lab.run.meta import read_run_meta


def _session(tmp_path: Path, plan: str) -> Path:
    folder = tmp_path / "session"
    folder.mkdir()
    (folder / "plan.md").write_text(plan, encoding="utf-8")
    (folder / "run.json").write_text(
        '{"plan_workflow":{"enabled":true,"phase":"HUMAN_PENDING"}}',
        encoding="utf-8",
    )
    return folder


def test_application_approval_projects_mission_to_legacy_read_model(tmp_path: Path) -> None:
    folder = _session(tmp_path, "# Plan\n\n- ship it")
    application = MissionApplication(folder, "ship it")

    approved = application.approve_plan()
    restored = MissionApplication(folder, "ship it").load()
    workflow = read_run_meta(folder)["plan_workflow"]

    assert approved.state is MissionState.READY_TO_EXECUTE
    assert restored == approved
    assert workflow["phase"] == "APPROVED"
    assert workflow["plan_hash_at_approval"] == approved.approved_plan_hash


def test_application_rejection_projects_revisit_without_execute(tmp_path: Path) -> None:
    folder = _session(tmp_path, "# Plan\n\n- revise it")
    application = MissionApplication(folder, "revise it")

    rejected = application.reject_plan("scope is unclear")
    workflow = read_run_meta(folder)["plan_workflow"]

    assert rejected.state is MissionState.DRAFTING
    assert workflow["phase"] == "CLARIFY"
    assert workflow["last_reject_note"] == "scope is unclear"


def test_application_can_reopen_same_plan_hash_after_rejection(tmp_path: Path) -> None:
    folder = _session(tmp_path, "# Plan\n\n- revisit it")
    application = MissionApplication(folder, "revisit")

    application.reject_plan("needs more detail")
    approved = application.approve_plan()

    assert approved.state is MissionState.READY_TO_EXECUTE
    assert approved.plan_revision == 2


def test_application_plan_revision_requires_new_approval_hash(tmp_path: Path) -> None:
    folder = _session(tmp_path, "# Plan\n\n- first")
    application = MissionApplication(folder, "revise")
    first = application.approve_plan()
    (folder / "plan.md").write_text("# Plan\n\n- second", encoding="utf-8")

    second = application.approve_plan()

    assert first.approved_plan_hash != second.approved_plan_hash
    assert second.state is MissionState.READY_TO_EXECUTE


def test_application_duplicate_approval_is_idempotent(tmp_path: Path) -> None:
    folder = _session(tmp_path, "# Plan\n\n- once")
    application = MissionApplication(folder, "once")

    first = application.approve_plan()
    second = application.approve_plan()

    assert second == first
    assert application.load().version == first.version


def test_application_answers_inbox_and_resumes_mission(tmp_path: Path) -> None:
    folder = _session(tmp_path, "# Plan\n\n- wait")
    application = MissionApplication(folder, "wait")
    application.approve_plan()
    application.repository.dispatch(BlockExecution("needs human"))
    item = create_inbox_item(
        folder,
        kind="question",
        source="test",
        prompt="Resume?",
    )

    resumed = application.answer_inbox(item["id"], "yes")
    run = read_run_meta(folder)
    resolved = next(row for row in run["human_inbox"] if row["id"] == item["id"])

    assert resumed.state is MissionState.READY_TO_EXECUTE
    assert resolved["status"] == "resolved"
    assert resolved["resolved_choice"] == "yes"
