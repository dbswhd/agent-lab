"""Decision clarity P0 — composer priority + event stack."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def test_composer_decision_surface_replaces_stacked_banners():
    room = _read("web", "src", "components", "RoomChat.tsx")
    main_pane = _read("web", "src", "components", "RoomChatMainPane.tsx")
    priority = _read("web", "src", "utils", "composerDecisionPriority.ts")
    surface = _read("web", "src", "components", "ComposerDecisionSurface.tsx")
    assert "RoomChatMainPane" in room
    assert "ComposerDecisionSurface" in main_pane
    assert "ComposerNoticeCard" in surface
    assert "<PlanWorkflowBanner" not in room
    assert "<HumanDecisionBanner" not in room
    assert "<RecoveryStrip" not in room
    assert "taskbar-dock" not in room
    assert "RoomTaskBar" not in room
    assert "ComposerEventStack" in room
    assert "InspectorTasksSummary" not in room
    assert "pickComposerDecisionTier" in priority
    assert '"human_gate"' in priority
    assert "showPlanApproval" in priority


def test_composer_event_stack_hosts_inbox_and_execute():
    room = _read("web", "src", "components", "RoomChat.tsx")
    stack = _read("web", "src", "components", "ComposerEventStack.tsx")
    assert "HumanInboxPanel" in stack
    assert "ExecuteQueueBar" in stack
    assert "WorkPlanApprovalSection" in stack
    assert "PlanExecutePanel" in _read("web", "src", "components", "WorkToolPanel.tsx")
    assert 'rightPanelMode === "inbox"' not in room
    assert 'rightPanelMode === "tasks"' not in room
    assert 'rightPanelMode === "plan"' not in room


def test_human_inbox_composer_only():
    room = _read("web", "src", "components", "RoomChat.tsx")
    assert "presentation=\"composer\"" in _read(
        "web", "src", "components", "ComposerEventStack.tsx"
    )
    assert "readOnly={inboxPendingCount > 0}" not in room


def test_decision_blocked_headline_ssot():
    headline = _read("web", "src", "utils", "decisionBlockedHeadline.ts")
    main_pane = _read("web", "src", "components", "RoomChatMainPane.tsx")
    assert "buildDecisionBlockedHeadline" in headline
    assert "decisionBlockedHeadline" in main_pane
    assert "blockedHeadline={decisionBlockedHeadline}" in main_pane
    assert "blockedHeadline.headline" in _read(
        "web", "src", "components", "ComposerDecisionSurface.tsx"
    )
