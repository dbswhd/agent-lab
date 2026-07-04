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

    detail = reason.strip() or "trust or mission signals dropped"
    return create_inbox_item(
        folder,
        kind="autonomy",
        source="autonomy_demotion",
        prompt=f"Autonomy decreased from {prev} to {effective}. {detail}",
        summary=f"{prev} → {effective}",
        options=[
            {"id": "accept", "label": f"Keep {effective}"},
            {"id": f"restore:{prev}", "label": f"Restore ceiling to {prev}"},
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
