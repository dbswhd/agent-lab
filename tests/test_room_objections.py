"""Objection registry and execute gates (Phase E)."""

from __future__ import annotations

import pytest

from agent_lab.agent_envelope import AgentEnvelope
from agent_lab.plan_execute import run_dry_run
from agent_lab.room_objections import (
    ObjectionBlocksExecute,
    append_objection,
    assert_execute_allowed,
    execute_block_reason_for_action,
    harvest_objections_from_turn,
    open_objections,
    resolve_objection,
)
from agent_lab.room_tasks import list_tasks, normalize_task


class _Msg:
    def __init__(self, role, agent=None, content="", envelope=None):
        self.role = role
        self.agent = agent
        self.content = content
        self.envelope = envelope


def test_append_and_execute_block():
    meta: dict = {}
    append_objection(
        meta,
        from_agent="claude",
        act="BLOCK",
        body="ratio unsupported",
        human_turn=2,
        refs=["plan_action:1"],
    )
    assert len(open_objections(meta)) == 1
    reason = execute_block_reason_for_action(meta, 1, "now")
    assert reason is not None
    with pytest.raises(ObjectionBlocksExecute):
        assert_execute_allowed(meta, 1, "now")


def _block_msgs() -> list[_Msg]:
    return [
        _Msg("user", content="go"),
        _Msg(
            "agent",
            agent="claude",
            content="block this",
            envelope=AgentEnvelope(
                act="BLOCK",
                refs=["plan_action:2"],
                message="block this",
            ).to_dict(),
        ),
    ]


def test_harvest_plan_mode_tags_mode():
    meta: dict = {}
    created = harvest_objections_from_turn(meta, _block_msgs(), human_turn=1, mode="plan")
    assert len(created) == 1
    assert created[0]["plan_action_index"] == 2
    assert created[0]["mode"] == "plan"


def test_harvest_discuss_mode_default_on(monkeypatch):
    monkeypatch.delenv("AGENT_LAB_DISCUSS_OBJECTIONS", raising=False)
    meta: dict = {}
    created = harvest_objections_from_turn(meta, _block_msgs(), human_turn=1, mode="discuss")
    assert len(created) == 1
    assert created[0]["mode"] == "discuss"


def test_harvest_discuss_mode_flag_off(monkeypatch):
    monkeypatch.setenv("AGENT_LAB_DISCUSS_OBJECTIONS", "0")
    meta: dict = {}
    assert harvest_objections_from_turn(meta, _block_msgs(), human_turn=1, mode="discuss") == []


def test_resolve_clears_execute_block():
    meta: dict = {}
    row = append_objection(
        meta,
        from_agent="codex",
        act="BLOCK",
        body="wait",
        human_turn=1,
        refs=["1"],
    )
    assert execute_block_reason_for_action(meta, 1, None)
    resolve_objection(meta, row["id"], verdict="wontfix")
    assert execute_block_reason_for_action(meta, 1, None) is None


def test_challenge_blocks_task():
    meta: dict = {"tasks": [normalize_task({"id": "t-abc1234567", "title": "x", "status": "pending"})]}
    append_objection(
        meta,
        from_agent="claude",
        act="CHALLENGE",
        body="recheck",
        human_turn=1,
        refs=["t-abc1234567"],
    )
    from agent_lab.room_objections import apply_challenge_task_blocks

    apply_challenge_task_blocks(meta)
    tasks = list_tasks(meta)
    assert tasks[0]["status"] == "blocked"


def test_dry_run_blocked_by_objection(tmp_path, monkeypatch):
    from agent_lab.plan_actions import find_dry_run_action
    from agent_lab.plan_pending import PlanSnapshotRequired, approve_pending_plan, ensure_plan_snapshot_approved

    folder = tmp_path / "sess"
    folder.mkdir()
    plan_md = "## 지금 실행\n1.\n   - 무엇을: fix\n   - 어디서: `README.md`\n   - 검증: ok\n"
    (folder / "plan.md").write_text(plan_md, encoding="utf-8")
    (folder / "run.json").write_text(
        '{"objections":[{"id":"obj-x","from":"claude","act":"BLOCK",'
        '"body":"no","status":"open","turn":1,"plan_action_index":1,"plan_action_kind":"now"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr("agent_lab.agents.cursor_agent.is_available", lambda: True)
    action = find_dry_run_action(plan_md, 1, kind="now")
    assert action is not None
    try:
        ensure_plan_snapshot_approved(folder, action, plan_md)
    except PlanSnapshotRequired as exc:
        approve_pending_plan(folder, exc.pending_plan["id"])
    with pytest.raises(ObjectionBlocksExecute):
        run_dry_run(folder, action_index=1, action_kind="now")
