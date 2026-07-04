"""Autonomy Ladder (N4) — L0~L3 session trust level SSOT."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from agent_lab.auto_approve_gate import auto_approve_threshold
from agent_lab.run.meta import patch_run_meta
from agent_lab.trust_budget import get_trust_budget

AutonomyLevel = Literal["L0", "L1", "L2", "L3"]

_LEVEL_ORDER: dict[str, int] = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}

_LEVEL_NAMES: dict[str, str] = {
    "L0": "Manual",
    "L1": "Assisted",
    "L2": "Budgeted",
    "L3": "Autonomous",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _autonomy_block(run_meta: dict[str, Any] | None) -> dict[str, Any]:
    meta = run_meta or {}
    raw = meta.get("autonomy")
    return raw if isinstance(raw, dict) else {}


def stored_autonomy_level(run_meta: dict[str, Any] | None) -> AutonomyLevel:
    level = _autonomy_block(run_meta).get("level")
    if level in _LEVEL_ORDER:
        return level  # type: ignore[return-value]
    return "L0"


def infer_effective_autonomy_level(run_meta: dict[str, Any] | None) -> AutonomyLevel:
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

    if auto_approve_threshold() is not None:
        return "L1"

    return "L0"


def resolve_display_autonomy_level(run_meta: dict[str, Any] | None) -> AutonomyLevel:
    """UI level: effective signals capped by stored ceiling when set."""
    stored = stored_autonomy_level(run_meta)
    effective = infer_effective_autonomy_level(run_meta)
    if _LEVEL_ORDER[effective] <= _LEVEL_ORDER[stored]:
        return effective
    return stored


def public_autonomy_payload(run_meta: dict[str, Any] | None) -> dict[str, Any]:
    meta = run_meta or {}
    block = _autonomy_block(meta)
    budget = get_trust_budget(meta)
    effective = infer_effective_autonomy_level(meta)
    display = resolve_display_autonomy_level(meta)
    ml = meta.get("mission_loop") if isinstance(meta.get("mission_loop"), dict) else {}
    seg = ml.get("autonomous_segment") if isinstance(ml.get("autonomous_segment"), dict) else {}
    transitions_raw = block.get("transitions")
    transitions: list[dict[str, Any]] = []
    if isinstance(transitions_raw, list):
        transitions = [row for row in transitions_raw if isinstance(row, dict)][-5:]
    return {
        "level": stored_autonomy_level(meta),
        "effective_level": effective,
        "display_level": display,
        "level_name": _LEVEL_NAMES.get(display, display),
        "trust_budget": {
            "auto_merge_remaining": int(budget.get("auto_merge_remaining") or 0),
            "auto_merge_total": int(budget.get("auto_merge_total") or 0),
        },
        "signals": {
            "auto_approve_enabled": auto_approve_threshold() is not None,
            "mission_loop_enabled": bool(ml.get("enabled")),
            "autonomous_segment_active": bool(seg.get("active")),
        },
        "transitions": transitions,
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
        prev = from_level or stored_autonomy_level(run)
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
    return public_autonomy_payload(updated)


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
            prev = stored_autonomy_level(run)

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
        block["level"] = effective
        block["updated_at"] = _now_iso()
        run["autonomy"] = block
        return run

    updated = patch_run_meta(folder, _apply)
    return public_autonomy_payload(updated)
