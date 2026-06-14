"""Plan composer toggle ↔ workflow FSM alignment (UI contract)."""

from __future__ import annotations

from pathlib import Path


def _read(*parts: str) -> str:
    return Path(__file__).resolve().parents[1].joinpath(*parts).read_text(encoding="utf-8")


def test_plan_toggle_sync_utils_exist():
    sync = _read("web", "src", "utils", "planComposerSync.ts")
    assert "suggestPlanToggleForWorkflow" in sync
    assert "isPlanWorkflowAwaitingApproval" in sync


def test_room_chat_blocks_send_during_human_pending():
    room = _read("web", "src", "components", "RoomChat.tsx")
    assert "planWorkflowAwaitingApproval" in room
    assert "planWorkflowComposerBlocked" in room
    assert "planWorkflowAwaitingApproval || turnProfile === \"loop\"" in room


def test_compose_mode_per_session_plan_toggle():
    compose = _read("web", "src", "utils", "composeMode.ts")
    assert "getPlanAfterSendForSession" in compose
    assert "setPlanAfterSendForSession" in compose
    assert "agent-lab-plan-after-send:" in compose


def test_side_discuss_hint_in_mode_chip():
    room = _read("web", "src", "components", "RoomChat.tsx")
    assert "planWorkflowSideDiscussHint" in room
