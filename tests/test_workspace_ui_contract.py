"""UI shell contract — developer agent console (PR 5+)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "src"


def _read(*parts: str) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def test_app_uses_workspace_shell_not_primary_messenger_label():
    app = _read("web", "src", "App.tsx")
    rail = _read("web", "src", "components", "SessionRail.tsx")
    assert "workspace-shell" in app
    assert "SessionRail" in app
    assert 'aria-label="Sessions"' in rail
    assert 'aria-label="Workspace"' in app
    assert '"Sessions"' in app
    assert "SessionRailStatusChip" in app
    assert "AgentHealthPanel" not in app or "healthToAgentOptions" in app


def test_workspace_tab_enum_in_utils():
    tabs = _read("web", "src", "utils", "workspaceTabs.ts")
    for slug in ("transcript", "work", "run", "artifacts"):
        assert f'"{slug}"' in tabs
    for slug in ("tasks", "activity", "quick"):
        assert f'"{slug}"' in tabs


def test_plan_execute_routed_to_work_workspace():
    room = _read("web", "src", "components", "RoomChat.tsx")
    assert 'workspaceTab === "work"' in room
    assert "WorkPanel" in room
    assert "PlanExecutePanel" in _read("web", "src", "components", "WorkPanel.tsx")
    assert "openWorkTab();" not in room or "openWorkTab" in room
    assert "reviewScrollRef" not in room


def test_transcript_uses_console_presentation():
    room = _read("web", "src", "components", "RoomChat.tsx")
    assert 'presentation="console"' in room
    bubble = _read("web", "src", "components", "ChatBubble.tsx")
    assert 'presentation?: "console" | "messenger"' in bubble
    css = _read("web", "src", "styles", "developer-console.css")
    assert ".workspace-transcript-panel .chat-turn" in css
    assert "--console-bg" in css


def test_transcript_is_readable_document_stream_not_cards():
    css = _read("web", "src", "styles", "developer-console.css")

    assert "width: var(--composer-cluster-width);" in css
    assert "max-width: calc(100% - 2 * var(--composer-pad-x));" in css
    assert "margin-left: auto;" in css
    assert "margin-right: auto;" in css
    assert "/* Workspace content surfaces — inspector-like, not floating cards */" in css
    assert "max-width: 76ch;" in css
    assert ".workspace-transcript-panel .chat-turn__body" in css
    assert "font-size: 14px;" in css
    assert "line-height: 1.7;" in css


def test_transcript_agent_rows_use_role_cards_with_initial_avatars():
    css = _read("web", "src", "styles", "developer-console.css")
    bubble = _read("web", "src", "components", "ChatBubble.tsx")
    chrome = _read("web", "src", "components", "TranscriptMessageChrome.tsx")

    assert "--transcript-role-tint" in css
    assert "border-left: 4px solid var(--transcript-role-color);" in css
    assert ".workspace-transcript-panel .chat-turn__head" in css
    assert "background: var(--transcript-role-tint);" in css
    assert "TranscriptIdentity" in bubble
    assert "TranscriptAuthorLine" in bubble
    assert "transcript-identity" in chrome
    assert "transcriptInitial" in chrome
    assert "transcript-author-line" in chrome
    assert "grid-template-columns:" in css
    assert ".workspace-transcript-panel .chat-turn--cursor" in css
    assert ".workspace-transcript-panel .chat-turn--codex" in css
    assert ".workspace-transcript-panel .chat-turn--claude" in css


def test_human_transcript_message_is_right_aligned_without_label_chrome():
    bubble = _read("web", "src", "components", "ChatBubble.tsx")
    room = _read("web", "src", "components", "RoomChat.tsx")
    css = _read("web", "src", "styles", "developer-console.css")

    assert 'className="chat-turn__head"' in bubble
    assert "message={{ ...message, label: message.label ?? \"Human\" }}" not in bubble
    assert 'm.role === "you" || m.sent ? "chat-line--you" : undefined' in room
    assert (
        ".workspace-panel--transcript .workspace-transcript-panel > "
        ".chat-line--you > .chat-turn"
    ) in css
    assert "max-width: 80%;" in css
    assert "background: var(--console-human);" in css
    assert "border-right: none;" in css
    assert ".workspace-transcript-panel .chat-turn--you .transcript-author-line" in css
    assert "display: none;" in css


def test_agent_waiting_state_shows_activity_log_and_dots():
    bubble = _read("web", "src", "components", "ChatBubble.tsx")
    css = _read("web", "src", "styles", "developer-console.css")

    assert "agent-activity-log" in bubble
    assert "TypingIndicator variant=\"stream\"" in bubble
    assert ".workspace-transcript-panel .chat-turn--waiting" in css
    assert ".workspace-transcript-panel .agent-activity-log" in css
    assert ".workspace-transcript-panel .typing-dots--stream" in css


def test_transcript_has_review_aware_inline_markers():
    bubble = _read("web", "src", "components", "ChatBubble.tsx")
    chrome = _read("web", "src", "components", "TranscriptMessageChrome.tsx")
    css = _read("web", "src", "styles", "developer-console.css")

    assert "TranscriptMarkerStrip" in bubble
    assert "transcript-marker-strip" in chrome
    assert "getTranscriptMarkers" in chrome
    assert "Review blocker" in chrome
    assert "Plan ref" in chrome
    assert ".transcript-marker-strip" in css
    assert ".transcript-marker" in css


def test_developer_console_doc_is_source_of_truth():
    doc = _read("docs", "developer-agent-console.md")
    assert "Developer Agent Console" in doc or "developer agent console" in doc
    assert "Transcript" in doc
    deprecated = _read("docs", "02-ui-ux-handoff.md")
    assert "DEPRECATED" in deprecated


def test_workspace_visual_hierarchy_tokens_are_defined():
    css = _read("web", "src", "styles", "developer-console.css")

    for token in (
        "--console-canvas",
        "--console-panel",
        "--console-panel-elevated",
        "--console-border-strong",
        "--console-active",
        "--console-review",
        "--console-review-bg",
        "--console-run",
        "--console-shadow-soft",
    ):
        assert token in css

    assert "--surface-base: var(--console-canvas);" in css
    assert "--surface-raised: var(--console-panel);" in css
    assert "--surface-overlay: var(--console-panel-elevated);" in css


def test_workspace_tabs_do_not_render_inline_status_badges():
    tab_bar = _read("web", "src", "components", "WorkspaceTabBar.tsx")
    room = _read("web", "src", "components", "RoomChat.tsx")

    assert "workspace-tab-bar__badge" not in tab_bar
    assert "workspace-tab-bar__badge-dot" not in tab_bar
    assert "Work pending" not in tab_bar
    assert "Review pending" not in tab_bar
    assert "suggestedTab=" not in room
    assert "reviewPending=" not in room


def test_workspace_panels_have_distinct_document_wrappers():
    room = _read("web", "src", "components", "RoomChat.tsx")
    css = _read("web", "src", "styles", "developer-console.css")

    for class_name in (
        "workspace-panel--work",
        "workspace-panel--run",
        "workspace-panel--artifacts",
        "workspace-panel--transcript",
        "workspace-document-panel",
        "workspace-document-panel__header",
    ):
        assert class_name in room or class_name in _read(
            "web", "src", "components", "WorkPanel.tsx"
        )
        assert f".{class_name}" in css or class_name in _read(
            "web", "src", "components", "WorkPanel.tsx"
        )


def test_workspace_content_panels_use_full_inset_surface_not_small_cards():
    css = _read("web", "src", "styles", "developer-console.css")
    normalized_css = " ".join(css.split())

    for selector in (
        ".messages-scroll.workspace-panel--transcript > .workspace-transcript-panel",
        ".messages-scroll.workspace-panel--work > .work-panel",
        ".messages-scroll.workspace-panel--run > .workspace-document-panel",
        ".messages-scroll.workspace-panel--artifacts > .workspace-document-panel",
    ):
        assert selector in normalized_css

    full_surface_block = css.split(
        "/* Workspace content surfaces — inspector-like, not floating cards */"
    )[1].split("/* Work / Artifacts — composer-aligned column on full-width inset surface */")[0]
    assert (
        ".messages-scroll.workspace-panel--transcript\n  > .workspace-transcript-panel"
        in css
    )
    assert (
        ".messages-scroll.workspace-panel--run\n  > .workspace-document-panel"
        in css
    )
    for declaration in (
        "width: 100%;",
        "max-width: none;",
        "margin: 0;",
        "border: none;",
        "border-radius: 0;",
        "background: transparent;",
        "box-shadow: none;",
    ):
        assert declaration in full_surface_block

    cluster_block = css.split(
        "/* Work / Artifacts — composer-aligned column on full-width inset surface */"
    )[1].split("/* Workspace content inner cards */")[0]
    normalized_cluster = " ".join(cluster_block.split())
    for selector in (
        ".messages-scroll.workspace-panel--work > .work-panel",
        ".messages-scroll.workspace-panel--work > .workspace-empty-state",
        ".messages-scroll.workspace-panel--artifacts > .workspace-document-panel",
    ):
        assert selector in normalized_cluster
    for declaration in (
        "width: var(--composer-cluster-width);",
        "max-width: calc(100% - 2 * var(--composer-pad-x));",
        "margin-left: auto;",
        "margin-right: auto;",
        "background: transparent;",
        "box-shadow: none;",
    ):
        assert declaration in cluster_block

    composer_fade_block = css.split(
        ".mac-app.mac-app--developer-console .chat-pane-body > .composer::before"
    )[1].split("}")[0]
    assert "backdrop-filter: none;" in composer_fade_block
    assert "var(--console-bg-inset)" in composer_fade_block


def test_workspace_tab_bar_blends_with_console_surface_not_segmented_card():
    css = _read("web", "src", "styles", "developer-console.css")

    assert "/* Workspace tab rail — flat console navigation */" in css

    tab_bar_block = css.split(
        "/* Workspace tab rail — flat console navigation */"
    )[1].split("/* Workspace content surfaces — inspector-like, not floating cards */")[0]
    for declaration in (
        "background: var(--console-panel);",
        "border-bottom: 0.5px solid var(--console-border-strong);",
        "box-shadow: none;",
    ):
        assert declaration in tab_bar_block

    assert ".workspace-tab-bar__seg.mac-segmented" in tab_bar_block
    assert "background: transparent;" in tab_bar_block
    assert "border: none;" in tab_bar_block
    assert ".workspace-tab-bar__seg button.active" in tab_bar_block
    assert "var(--mac-content-bg)" not in tab_bar_block


def test_inspector_sections_are_wrapped_as_cards():
    inspector = _read("web", "src", "components", "InspectorPane.tsx")
    room = _read("web", "src", "components", "RoomChat.tsx")
    css = _read("web", "src", "styles", "workspace-shell.css")

    assert "inspector-pane__body-inner" in inspector
    assert "inspector-pane__section-card" in room
    assert ".inspector-pane__body-inner" in css
    assert ".inspector-pane__section-card" in css


def test_phase0_efficiency_toggle_uses_efficient_class():
    room = _read("web", "src", "components", "RoomChat.tsx")
    assert 'efficiencyOn ? "composer--efficient"' in room
    assert "composer--efficiency" not in room


def test_phase0_session_rail_status_detail_is_distinct():
    chip = _read("web", "src", "components", "SessionRailStatusChip.tsx")
    css = _read("web", "src", "styles", "workspace-shell.css")
    assert "session-rail-status__detail-heading" in chip
    assert ".session-rail-status__detail-heading" in css
    assert "box-shadow:" in css.split(".session-rail-status__detail {")[1].split("}")[0]


def test_phase0_full_team_confirm_has_no_detail_line():
    room = _read("web", "src", "components", "RoomChat.tsx")
    assert "풀 팀 실행은 이번 턴에만 확인합니다." not in room


def test_run_session_registry_module_exists():
    reg = _read("web", "src", "run", "runSessionRegistry.ts")
    assert "SessionRunSnapshot" in reg
    assert "turnMessages" in reg
    assert "subscribeSessionRun" in reg
    assert "hydrateSessionMessages" in reg


def test_turn_run_panel_renders_turn_messages():
    panel = _read("web", "src", "components", "TurnRunPanel.tsx")
    room = _read("web", "src", "components", "RoomChat.tsx")
    assert "turnMessages" in panel
    assert "TurnRunPanel" in room
    assert "turnMessages={turnMessages}" in room


def test_session_list_shows_running_indicator():
    list_tsx = _read("web", "src", "components", "SessionList.tsx")
    app = _read("web", "src", "App.tsx")
    assert "runningSessionIds" in list_tsx
    assert "session-row__run-dot" in list_tsx
    assert "useRunningSessionIds" in app


def test_settings_page_and_work_ia_docs():
    doc = _read("docs", "WORK-TAB-IA.md")
    assert "Work" in doc
    assert "SettingsPage" in _read("web", "src", "components", "SettingsPage.tsx")


def test_developer_console_blur_is_limited_to_titlebar_and_popovers():
    chrome = _read("web", "src", "styles", "chrome.css")

    assert ".mac-titlebar" in chrome
    assert ".mac-context-menu" in chrome
    assert ".command-palette" in chrome
    assert ".view-options-popover" in chrome

    assert ".session-rail::after" not in chrome
    assert ".chat-list-pane::after" not in chrome
    assert ".inspector-pane" not in chrome
    assert ".context-sidebar" not in chrome
