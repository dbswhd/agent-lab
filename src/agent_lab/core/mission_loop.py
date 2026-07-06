"""Mission loop snapshot — read-only merge from run.json (F12, stdlib only)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DEFAULT_MAX_MOMUS_ROUNDS = 3
DEFAULT_MAX_REPAIR_PER_ACTION = 2
DEFAULT_MAX_MISSION_ITERATIONS = 20
_AUTONOMOUS_ENDS = (
    "merge_review",
    "circuit_breaker",
    "mission_done",
    "inbox_escalate",
)
AUTONOMOUS_ENDS = _AUTONOMOUS_ENDS


def default_mission_loop() -> dict[str, Any]:
    return {
        "enabled": False,
        "phase": "MISSION_DEFINE",
        "iteration": 0,
        "max_mission_iterations": DEFAULT_MAX_MISSION_ITERATIONS,
        "pending_action_indices": [],
        "current_action_index": None,
        "action_repair_counts": {},
        "max_repair_per_action": DEFAULT_MAX_REPAIR_PER_ACTION,
        "last_verify": None,
        "last_execution_id": None,
        "plan_gate": {
            "status": "pending",
            "momus_round": 0,
            "max_momus_rounds": DEFAULT_MAX_MOMUS_ROUNDS,
            "last_reject_reason": None,
            "failures": [],
        },
        "wisdom_refs": [],
        "discuss_recovery": {
            "pending": False,
            "reason": None,
            "action_index": None,
            "started_at": None,
            "completed_at": None,
        },
        "autonomous_segment": {
            "active": False,
            "started_at": None,
            "ends_on": list(_AUTONOMOUS_ENDS),
        },
        "circuit_breaker": False,
        "circuit_breaker_reason": None,
        "pause_reason": None,
        "last_partial": None,
    }


def get_mission_loop(run: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = (run or {}).get("mission_loop")
    if not isinstance(raw, dict):
        return default_mission_loop()
    base = default_mission_loop()
    for key, val in raw.items():
        if key == "plan_gate" and isinstance(val, dict):
            gate = dict(base["plan_gate"])
            gate.update(val)
            base["plan_gate"] = gate
        elif key == "autonomous_segment" and isinstance(val, dict):
            seg = dict(base["autonomous_segment"])
            seg.update(val)
            base["autonomous_segment"] = seg
        elif key == "discuss_recovery" and isinstance(val, dict):
            rec = dict(base["discuss_recovery"])
            rec.update(val)
            base["discuss_recovery"] = rec
        else:
            base[key] = val
    return base
