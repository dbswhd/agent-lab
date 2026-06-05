"""PR 4 Liquid Glass scope and CSS split contracts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_css_is_split_into_chrome_and_content_surface_policy():
    main = _read("web/src/main.tsx")

    assert 'import "./styles/chrome.css";' in main
    assert 'import "./styles/content-surfaces.css";' in main
    assert main.index('import "./styles/chrome.css";') < main.index(
        'import "./styles/content-surfaces.css";'
    )


def test_backdrop_filter_is_owned_only_by_chrome_policy():
    app = _read("web/src/styles/app.css")
    macos = _read("web/src/styles/macos26.css")
    chrome = _read("web/src/styles/chrome.css")

    assert "backdrop-filter" not in app
    assert "backdrop-filter" not in macos
    for selector in (
        ".mac-titlebar",
        ".mac-context-menu",
        ".command-palette",
        ".view-options-popover",
    ):
        assert selector in chrome
    for forbidden in (
        ".session-rail::after",
        ".chat-list-pane::after",
        ".inspector-pane",
        ".context-sidebar",
        ".session-row",
        ".session-list",
        ".room-task-bar",
        ".lg-panel",
        ".mac-bubble",
        ".chat-turn",
        ".composer-capsule",
    ):
        assert forbidden not in chrome


def test_lists_documents_and_general_panels_are_solid():
    solid = _read("web/src/styles/content-surfaces.css")

    for selector in (
        ".session-row",
        ".room-task-bar",
        ".clarifier-banner",
        ".human-synthesis-bubble",
        ".execute-queue-bar",
        ".lg-panel",
        ".mac-bubble--received",
        ".chat-turn",
        ".composer-capsule",
    ):
        assert selector in solid
    assert "backdrop-filter" not in solid
