"""Sprint C — per-turn lead, R1 ordering, discuss-only task policy, human synthesis."""

from __future__ import annotations

import re
from typing import Any

from agent_lab.room_tasks import RUN_TEAM_LEAD_KEY, ensure_team_lead, team_lead

RUN_TURN_LEADS_KEY = "turn_leads"
_GO_LEAD_RE = re.compile(
    r"(?:^|\n)\s*(?:GO|리드|lead)\s*(?:[:：]\s*|\s+)(cursor|codex|claude)\b",
    re.I,
)
_SYNTHESIS_MARKER = "[human synthesis — 턴 요약]"


def parse_go_lead_from_message(text: str) -> str | None:
    m = _GO_LEAD_RE.search(text or "")
    if not m:
        return None
    return m.group(1).strip().lower()


def turn_leads_map(run_meta: dict[str, Any] | None) -> dict[str, str]:
    if not run_meta:
        return {}
    raw = run_meta.get(RUN_TURN_LEADS_KEY)
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v).strip().lower() for k, v in raw.items() if str(v).strip()}


def record_turn_lead(
    run_meta: dict[str, Any],
    human_turn: int,
    agent: str,
) -> str:
    lead = str(agent or "").strip().lower() or team_lead(run_meta)
    leads = turn_leads_map(run_meta)
    leads[str(human_turn)] = lead
    run_meta[RUN_TURN_LEADS_KEY] = leads
    run_meta[RUN_TEAM_LEAD_KEY] = lead
    return lead


def resolve_turn_lead(
    run_meta: dict[str, Any],
    human_turn: int,
    active_agents: list[str],
    *,
    user_message: str = "",
) -> str:
    """Pick orchestrator for this human turn (explicit GO/리드, map, or rotate)."""
    ensure_team_lead(run_meta)
    parsed = parse_go_lead_from_message(user_message)
    if parsed and parsed in {a.lower() for a in active_agents}:
        return record_turn_lead(run_meta, human_turn, parsed)

    leads = turn_leads_map(run_meta)
    existing = leads.get(str(human_turn))
    if existing and existing in {a.lower() for a in active_agents}:
        run_meta[RUN_TEAM_LEAD_KEY] = existing
        return existing

    pool = [a.strip().lower() for a in active_agents if str(a).strip()]
    if not pool:
        return ensure_team_lead(run_meta)
    idx = max(0, human_turn - 1) % len(pool)
    return record_turn_lead(run_meta, human_turn, pool[idx])


def is_discuss_only_turn(
    *,
    mode: str,
    synthesize: bool,
    consensus_mode: bool,
) -> bool:
    return mode == "discuss" and not synthesize and not consensus_mode


def resolve_send_receipt(
    *,
    mode: str,
    synthesize: bool,
    consensus_mode: bool,
    consensus: dict[str, Any] | None = None,
    plan_updated: bool = False,
    status: str = "completed",
    plan_workflow_phase: str | None = None,
) -> str:
    """Turn outcome label for UI receipts and run.json turn snapshots."""
    if status == "cancelled":
        return "discuss_saved"
    if consensus_mode and consensus and consensus.get("status") == "reached":
        return "consensus_done"
    from agent_lab.plan_workflow import plan_workflow_send_receipt

    pw_receipt = plan_workflow_send_receipt(plan_workflow_phase)
    if pw_receipt:
        return pw_receipt
    if mode == "plan" or synthesize or plan_updated:
        return "plan_updated"
    return "discuss_saved"


def lead_discuss_role_block(agent: str, run_meta: dict[str, Any] | None) -> str:
    """Short prepend for team lead on pure discuss turns."""
    from agent_lab.room_tasks import team_lead

    aid = str(agent or "").strip().lower()
    if aid != team_lead(run_meta):
        return ""
    return (
        "[턴 리드 — discuss]\n"
        "동료 발화를 종합하고, 미배정 작업은 팀원에게 claim·제안하도록 조율하세요. "
        "이 턴에서는 전체 패치 구현보다 합의·분해·[PROPOSED:]에 집중하세요."
    )


def should_assign_tasks_on_turn(
    *,
    mode: str,
    synthesize: bool,
    consensus_mode: bool,
) -> bool:
    """Discuss turns harvest tasks but do not pre-claim for teammates."""
    if consensus_mode or synthesize or mode == "plan":
        return True
    return False


def team_r1_split(
    agents: list[str],
    run_meta: dict[str, Any] | None,
) -> tuple[list[str], list[str]]:
    """R1: teammates parallel first, lead runs last with full peer context."""
    lead = team_lead(run_meta)
    pool = [str(a).strip().lower() for a in agents if str(a).strip()]
    teammates = [a for a in pool if a != lead]
    if lead in pool and teammates:
        return teammates, [lead]
    return pool, []


def normalize_turn_profile(profile: str | None) -> str:
    p = (profile or "analyze").strip().lower()
    if p == "discuss":
        return "analyze"
    if p == "review":
        return "free"
    if p in ("quick", "analyze", "free", "specialist", "verified"):
        return p
    return "analyze"


def count_parallel_r1_agents(turn_messages: list[Any]) -> int:
    from agent_lab.room_chat_channels import is_peer_visibility

    agents: set[str] = set()
    for m in turn_messages:
        if getattr(m, "role", None) != "agent":
            continue
        if is_peer_visibility(getattr(m, "visibility", None)):
            continue
        pr = getattr(m, "parallel_round", None) or 1
        if pr != 1:
            continue
        agent = getattr(m, "agent", None)
        if agent:
            agents.add(str(agent).strip().lower())
    return len(agents)


def should_emit_human_turn_synthesis(
    turn_profile: str | None,
    turn_messages: list[Any],
    *,
    agents_used: list[str] | None = None,
) -> bool:
    """Emit turn summary only for ♾️ (free) or analyze with 3+ parallel R1 agents."""
    profile = normalize_turn_profile(turn_profile)
    if profile == "free":
        return True
    if profile != "analyze":
        return False
    parallel = count_parallel_r1_agents(turn_messages)
    scheduled = len({str(a).strip().lower() for a in (agents_used or []) if str(a).strip()})
    return max(parallel, scheduled) >= 3


def build_human_turn_synthesis(
    turn_messages: list[Any],
    *,
    lead: str,
    human_excerpt: str,
) -> str:
    from agent_lab.agents.registry import label
    from agent_lab.room_chat_channels import is_peer_visibility

    lines = [
        _SYNTHESIS_MARKER,
        f"리드: {lead}",
        "",
        "**Human**",
        (human_excerpt or "").strip()[:2000],
        "",
        "**에이전트 (요약)**",
    ]
    for m in turn_messages:
        if getattr(m, "role", None) != "agent":
            continue
        if is_peer_visibility(getattr(m, "visibility", None)):
            continue
        pr = getattr(m, "parallel_round", None) or 1
        if pr > 1:
            continue
        agent = getattr(m, "agent", None) or "agent"
        body = (getattr(m, "content", None) or "").strip()
        if not body:
            continue
        lines.append(f"- **{label(agent)}**: {body[:500]}")
    if len(lines) <= 5:
        lines.append("- (에이전트 응답 없음)")
    return "\n".join(lines)


def is_human_synthesis_message(content: str, visibility: str | None = None) -> bool:
    if visibility == "human" and (content or "").startswith(_SYNTHESIS_MARKER):
        return True
    return (content or "").startswith(_SYNTHESIS_MARKER)
