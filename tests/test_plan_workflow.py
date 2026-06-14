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
    plan_workflow_should_advance_on_turn,
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


def test_tick_clarify_discuss_send_does_not_advance(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    init_plan_workflow_on_plan_send(folder)
    tick = tick_plan_workflow_after_turn(
        folder,
        synthesize=False,
        cancelled=False,
        plan_md="",
        plan_before="",
        has_pending_inbox_question=False,
    )
    assert tick.get("discuss_only") is True
    assert tick.get("advance") is None
    assert get_plan_workflow(read_run_meta(folder))["phase"] == "CLARIFY"


def test_plan_workflow_should_advance_only_on_plan_send(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    init_plan_workflow_on_plan_send(folder)
    run = read_run_meta(folder)
    assert plan_workflow_should_advance_on_turn(run, synthesize=True) is True
    assert plan_workflow_should_advance_on_turn(run, synthesize=False) is False
    assert plan_workflow_should_advance_on_turn({}, synthesize=True) is False


def test_plan_workflow_scribe_requires_plan_send_when_active() -> None:
    from agent_lab.plan_workflow import plan_workflow_allows_scribe

    draft_run = {"plan_workflow": {"enabled": True, "phase": "DRAFT"}}
    refine_run = {"plan_workflow": {"enabled": True, "phase": "REFINE"}}
    assert plan_workflow_allows_scribe(draft_run, synthesize=True, user_plan_send=True) is True
    assert plan_workflow_allows_scribe(draft_run, synthesize=False, user_plan_send=False) is False
    assert plan_workflow_allows_scribe(refine_run, synthesize=False, user_plan_send=False) is False
    approved = {"plan_workflow": {"enabled": True, "phase": "APPROVED"}}
    assert plan_workflow_allows_scribe(approved, synthesize=True, user_plan_send=True) is True
    assert plan_workflow_allows_scribe(approved, synthesize=False, user_plan_send=False) is False


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


def test_approve_plan_execute_loop_gated_by_plan_intent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_LOOP", "1")
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "plan.md").write_text(SAMPLE_PLAN, encoding="utf-8")

    (folder / "run.json").write_text(
        '{"plan_intent":"loop","user_mode":"loop"}',
        encoding="utf-8",
    )
    set_plan_workflow_phase(folder, "HUMAN_PENDING")
    loop_result = approve_plan(folder)
    loop_run = read_run_meta(folder)
    assert loop_result["execute_loop_started"] is True
    assert loop_run["verified_loop"]["status"] == "running"

    (folder / "run.json").write_text(
        '{"plan_intent":"plan_only","user_mode":"team"}',
        encoding="utf-8",
    )
    set_plan_workflow_phase(folder, "HUMAN_PENDING")
    team_result = approve_plan(folder)
    team_run = read_run_meta(folder)
    assert team_result["execute_loop_started"] is False
    assert team_run.get("session_goal") is None
    assert team_run.get("verified_loop", {}).get("status") != "running"
    ensure_plan_workflow_approved(folder)


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
    import app.server.deps as deps_mod

    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", tmp_path)
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


def test_apply_legacy_verified_keeps_loop_semantics_on_plan_send() -> None:
    run_meta: dict = {"turn_profile": "verified"}
    apply_legacy_verified_turn_profile(None, run_meta, synthesize=True)
    assert run_meta["turn_profile"] == "verified"


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


def test_plan_workflow_send_receipt_mapping() -> None:
    from agent_lab.plan_workflow import plan_workflow_send_receipt

    assert plan_workflow_send_receipt("CLARIFY") == "plan_clarify"
    assert plan_workflow_send_receipt("HUMAN_PENDING") == "plan_pending_approval"
    assert plan_workflow_send_receipt(None) is None


def test_clarify_cap_sets_notice(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)

    def _cap(run: dict) -> dict:
        pw = get_plan_workflow(run)
        pw["max_clarify_rounds"] = 0
        run["plan_workflow"] = pw
        return run

    patch_run_meta(folder, _cap)
    tick_plan_workflow_after_turn(
        folder,
        synthesize=True,
        cancelled=False,
        plan_md="",
        plan_before="",
        has_pending_inbox_question=False,
    )
    pw = get_plan_workflow(read_run_meta(folder))
    assert pw["phase"] == "DRAFT"
    assert pw.get("notice") == "clarify_cap_reached"


def test_plan_workflow_complete_payload_includes_notice(tmp_path: Path) -> None:
    from agent_lab.plan_workflow import plan_workflow_complete_payload

    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)

    def _notice(run: dict) -> dict:
        pw = get_plan_workflow(run)
        pw["notice"] = "peer_review_cap_reached"
        pw["phase"] = "HUMAN_PENDING"
        run["plan_workflow"] = pw
        return run

    patch_run_meta(folder, _notice)
    payload = plan_workflow_complete_payload(folder)
    assert payload["plan_workflow_phase"] == "HUMAN_PENDING"
    assert payload["plan_workflow_notice"] == "peer_review_cap_reached"
    assert payload["plan_workflow_pending_approval"] is True
