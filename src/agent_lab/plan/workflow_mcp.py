from __future__ import annotations

"""Plan workflow MCP skill authority (P2/P3)."""

from pathlib import Path
from typing import Any

from agent_lab.plan.workflow_state import plan_workflow_phase
from agent_lab.run.meta import read_run_meta


def mcp_advance_plan_workflow_phase(
    folder: Path,
    *,
    target_phase: str,
    reason: str | None = None,
    caller_agent: str | None = None,
) -> dict[str, Any]:
    """Skill/MCP authority — forward-only FSM advance via runtime dispatch."""
    from agent_lab.runtime.events import RuntimeEvent
    from agent_lab.runtime.runtime import dispatch

    out = dispatch(
        folder,
        RuntimeEvent.PLAN_WORKFLOW_ADVANCE,
        {
            "target_phase": target_phase,
            "reason": reason,
            "caller_agent": caller_agent,
        },
    )
    if out.skipped:
        raise ValueError(str(out.reason or "plan_workflow_advance_blocked"))
    if isinstance(out.result, dict):
        return out.result
    return {"ok": out.handled}


def mcp_run_clarity_interview(
    folder: Path,
    *,
    caller_agent: str | None = None,
) -> dict[str, Any]:
    """Skill/MCP authority — score clarity panel and surface clarifier questions via Human Inbox."""
    from agent_lab.clarity import _mission_clarity_text, clarity_threshold_met, score_clarity
    from agent_lab.inbox.mcp_policy import enforce_mcp_run_clarity_interview_policy

    enforce_mcp_run_clarity_interview_policy(folder, caller_agent=caller_agent)
    run = read_run_meta(folder)
    text = _mission_clarity_text(run)
    agents_raw = run.get("agents") or run.get("room_agents") or []
    agents = [str(a).strip() for a in agents_raw if str(a).strip()]
    panel = score_clarity(text, agents=agents or None)
    threshold_met = clarity_threshold_met(run)
    payload: dict[str, Any] = {
        "ok": True,
        "threshold_met": threshold_met,
        "clarity_panel": panel,
        "phase": plan_workflow_phase(run),
    }
    if threshold_met:
        payload["hold"] = None
        payload["notice"] = "clarity_threshold_met"
        return payload
    from agent_lab.plan.workflow_clarify import clarity_gate_questions

    hold = clarity_gate_questions(folder, read_run_meta(folder))
    payload["hold"] = hold
    if hold and hold.get("clarity_pending"):
        payload["notice"] = hold.get("clarity_notice") or "clarity_pending"
    elif hold:
        payload["notice"] = hold.get("clarity_notice")
    return payload
