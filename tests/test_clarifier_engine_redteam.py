from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent_lab.run.meta import patch_run_meta, read_run_meta


@pytest.fixture(autouse=True)
def _legacy_plan_fsm_skill_first(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.name == "test_ac10b_mcp_first_engine_on_holds_clarify":
        return
    monkeypatch.setenv("AGENT_LAB_PLAN_FSM_SKILL_FIRST", "0")


def _sess(tmp_path: Path) -> Path:
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    return folder


def _seed_goal(folder: Path, text: str) -> None:
    def _patch(run: dict) -> dict:
        loop = run.get("verified_loop")
        loop = loop if isinstance(loop, dict) else {}
        loop["loop_goal"] = {"text": text}
        run["verified_loop"] = loop
        return run

    patch_run_meta(folder, _patch)


def _init_plan_workflow(folder: Path) -> None:
    from agent_lab.plan.workflow import init_plan_workflow_on_plan_send

    init_plan_workflow_on_plan_send(folder)


def _tick(folder: Path) -> dict:
    from agent_lab.plan.workflow import tick_plan_workflow_after_turn

    return tick_plan_workflow_after_turn(
        folder,
        synthesize=True,
        cancelled=False,
        plan_md="",
        plan_before="",
        has_pending_inbox_question=False,
    )


def _panel(source: str, qid: str, prompt: str = "Q?") -> dict:
    return {
        "version": 2,
        "status": "pending",
        "source": source,
        "weakest": "goal",
        "persisted": False,
        "questions": [{"id": qid, "category": "goal", "prompt": prompt}],
        "answers": {},
    }


def test_redteam_cross_source_pending_then_complete_allows_next(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    folder = _sess(tmp_path)

    from agent_lab.session.clarifier import (
        get_clarifier_interview,
        persist_clarifier_interview,
        record_clarifier_answers,
    )

    first = _panel("clarify_panel", "q1", "Panel?")
    assert persist_clarifier_interview(folder, first)["persisted"] is True

    blocked = persist_clarifier_interview(folder, _panel("server", "s1", "Server?"))
    assert blocked["persisted"] is False
    assert blocked["reason"] == "cross_source_pending"
    assert blocked["interview"]["source"] == "clarify_panel"
    assert get_clarifier_interview(read_run_meta(folder))["source"] == "clarify_panel"

    public = record_clarifier_answers(folder, answers={"q1": "answered"})
    assert public is not None and public["status"] == "complete"

    allowed = persist_clarifier_interview(folder, _panel("server", "s2", "Server 2?"))
    assert allowed["persisted"] is True
    assert allowed["reason"] == "prior_complete"
    assert get_clarifier_interview(read_run_meta(folder))["source"] == "server"


def test_redteam_engine_always_on_build_carries_source_and_cross_source_blocked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Engine always on: vague build → source marker present; cross-source pending is always blocked."""
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_CLARIFIER", "1")
    folder = _sess(tmp_path)

    from agent_lab.session.clarifier import build_clarifier_interview, persist_clarifier_interview

    built = build_clarifier_interview("hi", is_new_session=True, human_message_count=1)
    assert built is not None
    assert built.get("source") == "clarity_engine", "engine always on → source marker present"

    first = _panel("clarify_panel", "q1", "Panel?")
    second = _panel("server", "q2", "Server?")
    persist_clarifier_interview(folder, first)
    result = persist_clarifier_interview(folder, second)
    assert result["persisted"] is False
    assert result["reason"] == "cross_source_pending"
    assert result["interview"]["questions"] == first["questions"]  # preserved


def test_redteam_same_source_divergent_pending_is_preserved(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A same-source write that would DROP an already-pending question is blocked."""
    folder = _sess(tmp_path)

    from agent_lab.session.clarifier import get_clarifier_interview, persist_clarifier_interview

    first = _panel("clarity_engine", "q1", "First?")
    assert persist_clarifier_interview(folder, first)["persisted"] is True
    # Same source, DIFFERENT id set (drops q1) → must be preserved, not clobbered.
    divergent = _panel("clarity_engine", "q2", "Second?")
    blocked = persist_clarifier_interview(folder, divergent)
    assert blocked["persisted"] is False
    assert blocked["reason"] == "same_source_divergent"
    assert get_clarifier_interview(read_run_meta(folder))["questions"][0]["id"] == "q1"
    # Same source, SUPERSET id set (keeps q1, adds q2) → allowed refinement.
    superset = {
        "version": 2,
        "status": "pending",
        "source": "clarity_engine",
        "questions": [
            {"id": "q1", "category": "goal", "prompt": "First refined?"},
            {"id": "q2", "category": "context", "prompt": "Second?"},
        ],
        "answers": {},
    }
    ok = persist_clarifier_interview(folder, superset)
    assert ok["persisted"] is True
    assert ok["reason"] == "same_source_update"


def test_redteam_plan_workflow_gate_visibility_and_approval_spine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST", "1")
    monkeypatch.delenv("AGENT_LAB_PIPELINE", raising=False)

    from agent_lab.human_inbox import has_pending_question
    from agent_lab.plan.workflow import get_plan_workflow

    vague = _sess(tmp_path)
    _init_plan_workflow(vague)
    _seed_goal(vague, "make the whole thing better somehow")
    hold = _tick(vague)
    run = read_run_meta(vague)
    assert hold["phase"] == "CLARIFY"
    assert hold["clarity_pending"] is True
    assert has_pending_question(run) is True
    assert get_plan_workflow(run)["phase"] != "APPROVED"
    assert (run.get("verified_loop") or {}).get("status") != "running"

    anchored = tmp_path / "anchored"
    anchored.mkdir()
    (anchored / "run.json").write_text("{}", encoding="utf-8")
    _init_plan_workflow(anchored)
    _seed_goal(anchored, "fix src/agent_lab/run_meta.py null check")
    assert _tick(anchored).get("advance") == "DRAFT"


def test_redteam_no_visible_question_path_does_not_deadlock(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST", "1")  # harvest enabled → dedup path
    monkeypatch.delenv("AGENT_LAB_PIPELINE", raising=False)

    import agent_lab.inbox.harvest as inbox_harvest
    from agent_lab.human_inbox import has_pending_question
    from agent_lab.plan.workflow import get_plan_workflow

    monkeypatch.setattr(inbox_harvest, "harvest_clarifier_questions", lambda run, prompts, **kwargs: None)

    folder = _sess(tmp_path)
    _init_plan_workflow(folder)
    _seed_goal(folder, "make the whole thing better somehow")
    tick = _tick(folder)
    run = read_run_meta(folder)
    assert tick.get("clarity_pending") is False
    assert tick.get("clarity_notice") == "clarity_no_visible_question"
    assert tick.get("advance") == "DRAFT"
    assert has_pending_question(run) is False
    assert get_plan_workflow(run)["phase"] == "DRAFT"


def test_redteam_import_cycle_multiple_fresh_orders() -> None:
    orders = [
        ["agent_lab.clarity", "agent_lab.clarifier_engine", "agent_lab.session.clarifier"],
        ["agent_lab.session.clarifier", "agent_lab.clarity", "agent_lab.clarifier_engine"],
        ["agent_lab.clarifier_engine", "agent_lab.session.clarifier", "agent_lab.clarity"],
    ]
    for order in orders:
        code = "import importlib\n" + "\n".join(f"importlib.import_module({name!r})" for name in order)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path.cwd() / "src")
        proc = subprocess.run(
            [sys.executable, "-c", code], cwd=Path.cwd(), env=env, text=True, capture_output=True, check=False
        )
        assert proc.returncode == 0, proc.stderr


def test_redteam_engine_questions_one_pass_with_stubbed_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "0")
    monkeypatch.delenv("AGENT_LAB_CLARITY_TOPOLOGY", raising=False)

    import agent_lab.agents.registry as reg

    calls: list[str] = []

    def fake_call_agent(agent, system, user, **_kwargs):  # noqa: ANN001, ANN202
        calls.append(str(agent))
        return "goal=0.4 constraints=0.4 criteria=0.4 context=0.4"

    monkeypatch.setattr(reg, "available_agents", lambda: ["codex", "claude", "cursor", "gemini"])
    monkeypatch.setattr(reg, "call_agent", fake_call_agent)

    from agent_lab.clarifier_engine import engine_questions

    _result, questions = engine_questions("make the entire product better somehow")
    assert questions
    assert len(calls) <= 4


def test_redteam_mock_determinism_and_anchor_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")

    from agent_lab.clarifier_engine import build_engine_interview, engine_questions

    vague = "make the whole thing better somehow"
    assert engine_questions(vague) == engine_questions(vague)
    assert build_engine_interview(vague, human_message_count=1) == build_engine_interview(vague, human_message_count=1)

    anchored = "fix src/agent_lab/run_meta.py null check"
    _result, questions = engine_questions(anchored)
    assert questions == []
    assert build_engine_interview(anchored, human_message_count=1) is None
