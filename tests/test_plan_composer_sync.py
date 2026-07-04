"""Plan composer ↔ workflow FSM alignment (UI contract, Wave F TurnPolicy)."""

from __future__ import annotations

from pathlib import Path


def _read(*parts: str) -> str:
    return Path(__file__).resolve().parents[1].joinpath(*parts).read_text(encoding="utf-8")


def test_plan_workflow_sync_utils_exist():
    sync = _read("web", "src", "utils", "planComposerSync.ts")
    assert "isPlanWorkflowAwaitingApproval" in sync


def test_room_chat_blocks_send_during_human_pending():
    room = _read("web", "src", "components", "RoomChat.tsx")
    assert "planWorkflowAwaitingApproval" in room
    assert "planWorkflowComposerBlocked" in room
    assert "planWorkflowAwaitingApproval ||" in room
    assert "planComposeActive" in room


def test_compose_mode_derived_from_preset():
    prefs = _read("web", "src", "utils", "roomComposerPrefs.ts")
    room = _read("web", "src", "components", "RoomChat.tsx")
    assert 'roomPreset === "supervisor"' in prefs
    assert "planComposeActive" in prefs
    assert "useRoomComposerPrefs" in room
    assert "planComposeActive" in room


def test_side_discuss_hint_in_mode_chip():
    workflow_view = _read("web", "src", "utils", "planWorkflowView.ts")
    messages = _read("web", "src", "i18n", "messages.ts")
    room = _read("web", "src", "components", "RoomChat.tsx")
    assert "isPlanWorkflowComposerHint" in workflow_view
    assert "planWorkflowSideDiscussHint" in messages
    assert "showPlanWorkflowComposerHint" in room
