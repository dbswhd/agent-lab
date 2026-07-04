from __future__ import annotations

"""Plan workflow MCP skill authority (P2/P3)."""

from pathlib import Path
from typing import Any

from agent_lab.plan.workflow_state import (
    MCP_ADVANCE_TARGETS,
    PLAN_FSM_ORDER,
    get_plan_workflow,
    plan_workflow_phase,
    set_plan_workflow_phase,
)
from agent_lab.run.meta import read_run_meta

def mcp_advance_plan_workflow_phase(
    folder: Path,
    *,
    target_phase: str,
    reason: str | None = None,
    caller_agent: str | None = None,
) -> dict[str, Any]:
    """Skill/MCP authority — forward-only FSM advance; Human approve unchanged."""
    from agent_lab.inbox.mcp_policy import enforce_mcp_plan_phase_advance_policy
    from agent_lab.room.turn_policy import stamp_pending_skill_intent, turn_policy_enabled

    enforce_mcp_plan_phase_advance_policy(folder, caller_agent=caller_agent)
    target = str(target_phase or "").strip().upper()
    if target not in MCP_ADVANCE_TARGETS:
        allowed = ", ".join(sorted(MCP_ADVANCE_TARGETS))
        raise ValueError(f"target_phase must be one of: {allowed}")
    if target == "APPROVED":
        raise ValueError("APPROVED requires Human plan approve — not plan_phase_advance")

    run = read_run_meta(folder)
    current = plan_workflow_phase(run)
    order = list(PLAN_FSM_ORDER)
    if current not in order or target not in order:
        raise ValueError("invalid plan workflow phase")
    if order.index(target) <= order.index(current):
        raise ValueError(f"forward advance only (current={current}, target={target})")

    set_plan_workflow_phase(folder, target)  # type: ignore[arg-type]
    if turn_policy_enabled() and target in {"DRAFT", "REFINE", "HUMAN_PENDING"}:
        stamp_pending_skill_intent(folder, "plan_draft")
    payload: dict[str, Any] = {
        "ok": True,
        "previous_phase": current,
        "phase": target,
    }
    if reason and str(reason).strip():
        payload["reason"] = str(reason).strip()[:500]
    return payload


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
