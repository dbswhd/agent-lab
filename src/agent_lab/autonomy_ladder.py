"""Autonomy Ladder (N4) — L0~L3 session trust level SSOT."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from agent_lab.auto_approve_gate import auto_approve_threshold
from agent_lab.diff_risk import RiskLevel
from agent_lab.run.meta import patch_run_meta
from agent_lab.run.state import RunStateLike
from agent_lab.trust_budget import get_trust_budget

AutonomyLevel = Literal["L0", "L1", "L2", "L3"]

_LEVEL_ORDER: dict[str, int] = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}

# L1->L2 is "Budgeted" (NORTH-STAR N4): the ceiling alone is a label — the ladder
# only reports L2 *effective* once trust_budget is non-zero. Neither the dial nor
# the promotion inbox previously provisioned a budget, so a Human promoting to L2
# never actually reached it (infer_effective_autonomy_level stayed L0/L1).
_L2_DEFAULT_TRUST_BUDGET: dict[str, Any] = {
    "auto_merge_total": 10,
    "auto_merge_remaining": 10,
    "classifier_allow": ["docs_only", "test_only", "single_file"],
}

_LEVEL_NAMES: dict[str, str] = {
    "L0": "Manual",
    "L1": "Assisted",
    "L2": "Budgeted",
    "L3": "Autonomous",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _autonomy_block(run_meta: RunStateLike | None) -> dict[str, Any]:
    meta = run_meta or {}
    raw = meta.get("autonomy")
    return raw if isinstance(raw, dict) else {}


def effective_auto_approve_threshold(run_meta: RunStateLike | None) -> RiskLevel | None:
    """Max risk for auto-approve: env override, else L1+ Human ceiling defaults to low."""
    explicit = auto_approve_threshold()
    if explicit is not None:
        return explicit
    ceiling = stored_autonomy_level(run_meta)
    if ceiling and _LEVEL_ORDER[ceiling] >= _LEVEL_ORDER["L1"]:
        return "low"
    return None


def stored_autonomy_level(run_meta: RunStateLike | None) -> AutonomyLevel | None:
    """Human-set ceiling, or None when no explicit ceiling is stored."""
    level = _autonomy_block(run_meta).get("level")
    if level in _LEVEL_ORDER:
        return level  # type: ignore[return-value]
    return None


def infer_effective_autonomy_level(run_meta: RunStateLike | None) -> AutonomyLevel:
    """Derive active ladder level from mission loop, trust budget, auto-approve."""
    meta = run_meta or {}
    ml = meta.get("mission_loop")
    if isinstance(ml, dict) and ml.get("enabled"):
        seg = ml.get("autonomous_segment")
        if isinstance(seg, dict) and seg.get("active"):
            return "L3"

    budget = get_trust_budget(meta)
    remaining = int(budget.get("auto_merge_remaining") or 0)
    total = int(budget.get("auto_merge_total") or 0)
    if total > 0 and remaining > 0:
        return "L2"

    if effective_auto_approve_threshold(meta) is not None:
        return "L1"

    return "L0"


def resolve_display_autonomy_level(run_meta: RunStateLike | None) -> AutonomyLevel:
    """UI level: effective signals, capped by Human ceiling when explicitly set."""
    effective = infer_effective_autonomy_level(run_meta)
    stored = stored_autonomy_level(run_meta)
    if stored is None:
        return effective
    if _LEVEL_ORDER[effective] <= _LEVEL_ORDER[stored]:
        return effective
    return stored


def public_autonomy_payload(run_meta: RunStateLike | None) -> dict[str, Any]:
    meta = run_meta or {}
    block = _autonomy_block(meta)
    budget = get_trust_budget(meta)
    effective = infer_effective_autonomy_level(meta)
    display = resolve_display_autonomy_level(meta)
    ceiling = stored_autonomy_level(meta)
    ml = meta.get("mission_loop") if isinstance(meta.get("mission_loop"), dict) else {}
    seg = ml.get("autonomous_segment") if isinstance(ml.get("autonomous_segment"), dict) else {}
    transitions_raw = block.get("transitions")
    transitions: list[dict[str, Any]] = []
    if isinstance(transitions_raw, list):
        transitions = [row for row in transitions_raw if isinstance(row, dict)][-5:]
    from agent_lab.autonomy_promotion import evaluate_promotions, promotion_progress

    return {
        # Ceiling when Human-set; otherwise operating (effective) level.
        "level": ceiling if ceiling is not None else effective,
        "effective_level": effective,
        "display_level": display,
        "level_name": _LEVEL_NAMES.get(display, display),
        "ceiling_set": ceiling is not None,
        "trust_budget": {
            "auto_merge_remaining": int(budget.get("auto_merge_remaining") or 0),
            "auto_merge_total": int(budget.get("auto_merge_total") or 0),
        },
        "signals": {
            "auto_approve_enabled": effective_auto_approve_threshold(meta) is not None,
            "mission_loop_enabled": bool(ml.get("enabled")),
            "autonomous_segment_active": bool(seg.get("active")),
        },
        "transitions": transitions,
        "promotion": evaluate_promotions(meta),
        "promotion_progress": promotion_progress(meta),
    }


def record_autonomy_transition(
    folder,
    *,
    to_level: AutonomyLevel,
    reason: str,
    trigger: Literal["auto", "human", "demotion"] = "auto",
    from_level: AutonomyLevel | None = None,
) -> dict[str, Any]:
    """Append a ladder transition event to run.json (N4 audit trail)."""

    def _apply(run: dict[str, Any]) -> dict[str, Any]:
        block = dict(_autonomy_block(run))
        ceiling = stored_autonomy_level(run)
        prev = from_level or ceiling or infer_effective_autonomy_level(run)
        block["level"] = to_level
        effective = infer_effective_autonomy_level(run)
        block["last_effective"] = effective
        transitions = list(block.get("transitions") or [])
        transitions.append(
            {
                "from": prev,
                "to": to_level,
                "reason": reason[:500],
                "trigger": trigger,
                "at": _now_iso(),
            }
        )
        block["transitions"] = transitions[-20:]
        block["updated_at"] = _now_iso()
        run["autonomy"] = block
        return run

    updated = patch_run_meta(folder, _apply)
    if to_level == "L2":
        updated = _maybe_provision_l2_trust_budget(folder, updated)
    if to_level == "L3":
        apply_autonomy_level_capabilities(folder, "L3")
    return public_autonomy_payload(updated)


def _maybe_provision_l2_trust_budget(folder, run_meta: RunStateLike) -> dict[str, Any]:
    """Give a promotion to L2 a real trust_budget so the level is effective, not just labeled.

    Only fires when no budget is set yet (total<=0) — never overwrites a Human's
    or a prior session's custom allotment.
    """
    from agent_lab.trust_budget import set_trust_budget

    budget = get_trust_budget(run_meta)
    if int(budget.get("auto_merge_total") or 0) > 0:
        return dict(run_meta)
    set_trust_budget(folder, dict(_L2_DEFAULT_TRUST_BUDGET))
    from agent_lab.run.meta import read_run_meta

    return read_run_meta(folder)


def apply_autonomy_level_capabilities(folder, level: AutonomyLevel) -> None:
    """Wire L3 ceiling to mission loop autonomous segment (N4 runtime)."""
    if level != "L3":
        return
    from agent_lab.mission.loop import AUTONOMOUS_ENDS, get_mission_loop

    def _activate(run: dict[str, Any]) -> dict[str, Any]:
        ml = get_mission_loop(run)
        if not ml.get("enabled"):
            return run
        ml["autonomous_segment"] = {
            "active": True,
            "started_at": _now_iso(),
            "ends_on": list(AUTONOMOUS_ENDS),
            "source": "autonomy_l3_ceiling",
        }
        run["mission_loop"] = ml
        return run

    patch_run_meta(folder, _activate)


def observe_autonomy_level_change(
    folder,
    *,
    reason: str,
) -> dict[str, Any]:
    """Append auto/demotion transition when inferred effective level changes."""

    def _apply(run: dict[str, Any]) -> dict[str, Any]:
        block = dict(_autonomy_block(run))
        effective = infer_effective_autonomy_level(run)
        prev_raw = block.get("last_effective")
        if prev_raw in _LEVEL_ORDER:
            prev: AutonomyLevel = prev_raw  # type: ignore[assignment]
        else:
            ceiling = stored_autonomy_level(run)
            prev = ceiling if ceiling is not None else "L0"

        if effective == prev:
            if prev_raw not in _LEVEL_ORDER:
                block["last_effective"] = effective
                block.setdefault("updated_at", _now_iso())
                run["autonomy"] = block
            return run

        trigger: Literal["auto", "human", "demotion"] = (
            "demotion" if _LEVEL_ORDER[effective] < _LEVEL_ORDER[prev] else "auto"
        )
        transitions = list(block.get("transitions") or [])
        transitions.append(
            {
                "from": prev,
                "to": effective,
                "reason": reason[:500],
                "trigger": trigger,
                "at": _now_iso(),
            }
        )
        block["transitions"] = transitions[-20:]
        block["last_effective"] = effective
        # Demotion lowers the Human ceiling so UI stays at the reduced level
        # until Human restores via dial or inbox.
        if trigger == "demotion":
            block["level"] = effective
        block["updated_at"] = _now_iso()
        run["autonomy"] = block
        return run

    updated = patch_run_meta(folder, _apply)
    payload = public_autonomy_payload(updated)
    transitions = payload.get("transitions") or []
    if transitions:
        last = transitions[-1]
        if last.get("trigger") == "demotion":
            from agent_lab.autonomy_inbox import maybe_create_autonomy_demotion_inbox

            maybe_create_autonomy_demotion_inbox(
                folder,
                prev=last.get("from", "L0"),  # type: ignore[arg-type]
                effective=last.get("to", "L0"),  # type: ignore[arg-type]
                reason=str(last.get("reason") or ""),
            )
    return payload
