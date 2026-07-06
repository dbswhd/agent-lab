from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from agent_lab.autonomy_ladder import AutonomyLevel, record_autonomy_transition
from agent_lab.autonomy_promotion import (
    PromotionTransition,
    _promotion_harvest_key,
    evaluate_l1_to_l2,
    evaluate_l2_to_l3,
)
from agent_lab.run.meta import read_run_meta

_LEVELS_BY_ID: dict[str, AutonomyLevel] = {"L0": "L0", "L1": "L1", "L2": "L2", "L3": "L3"}


def _target_for_transition(transition: PromotionTransition) -> Literal["L2", "L3"]:
    if transition == "L1_to_L2":
        return "L2"
    return "L3"


def maybe_create_promotion_inbox(folder: Path, *, transition: PromotionTransition) -> dict[str, Any] | None:
    from agent_lab.human_inbox import create_inbox_item, inbox_items

    target = _target_for_transition(transition)
    key = _promotion_harvest_key(transition)
    run = read_run_meta(folder)
    for item in inbox_items(run):
        if item.get("kind") != "autonomy" or item.get("status") != "pending":
            continue
        if item.get("harvest_key") == key:
            return None

    eval_row = evaluate_l1_to_l2(run) if transition == "L1_to_L2" else evaluate_l2_to_l3(run)
    if not eval_row.get("eligible"):
        return None

    detail = (
        f"Promotion {transition} eligible - missions={eval_row.get('missions_completed')}"
        if transition == "L1_to_L2"
        else (
            f"Promotion {transition} eligible - completion={eval_row.get('completion_rate')}, "
            f"escalation={eval_row.get('escalation_rate')}"
        )
    )
    return create_inbox_item(
        folder,
        kind="autonomy",
        source="autonomy_promotion",
        prompt=f"Approve autonomy ceiling raise to {target}? {detail}",
        summary=f"Promote -> {target}",
        options=[
            {"id": f"promote:{target}", "label": f"Approve {target}"},
            {"id": "defer", "label": "Defer"},
        ],
        trigger="T-A1",
        refs=[key],
        harvest_key=key,
    )


def handle_autonomy_promotion_resolve(
    folder: Path,
    item: dict[str, Any],
    *,
    selected: list[str] | None = None,
) -> None:
    choice = str((selected or [""])[0] or item.get("resolved_choice") or "defer")
    if not choice.startswith("promote:"):
        return
    level = _LEVELS_BY_ID.get(choice.split(":", 1)[1].strip().upper())
    if level is None:
        return
    transition = str(item.get("harvest_key") or "").split(":")[-1]
    record_autonomy_transition(
        folder,
        to_level=level,
        reason=f"promotion_inbox:{transition}",
        trigger="human",
    )
