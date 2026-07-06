"""PR 3 macOS desktop controls and real-window smoke contracts."""

from __future__ import annotations

from ui_surface_bundles import room_chat_surface
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_room_send_keeps_transcript_visible_during_session_bind():
    app = _read("web/src/App.tsx")
    main_pane = _read("web/src/components/RoomChatMainPane.tsx")
    transcript = _read("web/src/components/RoomTranscriptPanel.tsx")

    assert "detail != null" in app
    assert "boundFromComposer" in _read("web/src/hooks/useWorkspaceTabs.ts")
    assert "loading &&" in transcript
    assert "!isNew &&" in transcript
    assert "!running &&" in transcript
    assert "visibleMessages.length === 0" in transcript
    assert "RoomTranscriptPanel" in main_pane


def test_session_rows_are_keyboard_controls_and_searchable():
    session_list = _read("web/src/components/SessionList.tsx")
    app = _read("web/src/App.tsx")

    assert '"session-item"' in session_list
    assert 'type="button"' in session_list
    assert "aria-current=" in session_list
    assert 'type="search"' in app
    assert 'aria-label="세션 검색"' in app


def test_macos_shortcuts_cover_new_sidebar_and_content_tabs():
    app = _read("web/src/App.tsx")
    shortcut = _read("web/src/utils/desktopShortcuts.ts")
    workspace_tabs = _read("web/src/hooks/useWorkspaceTabs.ts")
    room = room_chat_surface()

    assert 'key === "n"' in app
    assert 'event.ctrlKey && key === "s"' in app
    assert '"1", "2", "3", "4", "5"' in app
    assert "requestWorkspaceTabByIndex" in app
    assert '"1": "transcript"' in shortcut
    assert '"2": "diff"' in shortcut
    assert '"3": "background"' in shortcut
    # ⌘4 must map to the Files panel (Workspace Files feature).
    assert '"4": "files"' in shortcut
    assert '"5": "preview"' in shortcut
    assert "WORKSPACE_TAB_SHORTCUT_EVENT" in shortcut
    assert "WORKSPACE_TAB_SHORTCUT_EVENT" in workspace_tabs
    assert "CONTENT_TAB_SHORTCUT_EVENT" in shortcut
    assert "CONTENT_TAB_SHORTCUT_EVENT" in workspace_tabs
    assert "boundFromComposer" in workspace_tabs
    assert 'setInspectorTabState("tools")' in workspace_tabs
    assert "setRightPanelModeState(tab)" in workspace_tabs
    assert "<WorkspaceTabBar" not in room


def test_context_tools_and_workbench_width_preferences_are_separate():
    prefs = _read("web/src/utils/inspectorPanePrefs.ts")
    room = room_chat_surface()
    workbench_layout = _read("web/src/hooks/useRoomWorkbenchLayout.ts")

    assert 'WIDTH_KEY = "agent-lab-inspector-width"' in prefs
    assert 'TOOLS_WIDTH_KEY = "agent-lab-tools-inspector-width"' in prefs
    assert "WORKBENCH_WIDTH_CONTENT_RATIO" in prefs
    assert "workbenchContentWidth" in prefs
    assert "resolveDefaultWorkbenchWidth" in prefs
    assert "Main column flexes via --composer-max" in prefs
    assert "TOOLS_INSPECTOR_DEFAULT_WIDTH = 420" in prefs
    assert "TOOLS_INSPECTOR_MIN_WIDTH = 320" in prefs
    assert "TOOLS_INSPECTOR_MAX_WIDTH = 760" in prefs
    assert "WORKBENCH_PANEL_DEFAULT_WIDTH = 520" in prefs
    assert "WORKBENCH_PANEL_MIN_WIDTH = 360" in prefs
    assert "WORKBENCH_PANEL_MAX_WIDTH = 1600" in prefs
    assert "maxWorkbenchPanelWidth" in prefs
    assert "handleSelectRightPanelMode" in room
    assert "clampWorkbenchPanelWidth" in workbench_layout
    assert "workbenchWidthUserAdjustedRef" in workbench_layout


def test_workspace_chrome_replaces_web_traffic_lights_and_titlebar_logo():
    app = _read("web/src/App.tsx")
    room = room_chat_surface()
    chrome = _read("web/src/components/WorkspaceChrome.tsx")

    assert "traffic-lights" not in app
    assert "traffic-lights" not in chrome
    assert "MacTitlebar" not in app
    assert "app--tauri" in app
    assert "<WorkspaceChrome" in room
    assert "workspace-chrome--tauri" in chrome
    assert "WorkbenchModeMenu" in chrome


def test_workbench_diff_panel_reuses_execution_diff_records():
    diff_panel = _read("web/src/components/DiffToolPanel.tsx")
    inspector = _read("web/src/components/RoomChatInspector.tsx")

    assert "PlanExecutionRecord" in diff_panel
    assert "findActiveExecution" in diff_panel
    assert "PlanDiffStat" in diff_panel
    assert "SideBySideDiff" in diff_panel
    assert "<DiffToolPanel executions={planExecutions}" in inspector


def test_tauri_titlebar_and_minimum_window_are_real_window_smoke_contracts():
    chrome = _read("web/src/components/WorkspaceChrome.tsx")
    smoke = _read("scripts/smoke_tauri_ui.sh")
    capability = _read("web/src-tauri/capabilities/default.json")
    config = json.loads(_read("web/src-tauri/tauri.conf.json"))
    window = config["app"]["windows"][0]

    assert "data-tauri-drag-region" in chrome
    assert "getCurrentWindow().startDragging()" in chrome
    assert "core:window:allow-start-dragging" in capability
    assert "drag_tauri_titlebar.swift" in smoke
    assert "WINDOW_MIN_WIDTH < 900" in smoke
    assert "WINDOW_MIN_HEIGHT < 600" in smoke
    assert window["minWidth"] == 900
    assert window["minHeight"] == 600
