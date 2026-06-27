"""Decision clarity P0 — composer priority + inspector tasks summary."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def test_composer_decision_surface_replaces_stacked_banners():
    room = _read("web", "src", "components", "RoomChat.tsx")
    priority = _read("web", "src", "utils", "composerDecisionPriority.ts")
    surface = _read("web", "src", "components", "ComposerDecisionSurface.tsx")
    assert "ComposerDecisionSurface" in room
    assert "ComposerNoticeCard" in surface
    assert "<PlanWorkflowBanner" not in room
    assert "<HumanDecisionBanner" not in room
    assert "<RecoveryStrip" not in room
    assert "taskbar-dock" not in room
    assert "RoomTaskBar" not in room
    assert "InspectorTasksSummary" in room
    assert "pickComposerDecisionTier" in priority
    assert '"human_gate"' in priority


def test_inspector_tasks_summary_replaces_workbench_approval_dupes():
    room = _read("web", "src", "components", "RoomChat.tsx")
    summary = _read("web", "src", "components", "InspectorTasksSummary.tsx")
    assert "InspectorTasksSummary" in room
    assert "HumanGatePanel" not in room
    assert "<PlanWorkflowBanner" not in room
    assert "VerifiedLoopBanner" not in room
    assert "GoalLoopBanner" not in room
    assert 'rightPanelMode === "tasks"' in room
    assert "Work · 승인하기" not in room
    assert "buildInspectorTasksSummaryView" in summary


def test_workbench_inbox_readonly_when_composer_pending():
    room = _read("web", "src", "components", "RoomChat.tsx")
    inbox = _read("web", "src", "components", "HumanInboxPanel.tsx")
    assert "readOnly={inboxPendingCount > 0}" in room
    assert "readOnly" in inbox
    assert "inbox-readonly-banner" in inbox


def test_decision_blocked_headline_ssot():
    headline = _read("web", "src", "utils", "decisionBlockedHeadline.ts")
    room = _read("web", "src", "components", "RoomChat.tsx")
    assert "buildDecisionBlockedHeadline" in headline
    assert "decisionBlockedHeadline" in room
    assert "blockedHeadline={decisionBlockedHeadline}" in room
    assert "blockedHeadline.headline" in _read(
        "web", "src", "components", "ComposerDecisionSurface.tsx"
    )
