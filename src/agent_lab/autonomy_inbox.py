"""N4 v2 — inbox-linked autonomy demotion events."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.autonomy_ladder import (
    AutonomyLevel,
    record_autonomy_transition,
)
from agent_lab.human_inbox import create_inbox_item, inbox_items
from agent_lab.run.meta import read_run_meta

_LEVEL_ORDER: dict[str, int] = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}


def _demotion_harvest_key(prev: str, effective: str) -> str:
    return f"autonomy:demotion:{prev}:{effective}"


def human_demotion_reason(reason: str) -> str:
    """Say why autonomy dropped in words the person can act on.

    Mirrors ``autonomyWhyStopped`` in ``web/src/utils/autonomyLadder.ts`` so the
    Inbox row and the autonomy dial tell the same story. Reason codes answer
    "which rule fired"; an Inbox prompt has to answer "what happened to me".
    Unknown codes fall through unchanged rather than being swallowed.
    """
    raw = (reason or "").strip()
    if not raw:
        return "Auto-run was turned down."
    key = raw.lower()
    if "trust_budget" in key or "budget_consumed" in key:
        return "The auto-continue budget ran out."
    if "oracle" in key and ("fail" in key or "consecutive" in key):
        return "Verification (Oracle) failed repeatedly."
    if "diff_risk" in key or "high_risk" in key or key == "high":
        return "The change was classified as high risk."
    if "quarter" in key or "cost_ledger" in key or "budget_usd" in key:
        return "The quarterly spend limit was hit."
    if "risk_pin" in key or "trading" in key:
        return "A risk category (e.g. trading) pinned a more careful mode."
    if "inbox_restore" in key:
        return "Previous setting was restored."
    return raw


def maybe_create_autonomy_demotion_inbox(
    folder: Path,
    *,
    prev: AutonomyLevel,
    effective: AutonomyLevel,
    reason: str,
) -> dict[str, Any] | None:
    """Create a Human Inbox row when autonomy auto-demotion is detected."""
    if _LEVEL_ORDER.get(effective, 0) >= _LEVEL_ORDER.get(prev, 0):
        return None

    key = _demotion_harvest_key(prev, effective)
    run = read_run_meta(folder)
    for item in inbox_items(run):
        if item.get("kind") != "autonomy" or item.get("status") != "pending":
            continue
        if item.get("harvest_key") == key:
            return None

    detail = human_demotion_reason(reason)
    return create_inbox_item(
        folder,
        kind="autonomy",
        source="autonomy_demotion",
        prompt=f"{detail} Agents now stop for your OK before the next step.",
        summary=detail,
        options=[
            {"id": "accept", "label": "Keep asking me"},
            {"id": f"restore:{prev}", "label": f"Go back to running alone ({prev})"},
        ],
        trigger="T-A0",
        refs=[key],
        harvest_key=key,
    )


def handle_autonomy_inbox_resolve(
    folder: Path,
    item: dict[str, Any],
    *,
    selected: list[str] | None = None,
) -> None:
    """Apply Human choice from an autonomy demotion inbox item."""
    choice = ""
    if selected:
        choice = str(selected[0] or "")
    if not choice:
        choice = str(item.get("resolved_choice") or "accept")

    if choice.startswith("restore:"):
        level = choice.split(":", 1)[1].strip().upper()
        if level in _LEVEL_ORDER:
            record_autonomy_transition(
                folder,
                to_level=level,  # type: ignore[arg-type]
                reason="inbox_restore_ceiling",
                trigger="human",
            )
