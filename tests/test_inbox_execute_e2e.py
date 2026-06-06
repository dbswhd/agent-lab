"""Execute-lane Human Inbox E2E — MCP wait/resolve without live Cursor/Codex."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from agent_lab.human_inbox import (
    create_inbox_item,
    create_mcp_build_and_wait,
    create_mcp_question_and_wait,
    execute_inbox_build_go,
    resolve_inbox_item,
)
from agent_lab.run_meta import read_run_meta


@pytest.fixture
def session_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "sess-e2e"
    folder.mkdir()
    (folder / "run.json").write_text('{"human_inbox": []}', encoding="utf-8")
    return folder


def test_mcp_ask_human_threaded_resolve(session_folder: Path):
    def _resolve() -> None:
        time.sleep(0.05)
        run = read_run_meta(session_folder)
        pending = [i for i in run.get("human_inbox", []) if i.get("status") == "pending"]
        assert len(pending) == 1
        resolve_inbox_item(
            session_folder,
            pending[0]["id"],
            selected=["a"],
            append_chat=False,
        )

    threading.Thread(target=_resolve, daemon=True).start()
    result = create_mcp_question_and_wait(
        session_folder,
        question="Which scope?",
        options=[
            {"id": "a", "label": "VU only"},
            {"id": "b", "label": "VU + Theme"},
        ],
    )
    assert result["selected"] == ["a"]


def test_mcp_propose_build_go_threaded_resolve(session_folder: Path):
    def _resolve() -> None:
        time.sleep(0.05)
        run = read_run_meta(session_folder)
        pending = [i for i in run.get("human_inbox", []) if i.get("status") == "pending"]
        assert pending[0]["kind"] == "build"
        resolve_inbox_item(
            session_folder,
            pending[0]["id"],
            decision="go",
            append_chat=False,
        )

    threading.Thread(target=_resolve, daemon=True).start()
    result = create_mcp_build_and_wait(
        session_folder,
        summary="Add parser helper",
        action_ref="now:1",
    )
    assert result["decision"] == "go"
    assert execute_inbox_build_go(session_folder) is True


def test_execute_inbox_build_go_false_without_go(session_folder: Path):
    create_inbox_item(
        session_folder,
        kind="build",
        source="mcp_propose_build",
        prompt="Build?",
        action_ref="now:1",
    )
    item_id = read_run_meta(session_folder)["human_inbox"][0]["id"]
    resolve_inbox_item(session_folder, item_id, decision="defer", append_chat=False)
    assert execute_inbox_build_go(session_folder) is False


def test_plan_execute_inbox_gate_skips_implement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from agent_lab.plan_actions import PlanAction
    from agent_lab.plan_execute import _call_execute_agent

    session = tmp_path / "sess"
    session.mkdir()
    (session / "run.json").write_text('{"human_inbox": []}', encoding="utf-8")

    calls: list[list[str]] = []

    def _respond_session(system, prompts, **kwargs):
        calls.append(list(prompts))
        extra = kwargs.get("extra_prompts_if_gate") or []
        gate = kwargs.get("gate")
        if kwargs.get("gate_after") == 0 and gate and not gate():
            return "plan-only"
        calls.append(extra)
        return "plan+implement"

    monkeypatch.setattr("agent_lab.agents.cursor_agent.respond_session", _respond_session)

    action = PlanAction(
        index=1,
        kind="now",
        what="fix parser",
        where="plan_actions.py",
        verify="pytest",
        refs=(),
        raw="",
    )
    out = _call_execute_agent(
        "cursor",
        user="ignored",
        permissions={},
        cwd=tmp_path,
        on_activity=None,
        verify="pytest",
        session_folder=session,
        inbox_mcp=True,
        action=action,
    )
    assert out == "plan-only"
    assert len(calls) == 1
    assert "plan-first" in calls[0][0].lower()


def test_plan_execute_inbox_gate_runs_implement_after_go(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from agent_lab.human_inbox import create_inbox_item, resolve_inbox_item
    from agent_lab.plan_actions import PlanAction
    from agent_lab.plan_execute import _call_execute_agent

    session = tmp_path / "sess"
    session.mkdir()
    item = create_inbox_item(
        session,
        kind="build",
        source="mcp_propose_build",
        prompt="GO?",
        action_ref="now:1",
    )
    resolve_inbox_item(session, item["id"], decision="go", append_chat=False)

    seen: list[str] = []

    def _respond_session(system, prompts, **kwargs):
        seen.append("plan")
        extra = kwargs.get("extra_prompts_if_gate") or []
        gate = kwargs.get("gate")
        if gate and gate():
            seen.extend("implement" if "implement phase" in p.lower() else "other" for p in extra)
        return "done"

    monkeypatch.setattr("agent_lab.agents.cursor_agent.respond_session", _respond_session)

    action = PlanAction(
        index=1,
        kind="now",
        what="fix parser",
        where="plan_actions.py",
        verify="pytest",
        refs=(),
        raw="",
    )
    _call_execute_agent(
        "cursor",
        user="ignored",
        permissions={},
        cwd=tmp_path,
        on_activity=None,
        verify="pytest",
        session_folder=session,
        inbox_mcp=True,
        action=action,
    )
    assert seen == ["plan", "implement", "other"]
