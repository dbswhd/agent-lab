"""Fast preset skips orchestrator inbox harvest and discuss inbox MCP."""

from __future__ import annotations

from typing import Any

from agent_lab.cursor_inbox_mcp import discuss_inbox_mcp_enabled
from agent_lab.inbox_harvest import harvest_discuss_questions
from agent_lab.plan_workflow import plan_workflow_wants_inbox_mcp


def test_discuss_inbox_mcp_disabled_for_fast_preset() -> None:
    assert discuss_inbox_mcp_enabled({"room_preset": "fast"}) is False
    assert discuss_inbox_mcp_enabled({"room_preset": "supervisor"}) is False
    assert discuss_inbox_mcp_enabled({"user_mode": "quick", "plan_intent": "none"}) is False


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
