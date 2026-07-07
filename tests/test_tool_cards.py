"""S3a-0 — local capability inventory unit tests (mock-only, isolated from real skills).

docs/N10-USER-LOOP-WISDOM-DRAFT.md §2 (S3a-0).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.tool_cards import (
    _tag_categories,
    build_tool_cards,
    tool_card_note,
    unused_tool_cards_for_category,
)

_FAKE_PLUGINS = [
    {
        "id": "claude:skill:impeccable",
        "name": "impeccable",
        "agent": "claude",
        "kind": "skill",
        "description": "UI polish, animation, design review",
        "enabled_default": True,
    },
    {
        "id": "claude:skill:test-driven-development",
        "name": "test-driven-development",
        "agent": "claude",
        "kind": "skill",
        "description": "Write tests before implementation, debug failures",
        "enabled_default": True,
    },
    {
        "id": "codex:mcp:context7",
        "name": "context7",
        "agent": "codex",
        "kind": "mcp",
        "description": "Library documentation lookup",
        "enabled_default": True,
    },
]


@pytest.fixture(autouse=True)
def _fake_discovery(monkeypatch: pytest.MonkeyPatch):
    def _fake_discover_plugins(workspace: Path, *, mock: bool | None = None) -> dict:
        return {"workspace": str(workspace), "mock": True, "plugins": list(_FAKE_PLUGINS)}

    monkeypatch.setattr("agent_lab.plugin_discovery.discover_plugins", _fake_discover_plugins)


def test_tag_categories_always_includes_standard():
    assert "standard" in _tag_categories("some-tool", "does something generic")


def test_tag_categories_tags_design_as_deep():
    tags = _tag_categories("impeccable", "UI polish, animation, design review")
    assert "deep" in tags


def test_tag_categories_tags_test_as_critical():
    tags = _tag_categories("test-driven-development", "Write tests before implementation, debug failures")
    assert "critical" in tags


def test_build_tool_cards_wraps_discovery(tmp_path):
    cards = build_tool_cards(tmp_path)
    assert len(cards) == 3
    by_id = {c["id"]: c for c in cards}
    assert "deep" in by_id["claude:skill:impeccable"]["categories"]
    assert "standard" in by_id["claude:skill:impeccable"]["categories"]


def test_unused_tool_cards_excludes_allowlisted(tmp_path):
    run_meta = {"agent_plugins": {"claude": {"enabled": ["claude:skill:impeccable"]}}}
    unused = unused_tool_cards_for_category("deep", run_meta, tmp_path)
    ids = {c["id"] for c in unused}
    assert "claude:skill:impeccable" not in ids  # already allowlisted


def test_unused_tool_cards_filters_by_category(tmp_path):
    unused = unused_tool_cards_for_category("critical", {}, tmp_path)
    ids = {c["id"] for c in unused}
    assert "claude:skill:test-driven-development" in ids
    assert "codex:mcp:context7" not in ids  # context7 has no "critical" keyword hit


def test_unused_tool_cards_empty_when_wildcard_allowed(tmp_path):
    run_meta = {"agent_plugins": {"claude": {"enabled": ["*"]}}}
    unused = unused_tool_cards_for_category("deep", run_meta, tmp_path)
    assert unused == []


def test_tool_card_note_returns_names_and_ids(tmp_path):
    note, ids = tool_card_note("deep", {}, tmp_path)
    assert "impeccable" in note
    assert "claude:skill:impeccable" in ids


def test_tool_card_note_empty_for_unmatched_category(tmp_path):
    note, ids = tool_card_note("trading", {}, tmp_path)
    assert note == ""
    assert ids == ()


def test_tool_card_note_respects_limit(tmp_path):
    note, ids = tool_card_note("standard", {}, tmp_path, limit=1)
    assert len(ids) == 1
