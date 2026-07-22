"""Debate convergence scoring — clarity/interview-style gate for Room debate pacing.

Heuristic (0 LLM calls): envelope acts + open objections → multi-dim divergence,
coverage-weighted weakest dimension, advance when convergence >= threshold.

Kill switch: ``AGENT_LAB_DEBATE_CONVERGENCE_GATE=0`` (default off, OFF-parity).
"""

from __future__ import annotations

from agent_lab.run.state import RunStateLike
import os
from typing import Any

from agent_lab.agent.envelope import envelope_act

DEBATE_CONVERGENCE_THRESHOLD = 0.75
CONVERGENCE_DIMENSIONS: tuple[str, ...] = (
    "endorse_gap",
    "objection_residue",
    "conflict_trend",
    "amend_churn",
)

_CONFLICT_ACTS = frozenset({"CHALLENGE", "BLOCK", "AMEND"})
_SUPPORT_ACTS = frozenset({"ENDORSE", "PASS", "NOTE"})


def debate_convergence_gate_enabled() -> bool:
    raw = (os.getenv("AGENT_LAB_DEBATE_CONVERGENCE_GATE") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _threshold() -> float:
    raw = (os.getenv("AGENT_LAB_DEBATE_CONVERGENCE_THRESHOLD") or "").strip()
    if raw:
        try:
            return max(0.0, min(1.0, float(raw)))
        except ValueError:
            pass
    return DEBATE_CONVERGENCE_THRESHOLD


def _coverage_weighted_divergence(dimensions: dict[str, float]) -> float:
    vals = [float(v) for v in dimensions.values()]
    if not vals:
        return 0.8
    return round(0.6 * max(vals) + 0.4 * (sum(vals) / len(vals)), 4)


def _acts_by_round(messages: list[Any]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for msg in messages:
        if getattr(msg, "role", None) != "agent":
            continue
        act = envelope_act(getattr(msg, "envelope", None) if isinstance(getattr(msg, "envelope", None), dict) else None)
        if not act:
            continue
        round_key = str(getattr(msg, "parallel_round", None) or 1)
        bucket = out.setdefault(round_key, {})
        bucket[act] = bucket.get(act, 0) + 1
    return out


def _conflict_rate(acts: dict[str, int]) -> float:
    if not acts:
        return 0.0
    conflicts = sum(acts.get(a, 0) for a in _CONFLICT_ACTS)
    total = sum(acts.values())
    return conflicts / total if total else 0.0


def _endorse_gap_divergence(
    active_agents: list[str],
    acts_by_round: dict[str, dict[str, int]],
    *,
    consented: list[str] | None = None,
    pending: set[str] | None = None,
) -> float:
    pool = {str(a).strip().lower() for a in active_agents if str(a).strip()}
    if not pool:
        return 0.8
    if consented is not None or pending is not None:
        need = max(1, len(pool) - 1)
        have = len({str(a).strip().lower() for a in (consented or []) if str(a).strip()})
        return round(max(0.0, 1.0 - (have / need)), 4)
    if not acts_by_round:
        return 0.8
    last_key = max(acts_by_round.keys(), key=lambda k: int(k))
    last = acts_by_round[last_key]
    support = sum(last.get(a, 0) for a in _SUPPORT_ACTS)
    agents_in_round = max(1, sum(last.values()))
    coverage = min(1.0, support / min(len(pool), agents_in_round))
    return round(max(0.0, 1.0 - coverage), 4)


def _objection_residue_divergence(run_meta: RunStateLike | None, *, human_turn: int) -> float:
    if not run_meta:
        return 0.0
    from agent_lab.room.objections import open_objections

    open_rows = [
        o
        for o in open_objections(run_meta)
        if str(o.get("status") or "open") == "open" and int(o.get("turn") or 0) == human_turn
    ]
    if not open_rows:
        return 0.0
    return min(1.0, round(len(open_rows) * 0.5, 4))


def _conflict_trend_divergence(acts_by_round: dict[str, dict[str, int]]) -> float:
    if not acts_by_round:
        return 0.8
    rounds = sorted(acts_by_round.keys(), key=lambda k: int(k))
    rates = [_conflict_rate(acts_by_round[r]) for r in rounds]
    last = rates[-1]
    if len(rates) == 1:
        return round(min(1.0, last * 1.25), 4)
    prev_mean = sum(rates[:-1]) / len(rates[:-1])
    if last <= prev_mean * 0.5:
        return round(min(1.0, last * 0.5), 4)
    return round(min(1.0, max(last, prev_mean)), 4)


def _amend_churn_divergence(acts_by_round: dict[str, dict[str, int]]) -> float:
    if not acts_by_round:
        return 0.0
    rounds = sorted(acts_by_round.keys(), key=lambda k: int(k))[-2:]
    amends = sum(acts_by_round.get(r, {}).get("AMEND", 0) for r in rounds)
    return min(1.0, round(amends / 2.0, 4))


def score_debate_convergence(
    messages: list[Any],
    *,
    active_agents: list[str],
    run_meta: RunStateLike | None = None,
    human_turn: int = 0,
    phase: str = "debate",
    consented: list[str] | None = None,
    pending: set[str] | None = None,
) -> dict[str, Any]:
    """Return divergence/convergence snapshot for the current human turn thread."""
    acts_by_round = _acts_by_round(messages)
    dimensions = {
        "endorse_gap": _endorse_gap_divergence(
            active_agents,
            acts_by_round,
            consented=consented if phase == "endorse" else None,
            pending=pending if phase == "endorse" else None,
        ),
        "objection_residue": _objection_residue_divergence(run_meta, human_turn=human_turn),
        "conflict_trend": _conflict_trend_divergence(acts_by_round),
        "amend_churn": _amend_churn_divergence(acts_by_round),
    }
    divergence = _coverage_weighted_divergence(dimensions)
    convergence = round(max(0.0, 1.0 - divergence), 4)
    threshold = _threshold()
    weakest = max(dimensions, key=lambda d: dimensions[d]) if dimensions else None
    return {
        "phase": phase,
        "dimensions": dimensions,
        "divergence": divergence,
        "convergence": convergence,
        "weakest": weakest,
        "threshold": threshold,
        "met": convergence >= threshold and dimensions.get("objection_residue", 1.0) <= threshold,
        "acts_by_round": acts_by_round,
    }


def _open_objections_block(run_meta: RunStateLike | None, *, human_turn: int) -> bool:
    if not run_meta:
        return False
    from agent_lab.room.objections import open_objections

    return any(
        str(o.get("status") or "open") == "open" and int(o.get("turn") or 0) == human_turn
        for o in open_objections(run_meta)
    )


def should_advance_debate(
    result: dict[str, Any],
    run_meta: RunStateLike | None,
    *,
    human_turn: int,
    debate_round: int,
    min_debate_round: int = 2,
) -> tuple[bool, str | None]:
    """Early-exit debate phase (R2+) when converged and no open objections."""
    if not debate_convergence_gate_enabled():
        return False, None
    if debate_round < min_debate_round:
        return False, None
    if _open_objections_block(run_meta, human_turn=human_turn):
        return False, "open_objections"
    if not result.get("met"):
        return False, None
    return True, "convergence_threshold"


def should_advance_endorse(
    result: dict[str, Any],
    run_meta: RunStateLike | None,
    *,
    human_turn: int,
    endorse_count: int,
    active_agents: list[str],
    min_endorse_agents: int,
) -> tuple[bool, str | None]:
    if not debate_convergence_gate_enabled():
        return False, None
    if _open_objections_block(run_meta, human_turn=human_turn):
        return False, "open_objections"
    if endorse_count < min(min_endorse_agents, max(1, len(active_agents) - 1)):
        return False, None
    if not result.get("met"):
        return False, None
    return True, "convergence_threshold"


def public_convergence_snapshot(result: dict[str, Any]) -> dict[str, Any]:
    """Persist-safe subset for communicate_meta / SSE."""
    return {
        "phase": result.get("phase"),
        "convergence": result.get("convergence"),
        "divergence": result.get("divergence"),
        "threshold": result.get("threshold"),
        "met": result.get("met"),
        "weakest": result.get("weakest"),
        "dimensions": dict(result.get("dimensions") or {}),
    }


def record_debate_convergence(run_meta: RunStateLike | None, result: dict[str, Any]) -> None:
    if run_meta is None:
        return
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(run_meta, _debate_convergence=public_convergence_snapshot(result))
