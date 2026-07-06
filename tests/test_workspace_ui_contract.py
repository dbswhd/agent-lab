"""UI shell contract — developer agent console (PR 5+).

Source checks use format-independent tokens (symbol names, class fragments)
rather than full JSX attribute strings so Prettier reflows do not break tests.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "src"


def _read(*parts: str) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def test_app_uses_workspace_shell_not_primary_messenger_label():
    app = _read("web", "src", "App.tsx")
    rail = _read("web", "src", "components", "SessionRail.tsx")
    layout = _read("web", "src", "styles", "layout.css")
    # Canonical shell is `.shell`; legacy `.workspace-shell` rules merged into layout.css.
    assert "className={`shell" in app or " shell--rail-collapsed" in app
    assert ".workspace-shell" in layout or ".shell" in layout
    assert "SessionRail" in app
    assert 'aria-label="Sessions"' in rail
    assert 'aria-label="Workspace"' in app
    assert "Sessions" in app
    assert "SessionRailStatusChip" in app
    assert "AgentHealthPanel" not in app or "healthToAgentOptions" in app


@pytest.mark.integration
def test_agent_health_panel_shows_model_readiness_lane():
    client = _read("web", "src", "api", "client.ts")
    panel = _read("web", "src", "components", "AgentHealthPanel.tsx")
    room_modes = _read("web", "src", "utils", "roomModes.ts")
    presets = _read("web", "src", "utils", "roomPresets.ts")
    composer = _read("web", "src", "components", "ChatComposer.tsx")

    assert "team_ready?: boolean" in client
    assert "loop_ready?: boolean" in client
    assert "model_id?: string" in client
    assert 'model_cost_tier?: "low" | "medium" | "high"' in client
    assert "loop_cost_blocked?: boolean" in client
    assert "fetchRoomModes" in room_modes
    assert "loopCostHintLine" in room_modes
    assert "resolveRoomPresets" in presets
    assert "composer-preset-seg" in composer
    assert "model_provider?: string" in client
    assert "loop_ready" in panel
    assert "재연결" in panel
    assert "team-health" in panel


def test_workspace_tabs_stay_on_transcript_while_running():
    tabs = _read("web", "src", "utils", "workspaceTabs.ts")
    assert 'if (ctx.running) return "run"' not in tabs


def test_app_guards_room_bound_session_before_sidebar_list():
    app = _read("web", "src", "App.tsx")
    assert "roomBoundSessionRef" in app
    assert "roomBoundSessionRef.current === selectedId" in app


def test_use_workspace_tabs_pins_transcript_on_session_bind():
    hook = _read("web", "src", "hooks", "useWorkspaceTabs.ts")
    assert "boundFromComposer" in hook
    first_effect = hook.split("useEffect(() => {", 1)[1].split("}, [", 1)[1].split("]);", 1)[0]
    assert "running" not in first_effect


def test_workspace_tab_enum_in_utils():
    tabs = _read("web", "src", "utils", "workspaceTabs.ts")
    for slug in ("transcript", "diff", "files", "background"):
        assert f'"{slug}"' in tabs
    for slug in ("overview", "tools"):
        assert f'"{slug}"' in tabs
    assert 'id: "plan"' not in tabs
    assert '"tasks"' not in tabs
    assert 'id: "inbox"' not in tabs


def test_plan_execute_routed_to_composer_event_stack():
    room = _read("web", "src", "components", "RoomChat.tsx")
    hook = _read("web", "src", "hooks", "useWorkspaceTabs.ts")
    stack = _read("web", "src", "components", "ComposerEventStack.tsx")
    work_tool = _read("web", "src", "components", "WorkToolPanel.tsx")
    composer_shell = _read("web", "src", "components", "RoomChatComposerShell.tsx")
    assert "useRoomChat" in room
    assert "ComposerEventStack" in composer_shell
    assert "PlanExecutePanel" in work_tool
    assert "focusComposerStack" in hook
    assert "ExecuteQueueBar" in stack
    assert "reviewScrollRef" not in room


def test_transcript_uses_console_presentation():
    transcript = _read("web", "src", "components", "RoomTranscriptPanel.tsx")
    assert 'presentation="console"' in transcript
    bubble = _read("web", "src", "components", "ChatBubble.tsx")
    assert 'presentation?: "console" | "messenger"' in bubble


def test_transcript_agent_rows_use_role_cards_with_initial_avatars():
    bubble = _read("web", "src", "components", "ChatBubble.tsx")
    chrome = _read("web", "src", "components", "TranscriptMessageChrome.tsx")
    markers = _read("web", "src", "utils", "transcriptMessageMarkers.ts")

    assert "TranscriptIdentity" in bubble
    assert "TranscriptAuthorLine" in bubble
    assert "transcript-identity" in chrome
    assert "transcriptInitial" in markers
    assert "transcript-author-line" in chrome


def test_human_transcript_message_is_right_aligned_without_label_chrome():
    bubble = _read("web", "src", "components", "ChatBubble.tsx")
    transcript = _read("web", "src", "components", "RoomTranscriptPanel.tsx")
    css = _read("web", "src", "styles", "surfaces.css")

    assert "chat-turn__head" in bubble
    assert 'message={{ ...message, label: message.label ?? "Human" }}' not in bubble
    assert "transcript transcript--console" in transcript
    assert "bubble-row bubble-row--sent" in bubble
    assert ".transcript--console .bubble-row--sent" in css
    assert "margin-left: auto;" in css


def test_agent_waiting_state_shows_activity_log_and_dots():
    bubble = _read("web", "src", "components", "ChatBubble.tsx")
    css = _read("web", "src", "styles", "surfaces.css")
    layout = _read("web", "src", "styles", "layout.css")
    sse = _read("web", "src", "hooks", "useRoomSseHandler.ts")

    # Activity log was refactored from an inline `agent-activity-log` list into <TurnActivityGroup>.
    assert "TurnActivityGroup" in bubble
    assert ".turn-activity" in layout
    assert "agent-stream-preview" in bubble
    assert "typing" in bubble
    assert ".typing span" in css
    assert ".agent-stream-preview" in layout
    assert 't === "agent_token"' in sse


def test_transcript_has_review_aware_inline_markers():
    bubble = _read("web", "src", "components", "ChatBubble.tsx")
    chrome = _read("web", "src", "components", "TranscriptMessageChrome.tsx")
    markers = _read("web", "src", "utils", "transcriptMessageMarkers.ts")
    css = _read("web", "src", "styles", "layout.css")

    assert "TranscriptMarkerStrip" in bubble
    assert "transcript-marker-strip" in chrome
    assert "getTranscriptMarkers" in markers
    assert "Review blocker" in markers
    assert "Plan ref" in markers
    assert ".transcript-marker-strip" in css
    assert ".transcript-marker" in css


def test_developer_console_doc_is_source_of_truth():
    doc = _read("docs", "developer-agent-console.md")
    assert "Human-in-the-loop Agent Development Console" in doc
    assert "Transcript" in doc
    deprecated = _read("docs", "archive", "legacy", "02-ui-ux-handoff.md")
    lowered = deprecated.lower()
    assert "deprecated" in lowered or "legacy" in lowered


def test_workspace_tabs_do_not_render_inline_status_badges():
    room = _read("web", "src", "components", "RoomChat.tsx")

    assert "suggestedTab=" not in room
    assert "reviewPending=" not in room


def test_workspace_panels_have_distinct_document_wrappers():
    _read("web", "src", "components", "RoomChat.tsx")
    inspector = _read("web", "src", "components", "RoomChatInspector.tsx")
    surfaces = _read("web", "src", "styles", "surfaces.css")
    work_tool = _read("web", "src", "components", "WorkToolPanel.tsx")
    assert "work-surface" in work_tool or "work-stack" in work_tool
    status = _read("web", "src", "utils", "workStatusPhase.ts")
    status_bar = _read("web", "src", "components", "WorkStatusBar.tsx")
    assert "resolveWorkPhaseFromMission" in status
    assert "missionPaused" in status_bar
    assert "work-status-bar__pause-badge" in status_bar
    assert "work-mission-overview" in _read("web", "src", "components", "MissionOverviewSection.tsx")
    plugin = _read("web", "src", "components", "PluginPanel.tsx")
    assert "cursor-ide-mcp-hint" in plugin
    plan_exec = _read("web", "src", "components", "PlanExecutePanel.tsx")

    transcript = _read("web", "src", "components", "RoomTranscriptPanel.tsx")

    assert "transcript--console" in transcript
    assert "WorkbenchPanel" in inspector
    assert "ComposerEventStack" in _read("web", "src", "components", "RoomChatComposerShell.tsx")
    assert "plan-card" in plan_exec
    assert "exec-card" in plan_exec
    assert "plan-actions-bar" in plan_exec
    assert "PlanExecutePanel" in work_tool
    assert ".transcript--console" in surfaces


def test_inspector_matches_prototype_context_sidebar_body():
    room = _read("web", "src", "components", "RoomChat.tsx")
    inspector = _read("web", "src", "components", "RoomChatInspector.tsx")
    overview = _read("web", "src", "components", "ContextOverviewPanel.tsx")
    layout = _read("web", "src", "styles", "layout.css")

    assert "ContextOverviewPanel" in inspector
    assert "MissionOverviewSection" in overview
    assert "inspector-pane__section-card" not in room
    assert ".ctx-section" in layout
    assert ".context-sidebar__head" in layout


def test_phase0_composer_plan_toggle_removed():
    composer = _read("web", "src", "components", "ChatComposer.tsx")
    room = _read("web", "src", "components", "RoomChat.tsx")
    prefs = _read("web", "src", "hooks", "useRoomComposerPrefs.ts")
    assert "ComposerPlanToggle" not in composer
    assert "onPlanAfterSendChange" not in room
    assert "planComposeActive" not in prefs
    assert "planComposeActive" not in room
    assert 'composeMode: ComposeMode = "discuss"' in prefs
    assert "ComposerEfficiencyToggle" not in composer
    assert "efficiencyOn" not in room


def test_phase0_session_rail_status_detail_is_distinct():
    chip = _read("web", "src", "components", "SessionRailStatusChip.tsx")
    css = _read("web", "src", "styles", "layout.css")
    assert "rail-status__panel" in chip
    assert ".rail-status__panel" in css


def test_phase0_no_full_team_cost_confirm():
    composer = _read("web", "src", "components", "ChatComposer.tsx")
    room = _read("web", "src", "components", "RoomChat.tsx")
    assert "fullTeamConfirm" not in composer
    assert "fullTeamConfirm" not in room
    assert "cost-confirm" not in composer
    surfaces = _read("web", "src", "styles", "surfaces.css")
    assert ".cost-confirm" not in surfaces


def test_run_session_registry_module_exists():
    reg = _read("web", "src", "run", "runSessionRegistry.ts")
    assert "SessionRunSnapshot" in reg
    assert "turnMessages" in reg
    assert "subscribeSessionRun" in reg
    assert "hydrateSessionMessages" in reg


def test_room_patches_turn_messages():
    sse = _read("web", "src", "hooks", "useRoomSseHandler.ts")
    execute_send = _read("web", "src", "hooks", "useRoomExecuteSend.ts")
    assert "patchTurnMessages" in sse
    assert "createRoomRunEventHandler" in execute_send


def test_m3_terminal_uses_xterm():
    terminal = _read("web", "src", "components", "TerminalPanel.tsx")
    layout = _read("web", "src", "styles", "layout.css")
    assert "@xterm/xterm" in terminal
    assert "FitAddon" in terminal
    assert "terminal-panel__xterm" in terminal
    assert ".terminal-panel__xterm" in layout


def test_m3_preview_auto_probe_and_presets():
    preview = _read("web", "src", "components", "PreviewPanel.tsx")
    assert "probePreviewPort" in preview
    assert "getPreviewPresets" in preview
    assert "preview-panel__presets" in preview


def test_m3_files_monaco_editor_lazy():
    files = _read("web", "src", "components", "WorkspaceFilesPanel.tsx")
    monaco = _read("web", "src", "components", "FilesMonacoEditor.tsx")
    prefs = _read("web", "src", "utils", "filesRootPrefs.ts")
    layout = _read("web", "src", "styles", "layout.css")
    assert "FilesMonacoEditor" in files
    assert "lazy(" in files
    assert "@monaco-editor/react" in monaco
    assert "FilesRootsEditor" in files
    assert "getVisibleRootIds" in prefs
    assert "--files-explorer-size" in layout
    assert "--files-viewer-content-size" in layout
    assert "files-roots-edit" in layout


def test_m3_side_by_side_diff_in_execute_panel():
    plan = _read("web", "src", "components", "PlanExecutePanel.tsx")
    diff = _read("web", "src", "components", "SideBySideDiff.tsx")
    util = _read("web", "src", "utils", "sideBySideDiff.ts")
    css = _read("web", "src", "styles", "plan-execute.css")
    assert "SideBySideDiff" in plan
    assert "activeHunkId" in diff
    assert "parseSideBySideDiff" in util
    assert "exec-diff--split" in css


def test_m4_diagnostics_show_bridge_audit():
    diag = _read("web", "src", "components", "ApiDiagnosticsBar.tsx")
    assert "bridge_audit" in diag
    assert "auth_bootstrap_line" in diag
    assert "diag-bar__bridge" in diag


def test_m5_i18n_panels_use_locale():
    bgtask = _read("web", "src", "components", "BackgroundTasksPanel.tsx")
    terminal = _read("web", "src", "components", "TerminalPanel.tsx")
    live = _read("web", "src", "components", "LiveAgentsStrip.tsx")
    main_pane = _read("web", "src", "components", "RoomChatMainPane.tsx")
    transcript = _read("web", "src", "components", "RoomTranscriptPanel.tsx")
    plan_refs = _read("web", "src", "utils", "PlanDocRefs.tsx")
    layout = _read("web", "src", "styles", "layout.css")

    assert "useLocale" in bgtask
    assert "msg.bgtaskTitle" in bgtask
    assert "msg.terminalHint" in terminal
    assert "msg.liveAgentsResponding" in live
    assert "RoomTranscriptPanel" in main_pane
    assert "TranscriptActivityDivider" in transcript
    assert "msg.planRefGoToChat" in plan_refs
    assert ".plan-doc__ref--link" in layout


def test_m5_console_presentation_is_default():
    bubble = _read("web", "src", "components", "ChatBubble.tsx")
    synth = _read("web", "src", "components", "HumanSynthesisBubble.tsx")
    assert 'presentation = "console"' in bubble
    assert 'presentation = "console"' in synth


def test_session_list_shows_running_indicator():
    list_tsx = _read("web", "src", "components", "SessionList.tsx")
    app = _read("web", "src", "App.tsx")
    assert "runningSessionIds" in list_tsx
    assert "session-item--running" in list_tsx
    assert "rail-type-session-size" in _read("web", "src", "styles", "tokens.css")
    assert "var(--rail-type-session-size)" in _read("web", "src", "styles", "layout.css")
    assert "ctx-menu--session" in _read("web", "src", "components", "SessionContextMenu.tsx")
    assert "ctx-menu__sep--section" in _read("web", "src", "styles", "overlays.css")
    assert "groupSessionsForList" in list_tsx
    assert "draggable={dragEnabled}" in list_tsx
    assert "session-item--draggable" in list_tsx
    assert "SessionContextMenu" in list_tsx
    assert "useRunningSessionIds" in app


def test_m6_taskbar_canonical_classes_only():
    taskbar = _read("web", "src", "components", "RoomTaskBar.tsx")
    layout = _read("web", "src", "styles", "layout.css")
    assert "room-task-bar__" not in taskbar
    assert ".taskbar__turn-leads-history" in layout
    assert "legacy `.room-task-bar__*` block removed" in layout


def test_m6_plan_card_canonical_classes_only():
    panel = _read("web", "src", "components", "PlanExecutePanel.tsx")
    plan_css = _read("web", "src", "styles", "plan-execute.css")
    assert "plan-execute-panel__" not in panel
    assert "plan-execute-" not in panel
    assert "work-exec-" in panel
    assert "work-surface" in panel
    assert ".plan-card__muted" in plan_css


def test_m6_chat_turn_no_dual_class_root():
    bubble = _read("web", "src", "components", "ChatBubble.tsx")
    assert "`turn chat-turn" not in bubble
    assert "className={`chat-turn chat-turn--${role}" in bubble or "chat-turn--${role}" in bubble
    assert "chat-turn__head" in bubble


def test_m6_room_chat_canonical_shell_only():
    room = _read("web", "src", "components", "RoomChat.tsx")
    main_pane = _read("web", "src", "components", "RoomChatMainPane.tsx")
    transcript = _read("web", "src", "components", "RoomTranscriptPanel.tsx")
    layout = _read("web", "src", "styles", "layout.css")
    assert "room-workspace-shell" not in room
    assert "view-options-btn" not in room
    assert "view-options-popover" not in room
    assert "pane-row" in room
    assert "pane-main" in room
    assert "workspace-main" in room
    assert "RoomTranscriptPanel" in main_pane
    assert "TranscriptViewOptions" in transcript
    assert "transcript-view-options" in _read("web", "src", "components", "TranscriptViewOptions.tsx")
    assert "legacy `.room-workspace-shell`" in layout


def test_claude_stream_bridge_in_cli():
    cli = _read("src", "agent_lab", "claude", "cli.py")
    parser = _read("src", "agent_lab", "agent", "stream_parser.py")
    assert "_run_claude_stream" in cli
    assert "parse_claude_json_event" in parser
    assert "stream-json" in cli


def test_settings_page_and_work_ia_docs():
    doc = _read("docs", "archive", "legacy", "WORK-TAB-IA.md")
    assert "Work" in doc
    assert "SettingsPage" in _read("web", "src", "components", "SettingsPage.tsx")


def test_developer_console_blur_is_limited_to_titlebar_and_popovers():
    overlays = _read("web", "src", "styles", "overlays.css")
    layout = _read("web", "src", "styles", "layout.css")

    assert "backdrop-filter" in overlays
    assert ".cmd-palette-backdrop" in overlays or ".cmd-palette" in overlays
    assert ".ctx-menu" in overlays or ".ctx-menu" in layout

    assert ".session-rail::after" not in layout
    assert ".chat-list-pane::after" not in layout
    assert ".context-sidebar::after" not in layout
