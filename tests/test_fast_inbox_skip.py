"""Fast preset — orchestrator harvest off; agent inbox MCP on for team lead."""

from __future__ import annotations

from typing import Any

import pytest

from agent_lab.cursor_inbox_mcp import discuss_inbox_mcp_enabled
from agent_lab.inbox_harvest import (
    harvest_discuss_questions,
    orchestrator_inbox_harvest_enabled,
)
from agent_lab.plan_workflow import plan_workflow_wants_inbox_mcp


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
