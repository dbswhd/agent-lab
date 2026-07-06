"""MCP-first Human Inbox policy — single-flight, lead-only discuss gates (Phase C)."""

from __future__ import annotations

from agent_lab.run.state import RunStateLike
import os
from pathlib import Path

_DISCUSS_LANE = "discuss"
_EXECUTE_LANE = "execute"


def mcp_first_inbox_policy_active() -> bool:
    """True when orchestrator harvest is off (MCP-first default)."""
    from agent_lab.inbox.harvest import orchestrator_inbox_harvest_enabled

    return not orchestrator_inbox_harvest_enabled()


def inbox_gate_owner(run_meta: RunStateLike | None) -> str:
    """Agent allowed to call ``ask_human`` on discuss lane under MCP-first."""
    from agent_lab.room.tasks import team_lead

    lead = team_lead(run_meta)
    if not mcp_first_inbox_policy_active():
        return lead
    if lead != "cursor":
        return lead
    agents_raw = (run_meta or {}).get("agents") or (run_meta or {}).get("room_agents") or []
    active = {str(a).strip().lower() for a in agents_raw if str(a).strip()}
    for candidate in ("codex", "claude", "kimi_work"):
        if candidate in active:
            return candidate
    return lead


def discuss_inbox_mcp_lane_enabled(run_meta: RunStateLike | None) -> bool:
    """Lane-level discuss inbox MCP (before per-agent policy).

    Orchestrator harvest stays off on Fast; peer ``ask_human`` / ``propose_build`` MCP is allowed.
    """
    from agent_lab.plan.workflow import plan_workflow_wants_inbox_mcp

    if run_meta and plan_workflow_wants_inbox_mcp(run_meta):
        from agent_lab.cursor.inbox_mcp import plan_inbox_mcp_enabled

        return plan_inbox_mcp_enabled()
    if run_meta and mcp_first_inbox_policy_active():
        from agent_lab.cursor.inbox_mcp import execute_inbox_mcp_enabled

        return execute_inbox_mcp_enabled()
    return False


def discuss_inbox_mcp_agent_allowed(run_meta: RunStateLike | None, agent_id: str) -> bool:
    """Per-agent discuss inbox MCP under MCP-first lead-only rules."""
    if not discuss_inbox_mcp_lane_enabled(run_meta):
        return False
    if not mcp_first_inbox_policy_active():
        return True
    agent = str(agent_id or "").strip().lower()
    from agent_lab.room.preset import is_fast_room_session
    from agent_lab.room.tasks import team_lead

    if run_meta and is_fast_room_session(run_meta):
        return agent == team_lead(run_meta)
    if agent == "cursor":
        return False
    owner = inbox_gate_owner(run_meta)
    if agent != owner:
        return False
    from agent_lab.plan.workflow import plan_workflow_wants_inbox_mcp

    if run_meta and plan_workflow_wants_inbox_mcp(run_meta):
        return True
    return True


def _policy_lane_from_env() -> str:
    raw = os.getenv("AGENT_LAB_INBOX_POLICY_LANE", "").strip().lower()
    if raw in (_DISCUSS_LANE, _EXECUTE_LANE):
        return raw
    return _DISCUSS_LANE


def _caller_agent_from_env(explicit: str | None) -> str:
    return str(explicit or os.getenv("AGENT_LAB_INBOX_CALLER_AGENT") or "").strip().lower()


def enforce_mcp_ask_human_policy(
    folder: Path,
    *,
    caller_agent: str | None = None,
    policy_lane: str | None = None,
) -> None:
    """Raise ``ValueError`` when MCP-first policy blocks ``ask_human``."""
    if not mcp_first_inbox_policy_active():
        return
    from agent_lab.run.meta import read_run_meta
    from agent_lab.human_inbox import has_pending_question

    run = read_run_meta(folder)
    if has_pending_question(run):
        raise ValueError("pending Human Inbox question blocks a second ask_human")

    lane = (policy_lane or _policy_lane_from_env()).strip().lower()
    if lane != _DISCUSS_LANE:
        return

    agent = _caller_agent_from_env(caller_agent)
    if not agent:
        return

    from agent_lab.room.preset import is_fast_room_session
    from agent_lab.room.tasks import team_lead

    if is_fast_room_session(run):
        if agent != team_lead(run):
            raise ValueError(f"only team lead ({team_lead(run)}) may call ask_human on Fast")
        return

    if agent == "cursor":
        raise ValueError("cursor must not call ask_human on discuss — delegate to team lead")

    owner = inbox_gate_owner(run)
    if agent != owner:
        raise ValueError(f"only inbox gate owner ({owner}) may call ask_human on discuss")


def enforce_mcp_propose_build_policy(
    folder: Path,
    *,
    caller_agent: str | None = None,
) -> None:
    """Raise ``ValueError`` when MCP-first policy blocks ``propose_build``."""
    if not mcp_first_inbox_policy_active():
        return
    from agent_lab.run.meta import read_run_meta
    from agent_lab.room.tasks import team_lead

    agent = _caller_agent_from_env(caller_agent)
    if not agent:
        return
    run = read_run_meta(folder)
    lead = team_lead(run)
    if agent != lead:
        raise ValueError(f"only team lead ({lead}) may call propose_build")


def enforce_mcp_plan_phase_advance_policy(
    folder: Path,
    *,
    caller_agent: str | None = None,
) -> None:
    """Gate owner only; Human approve / execute gates remain server-side."""
    from agent_lab.plan.workflow import is_plan_workflow_active, plan_workflow_phase
    from agent_lab.run.meta import read_run_meta

    run = read_run_meta(folder)
    if not is_plan_workflow_active(run):
        raise ValueError("plan workflow is not active")
    phase = plan_workflow_phase(run)
    if phase == "APPROVED":
        raise ValueError("plan already approved — use execute lane")
    agent = _caller_agent_from_env(caller_agent)
    if not agent:
        return
    owner = inbox_gate_owner(run)
    if agent != owner:
        raise ValueError(f"only inbox gate owner ({owner}) may call plan_phase_advance")


def enforce_mcp_run_clarity_interview_policy(
    folder: Path,
    *,
    caller_agent: str | None = None,
) -> None:
    """Gate owner only; CLARIFY/INTAKE phases only."""
    from agent_lab.plan.workflow import is_plan_workflow_active, plan_workflow_phase
    from agent_lab.run.meta import read_run_meta

    run = read_run_meta(folder)
    if not is_plan_workflow_active(run):
        raise ValueError("plan workflow is not active")
    phase = plan_workflow_phase(run)
    if phase not in {"INTAKE", "CLARIFY"}:
        raise ValueError(f"run_clarity_interview requires CLARIFY (current={phase})")
    agent = _caller_agent_from_env(caller_agent)
    if not agent:
        return
    owner = inbox_gate_owner(run)
    if agent != owner:
        raise ValueError(f"only inbox gate owner ({owner}) may call run_clarity_interview")


def inbox_mcp_env_overrides(
    *,
    caller_agent: str | None = None,
    policy_lane: str | None = None,
) -> dict[str, str]:
    out: dict[str, str] = {}
    if caller_agent:
        out["AGENT_LAB_INBOX_CALLER_AGENT"] = str(caller_agent).strip().lower()
    if policy_lane:
        out["AGENT_LAB_INBOX_POLICY_LANE"] = str(policy_lane).strip().lower()
    return out
