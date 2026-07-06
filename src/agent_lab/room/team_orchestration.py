"""Sprint C — per-turn lead, R1 ordering, discuss-only task policy, human synthesis."""

from __future__ import annotations

from agent_lab.room._typing import agent_label
import re
from typing import Any

from agent_lab.run.state import RunStateLike

from agent_lab import provider_registry
from agent_lab.room.tasks import RUN_TEAM_LEAD_KEY, ensure_team_lead, team_lead

RUN_TURN_LEADS_KEY = "turn_leads"
_GO_LEAD_AGENT_IDS = "|".join(re.escape(pid) for pid in provider_registry.provider_ids())
_GO_LEAD_RE = re.compile(
    rf"(?:^|\n)\s*(?:GO|리드|lead)\s*(?:[:：]\s*|\s+)({_GO_LEAD_AGENT_IDS})\b",
    re.I,
)
_SYNTHESIS_MARKER = "[human synthesis — 턴 요약]"


def parse_go_lead_from_message(text: str) -> str | None:
    m = _GO_LEAD_RE.search(text or "")
    if not m:
        return None
    return m.group(1).strip().lower()


def turn_leads_map(run_meta: RunStateLike | None) -> dict[str, str]:
    if not run_meta:
        return {}
    raw = run_meta.get(RUN_TURN_LEADS_KEY)
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v).strip().lower() for k, v in raw.items() if str(v).strip()}


def record_turn_lead(
    run_meta: RunStateLike,
    human_turn: int,
    agent: str,
) -> str:
    from agent_lab.run.meta import stamp_run_meta

    lead = str(agent or "").strip().lower() or team_lead(run_meta)
    leads = turn_leads_map(run_meta)
    leads[str(human_turn)] = lead
    stamp_run_meta(
        run_meta,
        **{RUN_TURN_LEADS_KEY: leads, RUN_TEAM_LEAD_KEY: lead},
    )
    return lead


def reconcile_team_lead(run_meta: RunStateLike, active_agents: list[str]) -> str:
    """Ensure team_lead references an agent in the active roster (model-flexible)."""
    from agent_lab.run.meta import stamp_run_meta

    pool = [str(a).strip().lower() for a in active_agents if str(a).strip()]
    lead = team_lead(run_meta)
    if lead in pool:
        return lead
    if pool:
        stamp_run_meta(run_meta, **{RUN_TEAM_LEAD_KEY: pool[0]})
        return pool[0]
    return ensure_team_lead(run_meta)


def resolve_turn_lead(
    run_meta: RunStateLike,
    human_turn: int,
    active_agents: list[str],
    *,
    user_message: str = "",
) -> str:
    """Pick orchestrator for this human turn (explicit GO/리드, map, or rotate)."""
    ensure_team_lead(run_meta)
    parsed = parse_go_lead_from_message(user_message)
    if parsed and parsed in {a.lower() for a in active_agents}:
        record_turn_lead(run_meta, human_turn, parsed)
        return reconcile_team_lead(run_meta, active_agents)

    leads = turn_leads_map(run_meta)
    existing = leads.get(str(human_turn))
    if existing and existing in {a.lower() for a in active_agents}:
        from agent_lab.run.meta import stamp_run_meta

        stamp_run_meta(run_meta, **{RUN_TEAM_LEAD_KEY: existing})
        return reconcile_team_lead(run_meta, active_agents)

    pool = [a.strip().lower() for a in active_agents if str(a).strip()]
    if not pool:
        return ensure_team_lead(run_meta)
    idx = max(0, human_turn - 1) % len(pool)
    record_turn_lead(run_meta, human_turn, pool[idx])
    return reconcile_team_lead(run_meta, active_agents)


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
    turn_policy: dict[str, Any] | None = None,
    turn_kind: str | None = None,
) -> str:
    """Turn outcome label for UI receipts and run.json turn snapshots."""
    if status == "cancelled":
        return "discuss_saved"
    from agent_lab.room.turn_policy import turn_policy_enabled

    if turn_policy_enabled() and isinstance(turn_policy, dict):
        trigger = str(turn_policy.get("scribe_trigger") or "")
        if consensus_mode and consensus and consensus.get("status") == "reached":
            return "consensus_done"
        from agent_lab.plan.workflow import plan_workflow_send_receipt

        pw_receipt = plan_workflow_send_receipt(plan_workflow_phase)
        if pw_receipt:
            return pw_receipt
        if turn_kind == "plan_side_effect" or trigger == "synthesize_only":
            return "plan_updated"
        if turn_policy.get("run_scribe") or plan_updated:
            return "plan_updated"
        return "discuss_saved"
    if consensus_mode and consensus and consensus.get("status") == "reached":
        return "consensus_done"
    from agent_lab.plan.workflow import plan_workflow_send_receipt

    pw_receipt = plan_workflow_send_receipt(plan_workflow_phase)
    if pw_receipt:
        return pw_receipt
    if mode == "plan" or synthesize or plan_updated:
        return "plan_updated"
    return "discuss_saved"


def lead_discuss_role_block(agent: str, run_meta: RunStateLike | None) -> str:
    """Short prepend for team lead on pure discuss turns."""
    from agent_lab.room.tasks import team_lead

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


def lead_last_r1_enabled(run_meta: RunStateLike | None) -> bool:
    """Whether R1 should run teammates first, then lead with peer context.

    §3.2.1: light discuss (``discuss_light``) disables lead-last so all agents
    run in one fully parallel wave. Plan / consensus / peer-review keep lead-last.
    """
    if not isinstance(run_meta, dict):
        return True
    return not bool(run_meta.get("discuss_light"))


def team_r1_split(
    agents: list[str],
    run_meta: RunStateLike | None,
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
    from agent_lab.room.chat_channels import is_peer_visibility

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
    from agent_lab.room.chat_channels import is_peer_visibility

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
        lines.append(f"- **{agent_label(agent)}**: {body[:500]}")
    if len(lines) <= 5:
        lines.append("- (에이전트 응답 없음)")
    return "\n".join(lines)


def is_human_synthesis_message(content: str, visibility: str | None = None) -> bool:
    if visibility == "human" and (content or "").startswith(_SYNTHESIS_MARKER):
        return True
    return (content or "").startswith(_SYNTHESIS_MARKER)
