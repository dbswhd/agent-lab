"""Sprint B — pending plan snapshots and task harvest caps."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.plan.actions import find_dry_run_action
from agent_lab.plan.pending import (
    PlanSnapshotRequired,
    approve_pending_plan,
    ensure_plan_snapshot_approved,
    max_tasks_per_turn,
    plan_content_hash,
)
from agent_lab.run.meta import read_run_meta
from agent_lab.room.tasks import (
    list_tasks,
    mark_tasks_in_progress_for_execution,
    revert_tasks_for_rejected_execution,
    sync_tasks_from_messages,
)


SAMPLE_PLAN = """## 지금 실행
1.
   - 무엇을: Add feature flag
   - 어디서: src/app.py
   - 검증: pytest
"""


class _Msg:
    def __init__(self, role: str, content: str, **kwargs):
        self.role = role
        self.content = content
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_plan_snapshot_required_before_dry_run(tmp_path: Path, monkeypatch):
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "plan.md").write_text(SAMPLE_PLAN, encoding="utf-8")
    (folder / "run.json").write_text("{}\n", encoding="utf-8")

    action = find_dry_run_action(SAMPLE_PLAN, 1, kind="now")
    assert action is not None
    with pytest.raises(PlanSnapshotRequired) as exc:
        ensure_plan_snapshot_approved(folder, action, SAMPLE_PLAN)
    assert exc.value.pending_plan.get("action_key") == "now:1"


def test_approve_snapshot_then_allows_second_check(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "plan.md").write_text(SAMPLE_PLAN, encoding="utf-8")
    (folder / "run.json").write_text("{}\n", encoding="utf-8")

    action = find_dry_run_action(SAMPLE_PLAN, 1, kind="now")
    assert action is not None
    with pytest.raises(PlanSnapshotRequired) as exc:
        ensure_plan_snapshot_approved(folder, action, SAMPLE_PLAN)
    pid = exc.value.pending_plan["id"]
    approve_pending_plan(folder, pid)
    approved = ensure_plan_snapshot_approved(folder, action, SAMPLE_PLAN)
    assert approved.get("status") == "approved"


def test_whole_plan_approval_auto_approves_matching_action_snapshot(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "plan.md").write_text(SAMPLE_PLAN, encoding="utf-8")
    (folder / "run.json").write_text(
        '{"plan_workflow":{"enabled":true,"phase":"APPROVED",'
        f'"plan_hash_at_approval":"{plan_content_hash(SAMPLE_PLAN)}"}}}}\n',
        encoding="utf-8",
    )

    action = find_dry_run_action(SAMPLE_PLAN, 1, kind="now")
    assert action is not None
    approved = ensure_plan_snapshot_approved(folder, action, SAMPLE_PLAN)

    assert approved["status"] == "approved"
    assert approved["approved_by"] == "whole_plan"
    persisted = read_run_meta(folder)["pending_plans"][-1]
    assert persisted["approved_by"] == "whole_plan"


def test_plan_hash_changes_invalidate_approval(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "plan.md").write_text(SAMPLE_PLAN, encoding="utf-8")
    (folder / "run.json").write_text("{}\n", encoding="utf-8")
    action = find_dry_run_action(SAMPLE_PLAN, 1, kind="now")
    assert action is not None
    with pytest.raises(PlanSnapshotRequired) as exc:
        ensure_plan_snapshot_approved(folder, action, SAMPLE_PLAN)
    approve_pending_plan(folder, exc.value.pending_plan["id"])
    changed = SAMPLE_PLAN + "\n<!-- edit -->\n"
    with pytest.raises(PlanSnapshotRequired):
        ensure_plan_snapshot_approved(folder, action, changed)


def test_max_tasks_per_turn_cap(monkeypatch):
    monkeypatch.setenv("AGENT_LAB_MAX_TASKS_PER_TURN", "2")
    assert max_tasks_per_turn() == 2
    run_meta: dict = {"tasks": []}
    msgs = [
        _Msg("user", "go"),
        _Msg("agent", "[PROPOSED: A] [PROPOSED: B] [PROPOSED: C]", agent="codex"),
    ]
    created = sync_tasks_from_messages(run_meta, msgs, human_turn=1)
    assert len(created) == 2
    assert len(list_tasks(run_meta)) == 2


def test_task_in_progress_and_revert_on_reject():
    run_meta: dict = {"tasks": []}
    from agent_lab.room.tasks import add_task

    add_task(run_meta, "Add feature flag", source="test")
    tasks = list_tasks(run_meta)
    tasks[0]["plan_action_index"] = 1
    tasks[0]["plan_action_id"] = "plan-action-now-1"
    from agent_lab.room.tasks import write_tasks

    write_tasks(run_meta, tasks)
    mark_tasks_in_progress_for_execution(
        run_meta,
        action_index=1,
        action_id="plan-action-now-1",
        execution_id="exec-1",
    )
    assert list_tasks(run_meta)[0]["status"] == "in_progress"
    revert_tasks_for_rejected_execution(
        run_meta,
        action_index=1,
        action_id="plan-action-now-1",
        execution_id="exec-1",
    )
    assert list_tasks(run_meta)[0]["status"] == "pending"


def test_plan_content_hash_stable():
    assert plan_content_hash("a") == plan_content_hash("a")
    assert plan_content_hash("a") != plan_content_hash("b")
