from __future__ import annotations

"""Arm-time topology decision wiring (AGENT_LAB_MISSION_TOPOLOGY, default off).

Derives a CoordinationNeed deterministically from already-computed signals (topic
router category, persisted clarity panel, active roster, budget env) — no LLM
calls — then records choose_topology()'s decision to run.json ``mission_topology``
plus a goal_ledger breadcrumb. Consumers read the decision via the helpers here:
SINGLE skips plan PEER_REVIEW (human gate preserved) and ``max_agents`` can only
*lower* the dispatch fan-out cap.

The arm-time decision is not static:

- ``reroute_mission_topology_after_verify`` re-derives the need with a risk
  floor after each non-structural verify failure and applies an
  escalation-only swap (never a mid-mission downgrade), so a failing SINGLE
  mission regains peer review. When a recompute finds no room left to
  escalate (coordination has already been maxed out for this action), it
  either nudges the repair cap down by one — via
  ``mission_loop.action_repair_cap_override`` consumed by
  ``mission/advance.py::_on_verify_fail`` — so the *existing* DISCUSS
  recovery/replan path engages a repair sooner instead of burning another
  wasted attempt, or (when this failure already exhausts the cap) flags a
  non-blocking Human inbox item without touching phase/circuit_breaker.
- ``deescalate_mission_topology_after_pass`` is the mirror: after a sustained
  clean streak of verify passes (``mission_loop.consecutive_verify_passes``),
  it downgrades one step toward a freshly-recomputed *baseline* need (no risk
  floor) — but only when that baseline is genuinely smaller, so a mission
  that's still objectively complex/risky stays escalated.

``manager_bottleneck`` / ``exploration`` have no signal source yet so they are
always False (recorded in the ``signals`` provenance).

M6 scope note: this module's state (``run.json["mission_topology"]``,
``mission_loop.action_repair_cap_override``, ``mission_loop.consecutive_verify_passes``)
is intentionally legacy-only with no ``mission/kernel.py`` command/event
equivalent. Building one now would only matter once the
``AGENT_LAB_MISSION_DUAL_WRITE`` bounded cohort extends authority to plan/topology
decisions, which is deliberately not in progress (Wave B/inbox authority was
chosen over that track — see
docs/redesign-2026-07/evidence/m6-final-retire-2026-07-14/deletion-manifest.json
``m6_scope_exclusions``). Revisit only alongside that larger authority
expansion, not in isolation.
"""

from pathlib import Path
from typing import Any, cast

from agent_lab.env_flags import env_bool
from agent_lab.mission.topology import (
    CoordinationNeed,
    RiskLevel,
    TopologyDecision,
    TopologyKind,
    choose_topology,
)
from agent_lab.run.state import RunState, RunStateLike
from agent_lab.time_utils import utc_now_iso

MISSION_TOPOLOGY_VERSION = 1

_CATEGORY_COMPLEXITY: dict[str, int] = {
    "quick": 1,
    "standard": 3,
    "trading": 4,
    "deep": 5,
    "critical": 7,
}

_RISK_RANK: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
}

_CATEGORY_TIME_BUDGET_S: dict[str, int] = {
    "quick": 120,
    "standard": 300,
    "trading": 300,
    "deep": 600,
    "critical": 600,
}


def mission_topology_enabled() -> bool:
    return env_bool("AGENT_LAB_MISSION_TOPOLOGY")


def _category_risk(category: str) -> RiskLevel:
    if category == "critical":
        return RiskLevel.HIGH
    if category in {"deep", "trading"}:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _persisted_clarity(run: RunStateLike) -> dict[str, Any]:
    ml = run.get("mission_loop")
    ml = ml if isinstance(ml, dict) else {}
    clarity = ml.get("clarity")
    return clarity if isinstance(clarity, dict) else {}


def build_coordination_need(
    run: RunStateLike, *, risk_floor: RiskLevel | None = None
) -> tuple[CoordinationNeed, dict[str, Any]]:
    """Deterministic, read-only need derivation. Never calls agents/LLMs.

    ``risk_floor`` can only raise the category-derived risk, never lower it.
    """
    from agent_lab.clarity import _mission_clarity_text, _threshold
    from agent_lab.cost_ledger import _budget_limit_usd
    from agent_lab.room.roster_context import active_agents_from_run_meta
    from agent_lab.topic_router import classify_topic

    text = _mission_clarity_text(run)
    category, category_signals = classify_topic(text)

    clarity = _persisted_clarity(run)
    components = clarity.get("components")
    component_count = len(components) if isinstance(components, list) else 0
    dimensions = clarity.get("dimensions")
    dimensions = dimensions if isinstance(dimensions, dict) else {}
    criteria_raw = dimensions.get("criteria")
    criteria_ambiguity = float(criteria_raw) if isinstance(criteria_raw, (int, float)) else None
    evaluation_clear = criteria_ambiguity is not None and criteria_ambiguity <= _threshold()

    roster = active_agents_from_run_meta(run)
    budget = _budget_limit_usd()

    risk = _category_risk(category)
    if risk_floor is not None and _RISK_RANK[risk_floor] > _RISK_RANK[risk]:
        risk = risk_floor

    need = CoordinationNeed(
        complexity=_CATEGORY_COMPLEXITY.get(category, 3),
        domain_count=max(1, component_count),
        decomposable=component_count >= 2,
        risk=risk,
        evaluation_clear=evaluation_clear,
        time_budget_seconds=_CATEGORY_TIME_BUDGET_S.get(category, 300),
        cost_budget_usd=budget if budget is not None else 0.0,
        available_specialists=max(0, len(roster) - 1),
        manager_bottleneck=False,
        exploration=False,
    )
    signals: dict[str, Any] = {
        "category": category,
        "category_signals": list(category_signals),
        "clarity_available": bool(clarity),
        "clarity_overall": clarity.get("overall"),
        "criteria_ambiguity": criteria_ambiguity,
        "component_count": component_count,
        "roster": list(roster),
        "budget_env_set": budget is not None,
        "time_budget_rule": "category_default_v1",
        "v1_constants": ["manager_bottleneck=false", "exploration=false"],
        "risk_floor": str(risk_floor) if risk_floor is not None else None,
    }
    return need, signals


def _decision_dict(decision: TopologyDecision) -> dict[str, Any]:
    return {
        "kind": str(decision.kind),
        "reason": decision.reason,
        "max_agents": decision.max_agents,
        "fallback": str(decision.fallback),
    }


def _need_dict(need: CoordinationNeed) -> dict[str, Any]:
    return {
        "complexity": need.complexity,
        "domain_count": need.domain_count,
        "decomposable": need.decomposable,
        "risk": str(need.risk),
        "evaluation_clear": need.evaluation_clear,
        "time_budget_seconds": need.time_budget_seconds,
        "cost_budget_usd": need.cost_budget_usd,
        "available_specialists": need.available_specialists,
        "manager_bottleneck": need.manager_bottleneck,
        "exploration": need.exploration,
    }


def apply_mission_topology(run: RunState) -> dict[str, Any] | None:
    """Stamp the topology record into an in-flight run dict; None when already present.

    Only call inside a patch_run_meta updater (or on an in-memory run dict).
    """
    if run.get("mission_topology"):
        return None
    need, signals = build_coordination_need(run)
    decision = choose_topology(need)
    record: dict[str, Any] = {
        "version": MISSION_TOPOLOGY_VERSION,
        "at": utc_now_iso(),
        "revision": 1,
        "decision": _decision_dict(decision),
        "need": _need_dict(need),
        "signals": signals,
    }
    run["mission_topology"] = record
    return record


def ensure_mission_topology(folder: Path) -> dict[str, Any] | None:
    """Compute+persist the arm-time decision once; idempotent across re-arms."""
    if not mission_topology_enabled():
        return None
    from agent_lab.goal_ledger import append_goal_event
    from agent_lab.run.meta import patch_run_meta

    record_out: dict[str, Any] | None = None
    phase_out: str | None = None

    def _stamp(run: RunState) -> RunState:
        nonlocal record_out, phase_out
        record = apply_mission_topology(run)
        if record is not None:
            record_out = record
            ml = run.get("mission_loop")
            phase_out = str(ml.get("phase")) if isinstance(ml, dict) and ml.get("phase") else None
        return run

    patch_run_meta(folder, _stamp)
    record = record_out
    if record is None:
        return None
    decision = record["decision"]
    append_goal_event(
        folder,
        "mission_topology",
        phase=phase_out,
        note=(
            f"kind={decision['kind']} max_agents={decision['max_agents']} "
            f"fallback={decision['fallback']} — {decision['reason']}"
        ),
        payload={"decision": decision, "revision": record.get("revision", 1), "trigger": None},
    )
    return record


_HISTORY_CAP = 10
_DEESCALATE_STREAK = 3


def _flag_human_attention(run_in: RunState, *, action_index: int, current: dict[str, Any]) -> None:
    """Non-blocking Human inbox note — never touches phase/circuit_breaker.

    Mirrors mission/board.py's ``_apply_overflow`` pattern: dedup by
    (source, action_ref), append via the pure ``append_inbox_item`` (safe to
    call inside a patch_run_meta closure), then resync ``inbox_pending``.
    """
    from agent_lab.human_inbox import append_inbox_item, compute_inbox_pending, inbox_items, new_inbox_item

    source = "topology_router_plateau"
    ref = str(action_index)
    for item in inbox_items(run_in):
        if item.get("status") == "pending" and str(item.get("source") or "") == source and item.get(
            "action_ref"
        ) == ref:
            return
    item = new_inbox_item(
        kind="question",
        source=source,
        prompt=(
            f"Action #{action_index} is still failing after coordination escalated to "
            f"{current.get('kind') or 'single'} (max_agents={current.get('max_agents') or 1}) — "
            "repair cap reached. DISCUSS recovery engages automatically; flagging for visibility."
        ),
        summary=f"topology_router_plateau: action {action_index}",
        action_ref=ref,
        options=[{"id": "ack", "label": "Acknowledge"}],
    )
    append_inbox_item(run_in, item)
    run_in["inbox_pending"] = compute_inbox_pending(run_in)


def _handle_plateau(
    run_in: RunState,
    ml: dict[str, Any],
    *,
    action_index: int,
    count: int,
    max_rep: int,
    current: dict[str, Any],
) -> None:
    """No topology escalation happened for this failure.

    Coordination is already maxed out for this action. If this failure
    already exhausts the repair cap, flag a Human (the existing DISCUSS
    recovery path is about to engage). Otherwise nudge the cap down by one so
    that path engages *next* fail instead of burning another repair attempt
    coordination alone won't fix — but only from the 2nd fail on, so a
    naturally single-agent task's first failure never early-triggers this.
    """
    if count + 1 >= max_rep:
        _flag_human_attention(run_in, action_index=action_index, current=current)
        return
    if count >= 1:
        overrides = dict(ml.get("action_repair_cap_override") or {})
        overrides[str(action_index)] = count + 1
        ml2 = dict(ml)
        ml2["action_repair_cap_override"] = overrides
        run_in["mission_loop"] = ml2


def reroute_mission_topology_after_verify(
    folder: Path, *, verdict: str, reason: str = "", action_index: int
) -> dict[str, Any] | None:
    """Escalation-only re-decision after a non-structural verify failure.

    Only ever raises the topology (never downgrades mid-mission): a failing
    SINGLE mission regains peer review / more seats when a recompute with a
    risk floor (MEDIUM on first fail, HIGH once the failure would land in
    DISCUSS recovery per the repair cap) produces a strictly bigger decision.
    No-op when the flag is off, the verdict isn't a failure, the failure is
    structural (infra, not a coordination problem), or no arm-time record
    exists yet.
    """
    if not mission_topology_enabled():
        return None
    if str(verdict or "").strip().lower() != "fail":
        return None
    from agent_lab.mission.loop import DEFAULT_MAX_REPAIR_PER_ACTION, is_structural_verify_fail

    if is_structural_verify_fail(reason):
        return None

    from agent_lab.goal_ledger import append_goal_event
    from agent_lab.run.meta import patch_run_meta

    replaced_out: dict[str, Any] | None = None
    prev_out: dict[str, Any] | None = None
    phase_out: str | None = None
    revision_out: int = 0

    def _swap(run_in: RunState) -> RunState:
        nonlocal replaced_out, prev_out, phase_out, revision_out
        record = run_in.get("mission_topology")
        if not isinstance(record, dict):
            return run_in
        current = record.get("decision")
        current = current if isinstance(current, dict) else {}
        ml = run_in.get("mission_loop")
        ml = ml if isinstance(ml, dict) else {}
        counts = ml.get("action_repair_counts")
        counts = counts if isinstance(counts, dict) else {}
        count = int(counts.get(str(action_index)) or 0)
        max_rep = int(ml.get("max_repair_per_action") or DEFAULT_MAX_REPAIR_PER_ACTION)
        floor = RiskLevel.HIGH if count + 1 >= max_rep else RiskLevel.MEDIUM

        need, signals = build_coordination_need(run_in, risk_floor=floor)
        candidate = choose_topology(need)
        candidate_dict = _decision_dict(candidate)
        cur_kind = str(current.get("kind") or "")
        cur_max_raw = current.get("max_agents")
        cur_max = cur_max_raw if isinstance(cur_max_raw, int) else 1
        escalated = candidate_dict != current and (cur_kind == str(TopologyKind.SINGLE) or candidate.max_agents > cur_max)
        if not escalated:
            _handle_plateau(run_in, ml, action_index=action_index, count=count, max_rep=max_rep, current=current)
            return run_in

        revision_raw = record.get("revision")
        revision = revision_raw if isinstance(revision_raw, int) else 1
        history = [h for h in (record.get("history") or []) if isinstance(h, dict)]
        history.append(
            {
                "decision": current,
                "at": record.get("at"),
                "revision": revision,
                "trigger": record.get("trigger"),
            }
        )
        trigger = f"verify_fail_action_{action_index}"
        record["decision"] = candidate_dict
        record["need"] = _need_dict(need)
        record["signals"] = signals
        record["at"] = utc_now_iso()
        record["revision"] = revision + 1
        record["trigger"] = trigger
        record["history"] = history[-_HISTORY_CAP:]
        run_in["mission_topology"] = record

        replaced_out = candidate_dict
        prev_out = current
        phase_out = str(ml.get("phase")) if ml.get("phase") else None
        revision_out = revision + 1
        return run_in

    patch_run_meta(folder, _swap)
    if replaced_out is None:
        return None
    trigger = f"verify_fail_action_{action_index}"
    append_goal_event(
        folder,
        "mission_topology_reroute",
        phase=phase_out,
        note=(
            f"{(prev_out or {}).get('kind')}→{replaced_out['kind']} "
            f"max_agents {(prev_out or {}).get('max_agents')}→{replaced_out['max_agents']} "
            f"trigger={trigger} — {replaced_out['reason']}"
        ),
        payload={
            "from": prev_out,
            "to": replaced_out,
            "revision": revision_out,
            "trigger": trigger,
        },
    )
    return replaced_out


def deescalate_mission_topology_after_pass(folder: Path, *, action_index: int) -> dict[str, Any] | None:
    """One-shot topology de-escalation after a sustained clean streak.

    Mirror of ``reroute_mission_topology_after_verify`` on the pass side —
    deliberately a *separate* function so escalation's never-downgrade
    contract (see its docstring) is never touched by this code path. Only
    fires when the topology is escalated beyond SINGLE and the mission has
    gone ``_DEESCALATE_STREAK`` consecutive verify passes with no intervening
    failure. Downgrades to a freshly-recomputed baseline need (no risk floor)
    only when that baseline is genuinely smaller than the current decision —
    a mission that's still objectively complex/risky stays escalated even
    after a clean streak. Resets the streak on de-escalation so the next one
    needs its own full streak (self-limiting; no explicit one-step-at-a-time
    cap is needed).
    """
    if not mission_topology_enabled():
        return None
    from agent_lab.goal_ledger import append_goal_event
    from agent_lab.run.meta import patch_run_meta

    replaced_out: dict[str, Any] | None = None
    prev_out: dict[str, Any] | None = None
    phase_out: str | None = None
    revision_out: int = 0
    trigger_out: str = ""

    def _swap(run_in: RunState) -> RunState:
        nonlocal replaced_out, prev_out, phase_out, revision_out, trigger_out
        record = run_in.get("mission_topology")
        if not isinstance(record, dict):
            return run_in
        current = record.get("decision")
        current = current if isinstance(current, dict) else {}
        if str(current.get("kind") or "") == str(TopologyKind.SINGLE):
            return run_in

        ml = run_in.get("mission_loop")
        ml = ml if isinstance(ml, dict) else {}
        streak = int(ml.get("consecutive_verify_passes") or 0)
        if streak < _DEESCALATE_STREAK:
            return run_in

        need, signals = build_coordination_need(run_in)
        candidate = choose_topology(need)
        candidate_dict = _decision_dict(candidate)
        cur_max_raw = current.get("max_agents")
        cur_max = cur_max_raw if isinstance(cur_max_raw, int) else 1
        smaller = candidate.max_agents < cur_max or (
            candidate_dict.get("kind") == str(TopologyKind.SINGLE)
            and current.get("kind") != str(TopologyKind.SINGLE)
        )
        if not smaller:
            return run_in

        revision_raw = record.get("revision")
        revision = revision_raw if isinstance(revision_raw, int) else 1
        history = [h for h in (record.get("history") or []) if isinstance(h, dict)]
        history.append(
            {
                "decision": current,
                "at": record.get("at"),
                "revision": revision,
                "trigger": record.get("trigger"),
            }
        )
        trigger = f"verify_pass_streak_{streak}"
        record["decision"] = candidate_dict
        record["need"] = _need_dict(need)
        record["signals"] = signals
        record["at"] = utc_now_iso()
        record["revision"] = revision + 1
        record["trigger"] = trigger
        record["history"] = history[-_HISTORY_CAP:]
        run_in["mission_topology"] = record

        ml2 = dict(ml)
        ml2["consecutive_verify_passes"] = 0
        run_in["mission_loop"] = ml2

        replaced_out = candidate_dict
        prev_out = current
        phase_out = str(ml.get("phase")) if ml.get("phase") else None
        revision_out = revision + 1
        trigger_out = trigger
        return run_in

    patch_run_meta(folder, _swap)
    if replaced_out is None:
        return None
    append_goal_event(
        folder,
        "mission_topology_deescalate",
        phase=phase_out,
        note=(
            f"{(prev_out or {}).get('kind')}→{replaced_out['kind']} "
            f"max_agents {(prev_out or {}).get('max_agents')}→{replaced_out['max_agents']} "
            f"trigger={trigger_out}"
        ),
        payload={
            "from": prev_out,
            "to": replaced_out,
            "revision": revision_out,
            "trigger": trigger_out,
        },
    )
    return replaced_out


def mission_topology_decision(run: RunStateLike | None) -> dict[str, Any] | None:
    """Consumer-side reader: decision dict when the flag is on and a record exists."""
    if run is None or not mission_topology_enabled():
        return None
    record = run.get("mission_topology")
    if not isinstance(record, dict):
        return None
    decision = record.get("decision")
    if not isinstance(decision, dict):
        return None
    return cast(dict[str, Any], decision)


def topology_max_agents(run: RunStateLike | None) -> int | None:
    decision = mission_topology_decision(run)
    if not decision:
        return None
    raw = decision.get("max_agents")
    return raw if isinstance(raw, int) and raw >= 1 else None


def topology_skips_peer_review(run: RunStateLike | None) -> bool:
    decision = mission_topology_decision(run)
    if not decision:
        return False
    return decision.get("kind") == str(TopologyKind.SINGLE)
