"""CLARIFY phase — MCP-first: legacy orchestrator harvest stays off (no force-on)."""

from __future__ import annotations

from typing import Any

from agent_lab.inbox.harvest import harvest_discuss_questions, orchestrator_inbox_harvest_allowed


def test_harvest_not_forced_in_plan_clarify_under_mcp_first() -> None:
    run_meta: dict[str, Any] = {
        "room_preset": "supervisor",
        "plan_workflow": {"enabled": True, "phase": "CLARIFY"},
    }
    # Plan CLARIFY no longer force-enables legacy harvest — questions go via MCP ask_human.
    assert orchestrator_inbox_harvest_allowed(run_meta) is False


def test_harvest_discuss_noop_in_plan_clarify_under_mcp_first() -> None:
    run_meta: dict[str, Any] = {
        "room_preset": "supervisor",
        "plan_workflow": {"enabled": True, "phase": "CLARIFY"},
    }
    created = harvest_discuss_questions(
        run_meta,
        [],
        plan_md="## 쟁점 / 미결정\n- fork A vs B",
        mode="discuss",
    )
    assert created == []
    assert run_meta.get("human_inbox", []) == []
