"""Fast preset — orchestrator harvest off; agent inbox MCP on for team lead."""

from __future__ import annotations

from typing import Any

import pytest

from agent_lab.cursor.inbox_mcp import discuss_inbox_mcp_enabled
from agent_lab.inbox.harvest import (
    discuss_fork_harvest_allowed,
    harvest_discuss_questions,
    orchestrator_inbox_harvest_enabled,
)
from agent_lab.plan.workflow import plan_workflow_wants_inbox_mcp


def test_discuss_inbox_mcp_enabled_for_fast_lead() -> None:
    run: dict[str, Any] = {"room_preset": "fast", "team_lead": "codex"}
    assert discuss_inbox_mcp_enabled(run, agent_id="codex") is True
    assert discuss_inbox_mcp_enabled(run, agent_id="claude") is False


def test_discuss_inbox_mcp_fast_cursor_lead() -> None:
    run: dict[str, Any] = {
        "room_preset": "fast",
        "team_lead": "cursor",
        "agents": ["cursor"],
    }
    assert discuss_inbox_mcp_enabled(run, agent_id="cursor") is True


def test_discuss_inbox_mcp_quick_mode_lead() -> None:
    run: dict[str, Any] = {
        "user_mode": "quick",
        "plan_intent": "none",
        "team_lead": "codex",
    }
    assert discuss_inbox_mcp_enabled(run, agent_id="codex") is True


def test_orchestrator_harvest_disabled_by_default() -> None:
    assert orchestrator_inbox_harvest_enabled() is False


def test_discuss_mcp_gate_owner_on_supervisor_when_harvest_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST", raising=False)
    run: dict[str, Any] = {
        "room_preset": "supervisor",
        "team_lead": "cursor",
        "agents": ["cursor", "codex", "claude"],
    }
    assert discuss_inbox_mcp_enabled(run, agent_id="codex") is True
    assert discuss_inbox_mcp_enabled(run, agent_id="cursor") is False


def test_discuss_mcp_off_supervisor_when_legacy_harvest_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST", "1")
    run: dict[str, Any] = {"room_preset": "supervisor", "team_lead": "codex"}
    assert discuss_inbox_mcp_enabled(run, agent_id="codex") is False
    assert discuss_inbox_mcp_enabled(run, agent_id="claude") is False


def test_plan_workflow_inbox_mcp_disabled_for_fast() -> None:
    run: dict[str, Any] = {
        "room_preset": "fast",
        "plan_workflow": {"enabled": True, "phase": "CLARIFY"},
    }
    assert plan_workflow_wants_inbox_mcp(run) is False


def test_harvest_discuss_skipped_for_fast() -> None:
    run_meta: dict[str, Any] = {"room_preset": "fast"}
    created = harvest_discuss_questions(
        run_meta,
        [],
        plan_md="## 쟁점 / 미결정\n- open item",
        mode="discuss",
    )
    assert created == []
    assert "human_inbox" not in run_meta


def test_harvest_discuss_skipped_by_default_supervisor() -> None:
    run_meta: dict[str, Any] = {"room_preset": "supervisor"}
    created = harvest_discuss_questions(
        run_meta,
        [],
        plan_md="## 쟁점 / 미결정\n- open item",
        mode="discuss",
    )
    assert created == []
    assert "human_inbox" not in run_meta


def test_harvest_discuss_fork_without_legacy_orchestrator_flag() -> None:
    import json

    from dataclasses import dataclass

    @dataclass
    class _Msg:
        role: str
        agent: str | None = None
        content: str = ""

    payload = {
        "topic": "eval harness 연결 우선순위",
        "options": [
            {"label": "pytest XML → result_map adapter 먼저", "refs": ["eval_harness.py:56-60"]},
            {"label": "Docker sandbox 먼저 (격리 선행)", "refs": ["sandbox_policy.py:7"]},
        ],
    }
    fork_body = "```decision-fork\n" + json.dumps(payload, ensure_ascii=False) + "\n```"

    run_meta: dict[str, Any] = {"room_preset": "supervisor"}
    messages = [
        _Msg(role="user", content="topic"),
        _Msg(role="agent", agent="claude", content=fork_body),
    ]
    created = harvest_discuss_questions(run_meta, messages, human_turn=1, mode="discuss")
    assert len(created) == 1
    item = created[0]
    assert item["trigger"] == "T-Q1"
    assert item["prompt"] == "eval harness 연결 우선순위"
    assert len(item["options"]) == 2
    assert discuss_fork_harvest_allowed(run_meta) is True


def test_harvest_discuss_runs_when_legacy_flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST", "1")
    run_meta: dict[str, Any] = {"room_preset": "supervisor"}
    created = harvest_discuss_questions(
        run_meta,
        [],
        plan_md="## 쟁점 / 미결정\n- open item",
        mode="discuss",
    )
    assert len(created) == 1
