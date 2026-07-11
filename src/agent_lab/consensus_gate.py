"""Consensus gate for AGENT_LAB_PIPELINE (CONSENSUS mode).

Reuses the existing ConsensusPolicy plus the Room's consensus signal to decide whether the Room
reached consensus before plan.md may be finalized (DISCUSS -> PLAN_GATE). This module is read-only
over the Room's consensus state — the multi-agent debate engine (room_consensus_rounds) is
unchanged; consensus rounds are the source of truth, not a 1:1 agent->role mapping.
"""

from __future__ import annotations

from agent_lab.run.state import RunStateLike
from typing import Any


def normalize_consensus_signal(consensus: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize Room turn consensus meta for run-level pipeline gates."""
    if not consensus or not isinstance(consensus, dict):
        return None
    consented = consensus.get("agents_consented")
    try:
        endorse = int(consensus.get("endorse_count") or 0)
    except (TypeError, ValueError):
        endorse = 0
    if endorse == 0 and isinstance(consented, list):
        endorse = len(consented)
    snapshot = dict(consensus)
    snapshot["endorse_count"] = endorse
    status = snapshot.get("status") or snapshot.get("consensus_status")
    if status:
        snapshot.setdefault("status", status)
        snapshot.setdefault("consensus_status", status)
    return snapshot


def latest_turn_consensus(run: dict[str, Any]) -> dict[str, Any] | None:
    """Best-effort consensus from the most recent turn snapshot."""
    for turn in reversed(run.get("turns") or []):
        if not isinstance(turn, dict):
            continue
        raw = turn.get("consensus")
        if isinstance(raw, dict):
            return normalize_consensus_signal(raw)
    return None


def sync_consensus_snapshot(run_meta: RunStateLike, *, consensus: dict[str, Any] | None) -> None:
    """Mirror Room turn consensus onto run-level fields consumed by pipeline gates."""
    snapshot = normalize_consensus_signal(consensus)
    if not snapshot:
        return
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(run_meta, consensus=snapshot)
    ml = run_meta.get("mission_loop")
    if isinstance(ml, dict):
        ml["consensus"] = dict(snapshot)
        stamp_run_meta(run_meta, mission_loop=ml)


def best_consensus_for_persist(
    turns: list[dict[str, Any]] | None,
    prev_run: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Prefer the latest reached consensus turn; else latest turn signal; else prev run."""
    for turn in reversed(turns or []):
        if not isinstance(turn, dict):
            continue
        raw = turn.get("consensus")
        if isinstance(raw, dict) and raw.get("status") == "reached":
            return normalize_consensus_signal(raw)
    for turn in reversed(turns or []):
        if not isinstance(turn, dict):
            continue
        raw = turn.get("consensus")
        if isinstance(raw, dict):
            normalized = normalize_consensus_signal(raw)
            if normalized:
                return normalized
    prev = (prev_run or {}).get("consensus")
    if isinstance(prev, dict):
        return normalize_consensus_signal(prev)
    return None


def _consensus_signal(run: dict[str, Any]) -> dict[str, Any]:
    """Best-effort run-level consensus snapshot: {status|consensus_status, endorse_count}."""
    for key in ("consensus", "consensus_state"):
        candidate = run.get(key)
        if isinstance(candidate, dict):
            normalized = normalize_consensus_signal(candidate)
            return normalized if normalized is not None else candidate
    ml = run.get("mission_loop")
    if isinstance(ml, dict) and isinstance(ml.get("consensus"), dict):
        normalized = normalize_consensus_signal(ml["consensus"])
        return normalized if normalized is not None else ml["consensus"]
    fallback = latest_turn_consensus(run)
    return fallback or {}


def consensus_gate_met(run: dict[str, Any]) -> bool:
    """True when the Room reached consensus (status reached OR endorse >= policy threshold).

    Conservative: absent/ambiguous signal => not met, so plan.md stays gated until the Room's
    consensus rounds record agreement.
    """
    from agent_lab.consensus_policy import default_consensus_policy

    signal = _consensus_signal(run)
    status = signal.get("status") or signal.get("consensus_status")
    if status == "reached":
        return True
    policy = default_consensus_policy()
    try:
        endorse = int(signal.get("endorse_count") or 0)
    except (TypeError, ValueError):
        endorse = 0
    return endorse >= policy.min_endorse_agents


def consensus_action_block_reason(
    run: dict[str, Any],
    action_index: int,
    action_kind: Any = None,
) -> str | None:
    if not (run.get("_active_consensus") or run.get("consensus_mode")):
        return None
    signal = _consensus_signal(run)
    if (signal.get("status") or signal.get("consensus_status")) != "reached":
        return "consensus_not_reached"
    anchor = signal.get("anchor")
    if not isinstance(anchor, dict) or not all(str(anchor.get(key) or "").strip() for key in ("id", "agent", "excerpt")):
        return "consensus_anchor_incomplete"
    active = [str(agent).strip().lower() for agent in (run.get("agents") or []) if str(agent).strip()]
    required = int(effective_consensus(active).get("required_endorsements") or 0)
    consented = signal.get("agents_consented")
    if required and (not isinstance(consented, list) or len({str(agent).strip().lower() for agent in consented}) < required):
        return "consensus_endorsements_incomplete"
    from agent_lab.room.objections import execute_block_reason_for_action

    objection_reason = execute_block_reason_for_action(run, action_index, action_kind)
    if objection_reason:
        return objection_reason
    from agent_lab.room.tasks import consensus_tasks_ready

    tasks_ready, _blockers = consensus_tasks_ready(run, active)
    if not tasks_ready:
        return "consensus_tasks_incomplete"
    return None


# --- Dynamic resilient room: role allocation + degradation-aware consensus floor ---
# Pure additive helpers operating on the LIVE roster ids (never static default
# names). They build on default_consensus_policy (min_endorse_agents == floor 2).

ROLE_FILL_ORDER: tuple[str, ...] = ("propose", "endorse", "synthesize", "scribe")


def allocate_roles(agents: list[str]) -> dict[str, str]:
    """Assign roles to the live roster in fill order propose->endorse->synthesize->scribe.

    Operates on the actual agent ids passed in (post-substitution), not the static
    cursor/codex/claude defaults. Agents beyond the four named roles endorse.
    """
    roster = [a for a in agents]
    roles: dict[str, str] = {}
    for index, agent in enumerate(roster):
        if index < len(ROLE_FILL_ORDER):
            roles[agent] = ROLE_FILL_ORDER[index]
        else:
            roles[agent] = "endorse"
    return roles


def effective_consensus(agents: list[str]) -> dict[str, Any]:
    """Consensus mode for the current (possibly degraded) live roster.

    Mirrors the runtime model in room_consensus_rounds: the anchor author does
    not self-endorse, so reachable endorsements top out at ``size - 1``; a turn
    reaches consensus once all non-authors endorse OR the floor is met,
    whichever comes first. Required endorsements therefore are:

    size >= 2 -> ``min(size - 1, floor)`` (e.g. 2 agents -> 1, 3+ -> floor 2).
    size == 1 -> solo mode: consensus disabled, the single agent's output is accepted (0).
    size == 0 -> none (should not occur once the local fallback floor is wired, G006).
    """
    from agent_lab.consensus_policy import default_consensus_policy

    n = len([a for a in agents])
    floor = default_consensus_policy().min_endorse_agents
    if n <= 0:
        return {
            "roster_size": 0,
            "mode": "none",
            "consensus_enabled": False,
            "floor": floor,
            "required_endorsements": 0,
        }
    if n == 1:
        return {
            "roster_size": 1,
            "mode": "solo",
            "consensus_enabled": False,
            "floor": floor,
            "required_endorsements": 0,
        }
    return {
        "roster_size": n,
        "mode": "consensus",
        "consensus_enabled": True,
        "floor": floor,
        "required_endorsements": min(n - 1, floor),
    }
