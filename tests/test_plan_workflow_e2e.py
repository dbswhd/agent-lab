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
    orchestrate_plan_workflow_pipeline,
    set_plan_workflow_phase,
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

REFINED_PLAN = SAMPLE_PLAN + "\n\n<!-- peer refine -->\n"


def _add_open_plan_challenge(folder: Path) -> None:
    def _patch(run: dict) -> dict:
        rows = list(run.get("objections") or [])
        rows.append(
            {
                "id": "obj-peer-challenge",
                "from": "codex",
                "act": "CHALLENGE",
                "body": "narrow verify scope",
                "status": "open",
                "turn": 1,
            }
        )
        run["objections"] = rows
        return run

    patch_run_meta(folder, _patch)


def test_orchestrate_pipeline_peer_refine_human_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Post-scribe pipeline: peer review → refine scribe → second peer → HUMAN_PENDING."""
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("ROOM_SCRIBE_AGENT", "claude")

    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)
    set_plan_workflow_phase(folder, "DRAFT")
    (folder / "plan.md").write_text(SAMPLE_PLAN, encoding="utf-8")

    peer_calls = {"n": 0}

    def _fake_peer_review(folder, *_args, **_kwargs):
        peer_calls["n"] += 1
        if peer_calls["n"] == 1:
            _add_open_plan_challenge(folder)
        else:

            def _clear(run: dict) -> dict:
                for obj in run.get("objections") or []:
                    if obj.get("status") == "open":
                        obj["status"] = "resolved_wontfix"
                return run

            patch_run_meta(folder, _clear)
        return []

    def _fake_synthesize_plan(_topic, _messages, **kwargs):
        return REFINED_PLAN

    monkeypatch.setattr(
        "agent_lab.plan_workflow.run_plan_peer_review_round",
        _fake_peer_review,
    )
    monkeypatch.setattr(
        "agent_lab.room.synthesize_plan",
        _fake_synthesize_plan,
    )

    run_meta = read_run_meta(folder)
    run_meta["_session_folder"] = str(folder)
    plan_md, _replies, tick = orchestrate_plan_workflow_pipeline(
        folder,
        topic="Build widget",
        messages=[],
        plan_md=SAMPLE_PLAN,
        plan_before="",
        synthesize=True,
        cancelled=False,
        agents=["claude", "codex", "cursor"],
        permissions={},
        run_meta=run_meta,
    )

    pw = get_plan_workflow(read_run_meta(folder))
    assert peer_calls["n"] == 2
    assert plan_md.strip() == REFINED_PLAN.strip()
    assert pw["phase"] == "HUMAN_PENDING"
    assert tick.get("pending_approval") is True
    assert (folder / "plan.md").read_text(encoding="utf-8").strip() == REFINED_PLAN.strip()


def test_inbox_resolve_advances_clarify_to_draft(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    # Anchored goal so clarity gate short-circuits; scope question is for another reason.
    (folder / "run.json").write_text(
        '{"verified_loop": {"loop_goal": {"text": "fix src/agent_lab/run_meta.py null check"}}}',
        encoding="utf-8",
    )
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
    # Anchored goal so clarity gate short-circuits via regex (no LLM call, no mock dependency).
    (folder / "run.json").write_text(
        '{"verified_loop": {"loop_goal": {"text": "fix src/agent_lab/run_meta.py null check"}}}',
        encoding="utf-8",
    )
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


def test_run_room_plan_send_reaches_human_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full room plan send (mock) → scribe → peer/refine pipeline → HUMAN_PENDING."""
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_CLARIFIER", "0")
    monkeypatch.setenv("ROOM_SCRIBE_AGENT", "claude")
    from agent_lab import session as session_mod

    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)

    peer_calls = {"n": 0}

    def _fake_peer_review(folder, *_args, **_kwargs):
        peer_calls["n"] += 1
        if peer_calls["n"] == 1:
            _add_open_plan_challenge(folder)
        else:

            def _clear(run: dict) -> dict:
                for obj in run.get("objections") or []:
                    if obj.get("status") == "open":
                        obj["status"] = "resolved_wontfix"
                return run

            patch_run_meta(folder, _clear)
        return []

    def _fake_synthesize_plan(_topic, _messages, **kwargs):
        return SAMPLE_PLAN if peer_calls["n"] == 0 else REFINED_PLAN

    monkeypatch.setattr(
        "agent_lab.plan_workflow.run_plan_peer_review_round",
        _fake_peer_review,
    )
    monkeypatch.setattr("agent_lab.room.synthesize_plan", _fake_synthesize_plan)

    from agent_lab import room

    folder, _messages, plan_md = room.run_room(
        "fix src/agent_lab/room.py plan_workflow peer review",  # anchored → clarity gate passes
        synthesize=True,
        sessions_base=tmp_path,
        parallel_rounds=1,
    )
    pw = get_plan_workflow(read_run_meta(folder))
    assert peer_calls["n"] >= 1
    assert pw["phase"] == "HUMAN_PENDING"
    assert plan_md.strip()
    loop = read_run_meta(folder).get("verified_loop") or {}
    assert loop.get("status") == "pending_approval"
