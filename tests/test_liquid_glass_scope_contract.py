"""PR 4 Liquid Glass scope and CSS split contracts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_css_is_split_into_chrome_and_content_surface_policy():
    main = _read("web/src/main.tsx")

    ordered_imports = (
        'import "./styles/tokens.css";',
        'import "./styles/base.css";',
        'import "./styles/layout.css";',
        'import "./styles/surfaces.css";',
        'import "./styles/plan-execute.css";',
        'import "./styles/overlays.css";',
        'import "./styles/legacy-bridge.css";',
    )
    for import_line in ordered_imports:
        assert import_line in main
    assert [main.index(line) for line in ordered_imports] == sorted(
        main.index(line) for line in ordered_imports
    )
    assert 'import "./styles/chrome.css";' not in main
    assert 'import "./styles/content-surfaces.css";' not in main


def test_backdrop_filter_is_owned_only_by_chrome_policy():
    base = _read("web/src/styles/base.css")
    layout = _read("web/src/styles/layout.css")
    surfaces = _read("web/src/styles/surfaces.css")
    bridge = _read("web/src/styles/legacy-bridge.css")

    assert "backdrop-filter" not in base
    assert "backdrop-filter" not in surfaces
    assert "backdrop-filter" not in bridge
    overlays = _read("web/src/styles/overlays.css")
    assert "backdrop-filter" in overlays
    assert ".titlebar" in base
    for forbidden in (
        ".session-rail::after",
        ".chat-list-pane::after",
        ".context-sidebar::after",
        ".session-list::after",
        ".room-task-bar::after",
        ".mac-bubble::after",
        ".chat-turn::after",
        ".composer-capsule::after",
    ):
        assert forbidden not in layout


def test_lists_documents_and_general_panels_are_solid():
    solid = (
        _read("web/src/styles/surfaces.css")
        + "\n"
        + _read("web/src/styles/legacy-bridge.css")
        + "\n"
        + _read("web/src/styles/layout.css")
        + "\n"
        + _read("web/src/styles/overlays.css")
    )

    for selector in (
        ".session-item",
        ".room-task-bar",
        ".clarifier-banner",
        ".composer-capsule",
        ".exec-queue-bar",
        ".mac-bubble",
        ".chat-turn",
    ):
        assert selector in solid
    non_chrome_solid = (
        _read("web/src/styles/surfaces.css")
        + "\n"
        + _read("web/src/styles/legacy-bridge.css")
    )
    assert "backdrop-filter" not in non_chrome_solid
