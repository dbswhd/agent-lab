"""C3 — risk-inverse profile pin: external-risk topics pin the autonomy ceiling.

See docs/N10-USER-LOOP-WISDOM-DRAFT.md §4-C3 and NORTH-STAR N2. The 2026-07-06
usage audit found the opposite of what safety requires: sessions touching
external risk (trading/live-API/payment) had *looser* verification than core
agent-lab work, not tighter (G4). This module closes that gap by pinning the
autonomy ceiling to L1 the first time a risky category is detected in a
session's turn — reusing existing N4 machinery (``record_autonomy_transition``,
``maybe_create_autonomy_demotion_inbox``) rather than inventing a new gate.

Design constraints (NORTH-STAR §6 mote check):
- No new Inbox kind — the existing N4 demotion inbox item ("Keep L1" /
  "Restore ceiling to <prev>") already *is* the explicit-override escape
  hatch this needs.
- Pins once per category per session (idempotent) so a Human's explicit
  override (raising the ceiling back via the existing inbox/API) sticks —
  this module never re-lowers a ceiling the Human already restored.
- Read/patch only at turn close (``_finalize_durable_turn``), never mid-turn,
  per the run_meta write-discipline rule (F4, CLAUDE.md) — this mirrors
  where ``record_turn_outcome``/``maybe_run_drift_audit`` already run.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.env_flags import env_bool
from agent_lab.run.state import RunStateLike

# F5 lane scope (docs/F5-TRADING-ISOLATION.md) — topic_router already classifies
# this category; no new taxonomy is introduced here.
RISK_CATEGORIES = frozenset({"trading"})
RISK_PIN_CEILING = "L1"

_LEVEL_ORDER: dict[str, int] = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}


def risk_pin_enabled() -> bool:
    return env_bool("AGENT_LAB_RISK_PIN", default=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _turn_category(run_meta: RunStateLike) -> str:
    turns = run_meta.get("turns") or []
    if not turns or not isinstance(turns[-1], dict):
        return ""
    category = turns[-1].get("category")
    if not isinstance(category, dict):
        return ""
    return str(category.get("value") or "")


def _record_pin_marker(folder: Path, category: str) -> dict[str, Any]:
    from agent_lab.run.meta import patch_run_meta

    marker = {"category": category, "ceiling": RISK_PIN_CEILING, "pinned_at": _now_iso()}

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        run["risk_pin"] = marker
        return run

    patch_run_meta(folder, _patch)
    return marker


def maybe_apply_risk_pin(folder: Path, human_turn: int) -> dict[str, Any] | None:
    """Pin the autonomy ceiling once per risk category, at turn close (fail-open)."""
    try:
        if not risk_pin_enabled():
            return None
        from agent_lab.run.meta import read_run_meta

        run = read_run_meta(folder)
        category = _turn_category(run)
        if category not in RISK_CATEGORIES:
            return None

        existing = run.get("risk_pin")
        if isinstance(existing, dict) and existing.get("category") == category:
            return None  # already pinned this session for this category — Human override sticks

        from agent_lab.autonomy_ladder import infer_effective_autonomy_level, stored_autonomy_level

        ceiling = stored_autonomy_level(run)
        prev = ceiling if ceiling is not None else infer_effective_autonomy_level(run)
        if _LEVEL_ORDER.get(prev, 0) <= _LEVEL_ORDER[RISK_PIN_CEILING]:
            return _record_pin_marker(folder, category)

        from agent_lab.autonomy_inbox import maybe_create_autonomy_demotion_inbox
        from agent_lab.autonomy_ladder import record_autonomy_transition

        reason = (
            f"risk category '{category}' detected — autonomy ceiling pinned to {RISK_PIN_CEILING} (C3 risk-inverse pin)"
        )
        record_autonomy_transition(
            folder,
            to_level=RISK_PIN_CEILING,  # type: ignore[arg-type]
            reason=reason,
            trigger="demotion",
        )
        maybe_create_autonomy_demotion_inbox(
            folder,
            prev=prev,  # type: ignore[arg-type]
            effective=RISK_PIN_CEILING,  # type: ignore[arg-type]
            reason=reason,
        )
        return _record_pin_marker(folder, category)
    except Exception:  # fail-open: risk pin must never block turn completion
        import logging

        logging.getLogger(__name__).warning("maybe_apply_risk_pin failed for %s", folder, exc_info=True)
        return None


__all__ = [
    "RISK_CATEGORIES",
    "RISK_PIN_CEILING",
    "risk_pin_enabled",
    "maybe_apply_risk_pin",
]
