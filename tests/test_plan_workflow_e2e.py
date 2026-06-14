"""Plan-First Workflow end-to-end paths (mock agents, no live LLM)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.human_inbox import create_inbox_item, resolve_inbox_item
from agent_lab.plan_workflow import (
    PlanWorkflowNotApproved,
    approve_plan,
    ensure_plan_workflow_approved,
    get_plan_workflow,
    init_plan_workflow_on_plan_send,
    set_plan_workflow_phase,
    tick_plan_workflow_after_turn,
)
from agent_lab.run_meta import read_run_meta

SAMPLE_PLAN = """# Demo feature

## 지금 실행

1. Add widget
   - 무엇을: implement widget
   - 어디서: `src/widget.py`
   - 검증: `pytest tests/test_widget.py`
"""


def test_inbox_resolve_advances_clarify_to_draft(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)
    assert get_plan_workflow(read_run_meta(folder))["phase"] == "CLARIFY"

    item = create_inbox_item(
        folder,
        kind="question",
        source="mcp_ask_human",
        prompt="Which scope?",
        options=[{"id": "a", "label": "Minimal"}, {"id": "b", "label": "Full"}],
    )
    assert item["status"] == "pending"

    resolve_inbox_item(folder, item["id"], selected=["a"])
    assert get_plan_workflow(read_run_meta(folder))["phase"] == "DRAFT"


def test_e2e_clarify_draft_approve_execute_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_LOOP", "1")
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)

    tick = tick_plan_workflow_after_turn(
        folder,
        synthesize=True,
        cancelled=False,
        plan_md="",
        plan_before="",
        has_pending_inbox_question=False,
    )
    assert tick.get("advance") == "DRAFT"
    assert get_plan_workflow(read_run_meta(folder))["phase"] == "DRAFT"

    (folder / "plan.md").write_text(SAMPLE_PLAN, encoding="utf-8")
    tick = tick_plan_workflow_after_turn(
        folder,
        synthesize=True,
        cancelled=False,
        plan_md=SAMPLE_PLAN,
        plan_before="",
        has_pending_inbox_question=False,
    )
    assert tick.get("advance") == "PEER_REVIEW"

    set_plan_workflow_phase(folder, "HUMAN_PENDING")
    with pytest.raises(PlanWorkflowNotApproved):
        ensure_plan_workflow_approved(folder)

    result = approve_plan(folder)
    assert result["plan_workflow"]["phase"] == "APPROVED"
    ensure_plan_workflow_approved(folder)


def test_run_room_new_session_bootstraps_plan_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab import session as session_mod

    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)

    from agent_lab import room

    folder, _messages, _plan = room.run_room(
        "Build widget feature",
        synthesize=True,
        sessions_base=tmp_path,
        parallel_rounds=1,
    )
    run = read_run_meta(folder)
    pw = get_plan_workflow(run)
    assert pw["enabled"] is True
    assert pw["phase"] in {
        "CLARIFY",
        "DRAFT",
        "PEER_REVIEW",
        "REFINE",
        "HUMAN_PENDING",
    }
