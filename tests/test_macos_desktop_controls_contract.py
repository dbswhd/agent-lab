"""PR 3 macOS desktop controls and real-window smoke contracts."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_session_rows_are_keyboard_controls_and_searchable():
    session_list = _read("web/src/components/SessionList.tsx")
    app = _read("web/src/App.tsx")

    assert 'className={`session-row' in session_list
    assert 'type="button"' in session_list
    assert 'aria-current=' in session_list
    assert 'type="search"' in app
    assert 'aria-label="세션 검색"' in app


def test_macos_shortcuts_cover_new_sidebar_and_content_tabs():
    app = _read("web/src/App.tsx")
    shortcut = _read("web/src/utils/desktopShortcuts.ts")
    workspace_tabs = _read("web/src/hooks/useWorkspaceTabs.ts")
    viewer = _read("web/src/components/SessionViewer.tsx")

    assert 'key === "n"' in app
    assert 'event.ctrlKey && key === "s"' in app
    assert '"1", "2", "3", "4", "5"' in app
    assert "requestWorkspaceTabByIndex" in app
    assert "WORKSPACE_TAB_SHORTCUT_EVENT" in shortcut
    assert "WORKSPACE_TAB_SHORTCUT_EVENT" in workspace_tabs
    assert "CONTENT_TAB_SHORTCUT_EVENT" in shortcut
    assert "CONTENT_TAB_SHORTCUT_EVENT" in workspace_tabs
    assert "CONTENT_TAB_SHORTCUT_EVENT" in viewer


def test_tauri_titlebar_and_minimum_window_are_real_window_smoke_contracts():
    titlebar = _read("web/src/components/MacTitlebar.tsx")
    smoke = _read("scripts/smoke_tauri_ui.sh")
    capability = _read("web/src-tauri/capabilities/default.json")
    config = json.loads(_read("web/src-tauri/tauri.conf.json"))
    window = config["app"]["windows"][0]

    assert "data-tauri-drag-region" in titlebar
    assert "getCurrentWindow().startDragging()" in titlebar
    assert "core:window:allow-start-dragging" in capability
    assert "drag_tauri_titlebar.swift" in smoke
    assert "WINDOW_MIN_WIDTH < 900" in smoke
    assert "WINDOW_MIN_HEIGHT < 600" in smoke
    assert window["minWidth"] == 900
    assert window["minHeight"] == 600
