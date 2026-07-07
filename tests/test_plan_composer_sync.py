"""Plan composer ↔ workflow FSM alignment (UI contract, Wave F TurnPolicy)."""

from __future__ import annotations

from ui_surface_bundles import room_chat_orchestrator, room_chat_surface
from pathlib import Path


def _read(*parts: str) -> str:
    return Path(__file__).resolve().parents[1].joinpath(*parts).read_text(encoding="utf-8")


def test_plan_workflow_sync_utils_exist():
    sync = _read("web", "src", "utils", "planComposerSync.ts")
    assert "isPlanWorkflowAwaitingApproval" in sync


def test_room_chat_blocks_send_during_human_pending():
    room = room_chat_surface()
    orchestrator = room_chat_orchestrator()
    shell = _read("web", "src", "hooks", "useRoomPlanShellState.ts")
    assert "useRoomChat" in room
    assert "useRoomPlanShellState" in orchestrator
    assert "composerSendLocked" in room
    assert "planWorkflowComposerBlocked" in shell
    assert "isPlanWorkflowAwaitingApproval" in shell


def test_casual_send_has_no_compose_mode_plumbing():
    prefs = _read("web", "src", "hooks", "useRoomComposerPrefs.ts")
    execute = _read("web", "src", "hooks", "useRoomExecuteSend.ts")
    client = _read("web", "src", "api", "client.ts")
    room = room_chat_surface()
    orchestrator = room_chat_orchestrator()
    assert "composeMode" not in prefs
    assert "ComposeMode" not in execute
    assert "composeMode.ts" not in orchestrator
    assert "useRoomComposerPrefs" in orchestrator
    assert "planComposeActive" not in room
    assert "planComposeActive" not in orchestrator
    assert 'form.append("mode", "discuss")' in client


def test_side_discuss_hint_in_mode_chip():
    workflow_view = _read("web", "src", "utils", "planWorkflowView.ts")
    messages = _read("web", "src", "i18n", "messages.ts")
    room = room_chat_surface()
    assert "isPlanWorkflowComposerHint" in workflow_view
    assert "planWorkflowSideDiscussHint" in messages
    assert "showPlanWorkflowComposerHint" in room
