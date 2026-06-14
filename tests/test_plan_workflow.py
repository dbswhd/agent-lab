"""Plan-First Workflow (Merge Verified) tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.plan_workflow import (
    PlanWorkflowNotApproved,
    apply_legacy_verified_turn_profile,
    approve_plan,
    derive_loop_goal_from_plan,
    ensure_plan_workflow_approved,
    get_plan_workflow,
    init_plan_workflow_on_plan_send,
    plan_workflow_public,
    reject_plan,
    set_plan_workflow_phase,
    should_enable_plan_workflow,
    tick_plan_workflow_after_turn,
)
from agent_lab.run_meta import patch_run_meta, read_run_meta

SAMPLE_PLAN = """# Demo feature

## 지금 실행

1. Add widget
   - 무엇을: implement widget
   - 어디서: `src/widget.py`
   - 검증: `pytest tests/test_widget.py`
"""


def test_should_enable_plan_workflow_on_plan_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_PLAN_WORKFLOW", raising=False)
    assert should_enable_plan_workflow(synthesize=True) is True
    assert should_enable_plan_workflow(synthesize=False) is False
    monkeypatch.setenv("AGENT_LAB_PLAN_WORKFLOW", "0")
    assert should_enable_plan_workflow(synthesize=True) is False


def test_init_plan_workflow_sets_clarify(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    pw = init_plan_workflow_on_plan_send(folder)
    assert pw["enabled"] is True
    assert pw["phase"] == "CLARIFY"
    run = read_run_meta(folder)
    assert run["verified_loop"]["status"] == "proposing"


def test_tick_clarify_to_draft_when_inbox_clear(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
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


def test_derive_loop_goal_from_plan() -> None:
    derived = derive_loop_goal_from_plan(SAMPLE_PLAN)
    assert derived["goal"] == "Demo feature"
    assert "pytest" in derived["criteria"]


def test_approve_plan_requires_human_pending(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "plan.md").write_text(SAMPLE_PLAN, encoding="utf-8")
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)
    with pytest.raises(ValueError, match="not awaiting"):
        approve_plan(folder)


def test_approve_plan_derives_verified_and_goal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_LOOP", "1")
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "plan.md").write_text(SAMPLE_PLAN, encoding="utf-8")
    (folder / "run.json").write_text("{}", encoding="utf-8")
    set_plan_workflow_phase(folder, "HUMAN_PENDING")

    result = approve_plan(folder)
    run = read_run_meta(folder)
    assert result["plan_workflow"]["phase"] == "APPROVED"
    assert run["session_goal"]["set_by"] == "agents+human"
    assert run["verified_loop"]["status"] == "running"
    assert run["goal_loop"]["enabled"] is True


def test_ensure_plan_workflow_approved_blocks_execute(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)
    with pytest.raises(PlanWorkflowNotApproved):
        ensure_plan_workflow_approved(folder)


def test_reject_plan_returns_to_clarify(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    set_plan_workflow_phase(folder, "HUMAN_PENDING")
    pw = reject_plan(folder, note="revise scope")
    assert pw["phase"] == "CLARIFY"


def test_plan_workflow_public_pending_flag(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    set_plan_workflow_phase(folder, "HUMAN_PENDING")
    pub = plan_workflow_public(read_run_meta(folder))
    assert pub["plan_workflow_pending_approval"] is True


def test_patch_goal_blocked_when_plan_workflow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    import agent_lab.session as session_mod

    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    folder = tmp_path / "pw-sess"
    folder.mkdir()
    (folder / "topic.txt").write_text("topic\n", encoding="utf-8")
    (folder / "run.json").write_text(
        '{"plan_workflow":{"enabled":true,"phase":"CLARIFY"}}',
        encoding="utf-8",
    )
    from fastapi import HTTPException

    from app.server.deps import SessionGoalPatchRequest
    from app.server.routers.sessions import patch_session_goal

    with pytest.raises(HTTPException) as exc:
        patch_session_goal("pw-sess", SessionGoalPatchRequest(text="manual goal"))
    assert exc.value.status_code == 409


def test_apply_legacy_verified_redirects_on_plan_send() -> None:
    run_meta: dict = {"turn_profile": "verified"}
    apply_legacy_verified_turn_profile(None, run_meta, synthesize=True)
    assert run_meta["turn_profile"] == "analyze"


def test_verified_loop_approve_delegates_with_deprecation_header(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import agent_lab.session as session_mod
    from agent_lab.plan_workflow import set_plan_workflow_phase

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_LOOP", "1")
    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    import app.server.deps as deps_mod

    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", tmp_path)
    folder = tmp_path / "pw-api"
    folder.mkdir()
    (folder / "topic.txt").write_text("t\n", encoding="utf-8")
    (folder / "plan.md").write_text(SAMPLE_PLAN, encoding="utf-8")
    (folder / "run.json").write_text("{}", encoding="utf-8")
    set_plan_workflow_phase(folder, "HUMAN_PENDING")

    from app.server.main import app

    client = TestClient(app)
    res = client.post(f"/api/sessions/{folder.name}/verified-loop/approve", json={})
    assert res.status_code == 200
    assert res.headers.get("Deprecation") == "true"
    assert "plan/approve" in (res.headers.get("Link") or "")
    assert res.json()["deprecated"] == "use POST /plan/approve"
