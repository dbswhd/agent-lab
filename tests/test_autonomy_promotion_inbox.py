"""N4 — promotion inbox resolve (L1→L2 / L2→L3 Human gate)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.autonomy_ladder import infer_effective_autonomy_level, stored_autonomy_level
from agent_lab.autonomy_promotion import (
    L1_TO_L2_MISSIONS,
    L2_TO_L3_MIN_MISSIONS,
    maybe_create_promotion_inbox,
)
from agent_lab.human_inbox import resolve_inbox_item
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.trust_budget import set_trust_budget


@pytest.fixture
def session_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "sess-promo-inbox"
    folder.mkdir()
    patch_run_meta(folder, lambda run: {**run, "status": "active"})
    return folder


def test_l1_to_l2_promotion_inbox_resolve(session_folder: Path) -> None:
    set_trust_budget(session_folder, {"auto_merge_remaining": 3, "auto_merge_total": 5})
    patch_run_meta(
        session_folder,
        lambda run: {
            **run,
            "autonomy": {
                "level": "L1",
                "promotion": {"l1_to_l2": {"missions_completed": L1_TO_L2_MISSIONS}},
            },
        },
    )
    item = maybe_create_promotion_inbox(session_folder, transition="L1_to_L2")
    assert item is not None
    assert item.get("source") == "autonomy_promotion"

    resolve_inbox_item(
        session_folder,
        item["id"],
        status="resolved",
        selected=["promote:L2"],
    )
    run = read_run_meta(session_folder)
    assert stored_autonomy_level(run) == "L2"


def test_l2_to_l3_promotion_activates_mission_autorun(session_folder: Path) -> None:
    patch_run_meta(
        session_folder,
        lambda run: {
            **run,
            "autonomy": {
                "level": "L2",
                "promotion": {
                    "l2_to_l3": {
                        "missions_total": L2_TO_L3_MIN_MISSIONS,
                        "missions_done": L2_TO_L3_MIN_MISSIONS,
                        "inbox_escalations": 0,
                    }
                },
            },
            "mission_loop": {"enabled": True, "phase": "EXECUTE_QUEUE"},
        },
    )
    item = maybe_create_promotion_inbox(session_folder, transition="L2_to_L3")
    assert item is not None

    resolve_inbox_item(
        session_folder,
        item["id"],
        status="resolved",
        selected=["promote:L3"],
    )
    run = read_run_meta(session_folder)
    assert stored_autonomy_level(run) == "L3"
    assert run["mission_loop"]["autonomous_segment"]["active"] is True
    assert infer_effective_autonomy_level(run) == "L3"


def test_promotion_inbox_dedupes(session_folder: Path) -> None:
    patch_run_meta(
        session_folder,
        lambda run: {
            **run,
            "autonomy": {
                "level": "L1",
                "promotion": {"l1_to_l2": {"missions_completed": L1_TO_L2_MISSIONS}},
            },
        },
    )
    set_trust_budget(session_folder, {"auto_merge_remaining": 1, "auto_merge_total": 3})
    first = maybe_create_promotion_inbox(session_folder, transition="L1_to_L2")
    second = maybe_create_promotion_inbox(session_folder, transition="L1_to_L2")
    assert first is not None
    assert second is None
