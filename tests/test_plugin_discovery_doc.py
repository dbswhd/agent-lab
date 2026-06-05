"""Phase A: PLUGIN-DISCOVERY.md contract."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "PLUGIN-DISCOVERY.md"


def test_plugin_discovery_doc_exists_and_covers_agents():
    text = DOC.read_text(encoding="utf-8")
    assert "Phase A" in text
    for agent in ("Claude", "Codex", "Cursor"):
        assert agent in text
    for heading in (
        "Pass-through",
        "Phase B",
        "built-in commands",
        "External tools",
    ):
        assert heading.lower() in text.lower()
