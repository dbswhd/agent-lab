"""N4 v2 — inbox-linked autonomy demotion events."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.autonomy_inbox import (
    handle_autonomy_inbox_resolve,
    maybe_create_autonomy_demotion_inbox,
)
from agent_lab.autonomy_ladder import public_autonomy_payload, stored_autonomy_level
from agent_lab.human_inbox import inbox_items, resolve_inbox_item
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.trust_budget import consume_auto_merge_budget, set_trust_budget


@pytest.fixture
def session_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "sess-autonomy-inbox"
    folder.mkdir()
    patch_run_meta(folder, lambda run: {**run, "status": "active"})
    return folder


def test_demotion_creates_autonomy_inbox(session_folder: Path) -> None:
    set_trust_budget(session_folder, {"auto_merge_remaining": 1, "auto_merge_total": 1})
    consume_auto_merge_budget(session_folder)
    run = read_run_meta(session_folder)
    pending = [item for item in inbox_items(run) if item.get("kind") == "autonomy" and item.get("status") == "pending"]
    assert len(pending) == 1
    assert pending[0].get("source") == "autonomy_demotion"
    assert pending[0].get("harvest_key") == "autonomy:demotion:L2:L0"


def test_demotion_inbox_dedupes_by_harvest_key(session_folder: Path) -> None:
    item = maybe_create_autonomy_demotion_inbox(
        session_folder,
        prev="L2",
        effective="L0",
        reason="trust_budget_consumed",
    )
    assert item is not None
    again = maybe_create_autonomy_demotion_inbox(
        session_folder,
        prev="L2",
        effective="L0",
        reason="trust_budget_consumed",
    )
    assert again is None


def test_restore_ceiling_from_inbox(session_folder: Path) -> None:
    maybe_create_autonomy_demotion_inbox(
        session_folder,
        prev="L2",
        effective="L0",
        reason="trust_budget_consumed",
    )
    run = read_run_meta(session_folder)
    pending = next(
        item for item in inbox_items(run) if item.get("kind") == "autonomy" and item.get("status") == "pending"
    )
    resolve_inbox_item(
        session_folder,
        pending["id"],
        status="resolved",
        selected=["restore:L2"],
    )
    run = read_run_meta(session_folder)
    assert stored_autonomy_level(run) == "L2"
    payload = public_autonomy_payload(run)
    human = [t for t in payload["transitions"] if t.get("trigger") == "human"]
    assert human
    assert human[-1]["to"] == "L2"


def test_handle_autonomy_inbox_resolve_accept_keeps_effective(session_folder: Path) -> None:
    patch_run_meta(
        session_folder,
        lambda run: {
            **run,
            "autonomy": {"level": "L0", "last_effective": "L0"},
        },
    )
    item = maybe_create_autonomy_demotion_inbox(
        session_folder,
        prev="L2",
        effective="L0",
        reason="trust_budget_consumed",
    )
    assert item is not None
    handle_autonomy_inbox_resolve(session_folder, item, selected=["accept"])
    run = read_run_meta(session_folder)
    assert stored_autonomy_level(run) == "L0"
