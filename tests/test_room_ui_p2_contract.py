"""PR 2 Room visual, accessibility, and narrow-width contracts."""

from __future__ import annotations

from ui_surface_bundles import room_chat_surface
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_room_task_bar_and_banners_have_accessible_names():
    task_bar = _read("web/src/components/RoomTaskBar.tsx")
    room_chat = room_chat_surface()
    composer_shell = _read("web/src/components/RoomChatComposerShell.tsx")
    recovery = _read("web/src/components/RecoveryStrip.tsx")
    readiness = _read("web/src/components/ReadinessComposerBar.tsx")

    assert 'role="region"' in task_bar
    assert 'aria-label="팀 할 일 목록"' in task_bar
    assert 'aria-label="합의 차단"' in task_bar
    assert 'aria-label="확인 질문"' in composer_shell
    assert 'aria-label="일부 에이전트 실패"' not in room_chat
    assert "room-partial-banner" not in room_chat
    assert 'role={items.length > 0 ? "alert" : "status"}' in recovery
    assert 'aria-label="복구 액션"' in recovery
    assert "진단 정보" in recovery
    assert "<summary>details</summary>" not in recovery
    assert 'aria-label="에이전트 준비 상태"' in readiness


def test_room_task_bar_has_tauri_minimum_width_layout():
    css = _read("web/src/styles/layout.css")

    assert "@media (max-width: 1000px)" in css
    assert ".taskbar-lead-select,\n  .taskbar__summary" in css
    assert "flex: 1 0 100%;" in css


def test_room_figma_mapping_uses_code_tokens():
    room_doc = _read("docs/archive/legacy/04-multi-agent-room.md")

    for token in (
        "--color-bubble-sent",
        "--color-agent-cursor",
        "--lg-panel-surface",
        ".taskbar",
        ".taskbar-dock",
        ".chat-line--synthesis",
        ".clarifier-banner",
    ):
        assert token in room_doc
