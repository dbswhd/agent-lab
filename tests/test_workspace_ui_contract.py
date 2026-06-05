"""UI shell contract — developer agent console (PR 5+)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "src"


def _read(*parts: str) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def test_app_uses_workspace_shell_not_primary_messenger_label():
    app = _read("web", "src", "App.tsx")
    assert "workspace-shell" in app
    assert 'aria-label="Sessions"' in app
    assert 'aria-label="Workspace"' in app
    assert '"Sessions"' in app
    assert "SessionRailStatusChip" in app
    assert "AgentHealthPanel" not in app or "healthToAgentOptions" in app


def test_workspace_tab_enum_in_utils():
    tabs = _read("web", "src", "utils", "workspaceTabs.ts")
    for slug in ("transcript", "plan", "review", "run", "artifacts"):
        assert f'"{slug}"' in tabs
    for slug in ("context", "tasks", "run", "settings"):
        assert f'"{slug}"' in tabs


def test_plan_execute_routed_to_review_workspace():
    room = _read("web", "src", "components", "RoomChat.tsx")
    review_idx = room.index('workspaceTab === "review"')
    execute_idx = room.index("PlanExecutePanel", review_idx)
    run_panel_idx = room.index('workspaceTab === "run"')
    assert execute_idx < run_panel_idx
    assert "openReviewTab();" in room
    assert "reviewScrollRef" in room


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

    assert "grid-template-columns: minmax(92px, 112px) minmax(0, 1fr);" in css
    assert "width: var(--composer-cluster-width);" in css
    assert "max-width: 76ch;" in css
    assert ".workspace-transcript-panel .chat-turn__body" in css
    assert "font-size: 14px;" in css
    assert "line-height: 1.7;" in css


def test_transcript_agent_rows_have_visible_bands_and_rails():
    css = _read("web", "src", "styles", "developer-console.css")

    assert "--transcript-role-tint" in css
    assert "border-left: 4px solid var(--transcript-role-color);" in css
    assert ".workspace-transcript-panel .chat-turn__head" in css
    assert "background: var(--transcript-role-tint);" in css
    assert ".workspace-transcript-panel .chat-turn--cursor" in css
    assert ".workspace-transcript-panel .chat-turn--codex" in css
    assert ".workspace-transcript-panel .chat-turn--claude" in css


def test_transcript_has_review_aware_inline_markers():
    bubble = _read("web", "src", "components", "ChatBubble.tsx")
    css = _read("web", "src", "styles", "developer-console.css")

    assert "transcript-marker-strip" in bubble
    assert "getTranscriptMarkers" in bubble
    assert "Review blocker" in bubble
    assert "Plan ref" in bubble
    assert ".transcript-marker-strip" in css
    assert ".transcript-marker" in css


def test_developer_console_doc_is_source_of_truth():
    doc = _read("docs", "developer-agent-console.md")
    assert "Developer Agent Console" in doc or "developer agent console" in doc
    assert "Transcript" in doc
    assert "Review" in doc
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


def test_workspace_review_pending_uses_badge_markup():
    tab_bar = _read("web", "src", "components", "WorkspaceTabBar.tsx")

    assert "workspace-tab-bar__badge" in tab_bar
    assert "workspace-tab-bar__badge-dot" in tab_bar
    assert "Review pending" in tab_bar
    assert "·" not in tab_bar


def test_workspace_panels_have_distinct_document_wrappers():
    room = _read("web", "src", "components", "RoomChat.tsx")
    css = _read("web", "src", "styles", "developer-console.css")

    for class_name in (
        "workspace-panel--plan",
        "workspace-panel--review",
        "workspace-panel--run",
        "workspace-panel--artifacts",
        "workspace-panel--transcript",
        "workspace-document-panel",
        "workspace-document-panel__header",
    ):
        assert class_name in room
        assert f".{class_name}" in css


def test_inspector_sections_are_wrapped_as_cards():
    inspector = _read("web", "src", "components", "InspectorPane.tsx")
    room = _read("web", "src", "components", "RoomChat.tsx")
    css = _read("web", "src", "styles", "workspace-shell.css")

    assert "inspector-pane__body-inner" in inspector
    assert "inspector-pane__section-card" in room
    assert ".inspector-pane__body-inner" in css
    assert ".inspector-pane__section-card" in css


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
