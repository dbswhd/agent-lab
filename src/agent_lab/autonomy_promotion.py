"""N4 Layer 2 — autonomy promotion triggers (L0→L1 / L1→L2 / L2→L3).

Inputs are read from existing run.json fields (diff_risk, oracle verdict/confidence,
trust_budget, mission_loop, inbox). Promotion audit events append to autonomy.transitions.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from agent_lab.autonomy_ladder import infer_effective_autonomy_level, record_autonomy_transition, stored_autonomy_level
from agent_lab.diff_risk import assess_diff_risk
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.run.state import RunState, RunStateLike
from agent_lab.trust_budget import get_trust_budget

PromotionTransition = Literal["L0_to_L1", "L1_to_L2", "L2_to_L3"]

L0_TO_L1_STREAK = 5
L0_TO_L1_ORACLE_CONF = 0.85
L1_TO_L2_MISSIONS = 10
L2_TO_L3_MIN_MISSIONS = 10
L2_TO_L3_COMPLETION_RATE = 0.90
L2_TO_L3_ESCALATION_MAX = 0.05

_LEVEL_ORDER: dict[str, int] = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def oracle_confidence(oracle: Mapping[str, Any] | None) -> float:
    """Oracle confidence from run.json oracle blob (explicit or verdict-derived)."""
    if not oracle:
        return 0.0
    raw = oracle.get("confidence")
    if isinstance(raw, (int, float)):
        return max(0.0, min(1.0, float(raw)))
    verdict = str(oracle.get("verdict") or "").strip().lower()
    if verdict == "pass":
        return 1.0
    if verdict == "fail":
        return 0.0
    return 0.0


def execution_diff_risk_level(execution: Mapping[str, Any]) -> str:
    """diff_risk level for an execution row (stored or assessed)."""
    stored = execution.get("auto_approve_risk_level")
    if stored in ("low", "medium", "high"):
        return str(stored)
    level, _reasons = assess_diff_risk(dict(execution))
    return level


def _autonomy_block(run_meta: RunStateLike | None) -> dict[str, Any]:
    raw = (run_meta or {}).get("autonomy")
    return dict(raw) if isinstance(raw, dict) else {}


def _promotion_block(run_meta: RunStateLike | None) -> dict[str, Any]:
    raw = _autonomy_block(run_meta).get("promotion")
    return dict(raw) if isinstance(raw, dict) else {}


def _default_promotion_progress() -> dict[str, Any]:
    return {
        "l0_to_l1": {"streak": 0, "last_sample_at": None},
        "l1_to_l2": {"missions_completed": 0, "last_mission_at": None},
        "l2_to_l3": {
            "missions_total": 0,
            "missions_done": 0,
            "inbox_escalations": 0,
            "last_mission_at": None,
        },
    }


def promotion_progress(run_meta: RunStateLike | None) -> dict[str, Any]:
    base = _default_promotion_progress()
    block = _promotion_block(run_meta)
    for key in base:
        section = block.get(key)
        if isinstance(section, dict):
            base[key] = {**base[key], **section}
    return base


def evaluate_l0_to_l1(run_meta: RunStateLike | None) -> dict[str, Any]:
    progress = promotion_progress(run_meta)
    streak = int(progress["l0_to_l1"].get("streak") or 0)
    ceiling = stored_autonomy_level(run_meta)
    current = ceiling or infer_effective_autonomy_level(run_meta)
    eligible = streak >= L0_TO_L1_STREAK and _LEVEL_ORDER[current] < _LEVEL_ORDER["L1"]
    return {
        "transition": "L0_to_L1",
        "eligible": eligible,
        "streak": streak,
        "streak_required": L0_TO_L1_STREAK,
        "oracle_conf_required": L0_TO_L1_ORACLE_CONF,
        "auto_apply": eligible,
    }


def evaluate_l1_to_l2(run_meta: RunStateLike | None) -> dict[str, Any]:
    progress = promotion_progress(run_meta)
    missions = int(progress["l1_to_l2"].get("missions_completed") or 0)
    budget = get_trust_budget(run_meta)
    remaining = int(budget.get("auto_merge_remaining") or 0)
    total = int(budget.get("auto_merge_total") or 0)
    budget_ok = total > 0 and remaining > 0
    ceiling = stored_autonomy_level(run_meta)
    current = ceiling or infer_effective_autonomy_level(run_meta)
    eligible = missions >= L1_TO_L2_MISSIONS and budget_ok and _LEVEL_ORDER[current] < _LEVEL_ORDER["L2"]
    return {
        "transition": "L1_to_L2",
        "eligible": eligible,
        "missions_completed": missions,
        "missions_required": L1_TO_L2_MISSIONS,
        "trust_budget_remaining": remaining,
        "trust_budget_total": total,
        "requires_human": True,
    }


def evaluate_l2_to_l3(run_meta: RunStateLike | None) -> dict[str, Any]:
    progress = promotion_progress(run_meta)
    l23 = progress["l2_to_l3"]
    total = int(l23.get("missions_total") or 0)
    done = int(l23.get("missions_done") or 0)
    escalations = int(l23.get("inbox_escalations") or 0)
    completion_rate = (done / total) if total else 0.0
    escalation_rate = (escalations / total) if total else 0.0
    ceiling = stored_autonomy_level(run_meta)
    current = ceiling or infer_effective_autonomy_level(run_meta)
    eligible = (
        total >= L2_TO_L3_MIN_MISSIONS
        and completion_rate >= L2_TO_L3_COMPLETION_RATE
        and escalation_rate <= L2_TO_L3_ESCALATION_MAX
        and _LEVEL_ORDER[current] < _LEVEL_ORDER["L3"]
    )
    return {
        "transition": "L2_to_L3",
        "eligible": eligible,
        "missions_total": total,
        "missions_done": done,
        "completion_rate": round(completion_rate, 4),
        "escalation_rate": round(escalation_rate, 4),
        "completion_rate_required": L2_TO_L3_COMPLETION_RATE,
        "escalation_rate_max": L2_TO_L3_ESCALATION_MAX,
        "requires_human": True,
    }


def evaluate_promotions(run_meta: RunStateLike | None) -> dict[str, Any]:
    return {
        "l0_to_l1": evaluate_l0_to_l1(run_meta),
        "l1_to_l2": evaluate_l1_to_l2(run_meta),
        "l2_to_l3": evaluate_l2_to_l3(run_meta),
    }


def _patch_promotion(folder: Path, mutator: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    def _apply(run: RunState) -> RunState:
        block = dict(_autonomy_block(run))
        promo = promotion_progress(run)
        mutator(promo)
        block["promotion"] = promo
        block.setdefault("updated_at", _now_iso())
        run["autonomy"] = block
        return run

    patch_run_meta(folder, _apply)
    return promotion_progress(read_run_meta(folder))


def record_l0_to_l1_sample(folder: Path, execution: Mapping[str, Any]) -> dict[str, Any]:
    """Record one L0→L1 streak sample after execute verify (diff_risk + oracle)."""
    oracle = execution.get("oracle") if isinstance(execution.get("oracle"), dict) else {}
    risk = execution_diff_risk_level(execution)
    conf = oracle_confidence(oracle)
    verdict = str(oracle.get("verdict") or "").strip().lower()
    qualifies = risk == "low" and conf >= L0_TO_L1_ORACLE_CONF and verdict == "pass"

    def _mutate(promo: dict[str, Any]) -> None:
        row = dict(promo.get("l0_to_l1") or {})
        if qualifies:
            row["streak"] = int(row.get("streak") or 0) + 1
        else:
            row["streak"] = 0
        row["last_sample_at"] = _now_iso()
        row["last_risk"] = risk
        row["last_oracle_conf"] = round(conf, 3)
        promo["l0_to_l1"] = row

    progress = _patch_promotion(folder, _mutate)
    status = evaluate_l0_to_l1(read_run_meta(folder))
    if status.get("eligible"):
        record_autonomy_transition(
            folder,
            to_level="L1",
            reason="l0_to_l1:low_risk_oracle_streak",
            trigger="auto",
            from_level="L0",
        )

        def _reset_streak(promo: dict[str, Any]) -> None:
            row = dict(promo.get("l0_to_l1") or {})
            row["streak"] = 0
            row["applied_at"] = _now_iso()
            promo["l0_to_l1"] = row

        _patch_promotion(folder, _reset_streak)
    return progress


def record_mission_completion(
    folder: Path,
    *,
    completed: bool,
    inbox_escalated: bool = False,
) -> dict[str, Any]:
    """Bump L1→L2 / L2→L3 promotion counters when a mission loop cycle closes."""

    def _mutate(promo: dict[str, Any]) -> None:
        l12 = dict(promo.get("l1_to_l2") or {})
        l23 = dict(promo.get("l2_to_l3") or {})
        if completed:
            l12["missions_completed"] = int(l12.get("missions_completed") or 0) + 1
            l12["last_mission_at"] = _now_iso()
        l23["missions_total"] = int(l23.get("missions_total") or 0) + 1
        if completed:
            l23["missions_done"] = int(l23.get("missions_done") or 0) + 1
        if inbox_escalated:
            l23["inbox_escalations"] = int(l23.get("inbox_escalations") or 0) + 1
        l23["last_mission_at"] = _now_iso()
        promo["l1_to_l2"] = l12
        promo["l2_to_l3"] = l23

    progress = _patch_promotion(folder, _mutate)
    run = read_run_meta(folder)
    if evaluate_l1_to_l2(run).get("eligible"):
        maybe_create_promotion_inbox(folder, transition="L1_to_L2")
    if evaluate_l2_to_l3(run).get("eligible"):
        maybe_create_promotion_inbox(folder, transition="L2_to_L3")
    return progress


def _promotion_harvest_key(transition: PromotionTransition) -> str:
    return f"autonomy:promotion:{transition}"


def maybe_create_promotion_inbox(folder: Path, *, transition: PromotionTransition) -> dict[str, Any] | None:
    """Human gate for L1→L2 and L2→L3 promotions."""
    from agent_lab.autonomy_promotion_inbox import maybe_create_promotion_inbox as _create

    return _create(folder, transition=transition)


def handle_autonomy_promotion_resolve(
    folder: Path,
    item: dict[str, Any],
    *,
    selected: list[str] | None = None,
) -> None:
    """Apply Human approval for a promotion inbox item."""
    from agent_lab.autonomy_promotion_inbox import handle_autonomy_promotion_resolve as _resolve

    _resolve(folder, item, selected=selected)
