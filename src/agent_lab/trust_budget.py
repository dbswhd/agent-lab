"""Trust budget for governed auto-merge (Gate 1-D)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from agent_lab.gate_scope import GateProfile, get_gate_profile
from agent_lab.run_meta import patch_run_meta

ClassifierAllow = Literal["docs_only", "test_only", "single_file"]

_DEFAULT_DEV: dict[str, Any] = {
    "auto_merge_remaining": 0,
    "auto_merge_total": 0,
    "classifier_allow": [],
}

_DEFAULT_ASSISTANT: dict[str, Any] = {
    "auto_merge_remaining": 0,
    "auto_merge_total": 0,
    "classifier_allow": ["docs_only", "test_only", "single_file"],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_trust_budget(profile: GateProfile) -> dict[str, Any]:
    return dict(_DEFAULT_ASSISTANT if profile == "assistant" else _DEFAULT_DEV)


def get_trust_budget(run_meta: dict[str, Any] | None) -> dict[str, Any]:
    meta = run_meta or {}
    raw = meta.get("trust_budget")
    if not isinstance(raw, dict):
        return default_trust_budget(get_gate_profile(meta))
    profile = get_gate_profile(meta)
    base = default_trust_budget(profile)
    merged = {**base, **raw}
    allow = merged.get("classifier_allow")
    if isinstance(allow, str):
        merged["classifier_allow"] = [a.strip() for a in allow.split(",") if a.strip()]
    elif allow is None:
        merged["classifier_allow"] = list(base["classifier_allow"])
    else:
        merged["classifier_allow"] = list(allow)
    try:
        merged["auto_merge_remaining"] = int(merged.get("auto_merge_remaining") or 0)
    except (TypeError, ValueError):
        merged["auto_merge_remaining"] = 0
    try:
        merged["auto_merge_total"] = int(merged.get("auto_merge_total") or 0)
    except (TypeError, ValueError):
        merged["auto_merge_total"] = merged["auto_merge_remaining"]
    return merged


def set_trust_budget(folder, patch: dict[str, Any]) -> dict[str, Any]:
    def _apply(run: dict[str, Any]) -> dict[str, Any]:
        current = get_trust_budget(run)
        for key, value in patch.items():
            if value is not None:
                current[key] = value
        current["updated_at"] = _now_iso()
        run["trust_budget"] = current
        return run

    updated = patch_run_meta(folder, _apply)
    return get_trust_budget(updated)


def consume_auto_merge_budget(folder) -> tuple[int, int]:
    """Decrement budget; returns (before, after). Raises if empty."""

    state = {"before": 0, "after": 0}

    def _consume(run: dict[str, Any]) -> dict[str, Any]:
        budget = get_trust_budget(run)
        before = int(budget.get("auto_merge_remaining") or 0)
        if before <= 0:
            raise ValueError("trust_budget exhausted")
        after = before - 1
        budget["auto_merge_remaining"] = after
        budget["last_consumed_at"] = _now_iso()
        run["trust_budget"] = budget
        state["before"] = before
        state["after"] = after
        return run

    patch_run_meta(folder, _consume)
    return state["before"], state["after"]
