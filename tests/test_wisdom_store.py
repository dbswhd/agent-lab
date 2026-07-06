"""Tests for the cross-session Wisdom Index store (no mcp dependency)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.wisdom.store import (
    wisdom_append,
    wisdom_cache_signature,
    wisdom_list_recent,
    wisdom_load,
    wisdom_mcp_enabled,
    wisdom_query,
    wisdom_status,
)


def _path(tmp_path: Path) -> Path:
    return tmp_path / "wisdom.jsonl"


def test_wisdom_mcp_enabled_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_WISDOM_MCP", raising=False)
    assert wisdom_mcp_enabled() is False
    for val in ("1", "true", "yes", "on"):
        monkeypatch.setenv("AGENT_LAB_WISDOM_MCP", val)
        assert wisdom_mcp_enabled() is True
    monkeypatch.setenv("AGENT_LAB_WISDOM_MCP", "0")
    assert wisdom_mcp_enabled() is False


def test_wisdom_cache_signature_changes_on_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_WISDOM_MCP", raising=False)
    sig_off = wisdom_cache_signature()
    monkeypatch.setenv("AGENT_LAB_WISDOM_MCP", "1")
    sig_on = wisdom_cache_signature()
    assert sig_off != sig_on


def test_append_and_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_WISDOM_PATH", str(_path(tmp_path)))
    entry = wisdom_append("JWT uses RS256 in this project", tags=["auth", "jwt"])
    assert entry.id.startswith("w-")
    assert entry.tags == ["auth", "jwt"]
    entries = wisdom_load()
    assert len(entries) == 1
    assert entries[0].content == "JWT uses RS256 in this project"
    assert entries[0].tags == ["auth", "jwt"]


def test_append_multiple(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_WISDOM_PATH", str(_path(tmp_path)))
    wisdom_append("First entry")
    wisdom_append("Second entry")
    wisdom_append("Third entry")
    entries = wisdom_load()
    assert len(entries) == 3
    assert [e.content for e in entries] == ["First entry", "Second entry", "Third entry"]


def test_append_empty_content_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_WISDOM_PATH", str(_path(tmp_path)))
    with pytest.raises(ValueError, match="empty"):
        wisdom_append("   ")


def test_query_basic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _path(tmp_path)
    monkeypatch.setenv("AGENT_LAB_WISDOM_PATH", str(p))
    wisdom_append("Authentication uses JWT tokens", tags=["auth"])
    wisdom_append("Database schema uses PostgreSQL", tags=["db"])
    wisdom_append("Cache invalidation pattern in Redis", tags=["cache"])

    hits = wisdom_query("JWT authentication", path=p)
    assert len(hits) >= 1
    assert hits[0].content == "Authentication uses JWT tokens"


def test_query_no_match_returns_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _path(tmp_path)
    monkeypatch.setenv("AGENT_LAB_WISDOM_PATH", str(p))
    wisdom_append("Some unrelated content", tags=["misc"])
    hits = wisdom_query("quantum computing", path=p)
    assert hits == []


def test_query_tags_also_searched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _path(tmp_path)
    monkeypatch.setenv("AGENT_LAB_WISDOM_PATH", str(p))
    wisdom_append("Important architectural decision", tags=["architecture", "design"])
    wisdom_append("Cache layer details", tags=["cache"])

    hits = wisdom_query("architecture", path=p)
    assert len(hits) == 1
    assert "architecture" in hits[0].tags


def test_query_k_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _path(tmp_path)
    monkeypatch.setenv("AGENT_LAB_WISDOM_PATH", str(p))
    for i in range(10):
        wisdom_append(f"auth pattern variant {i}", tags=["auth"])
    hits = wisdom_query("auth pattern", k=3, path=p)
    assert len(hits) <= 3


def test_list_recent_newest_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _path(tmp_path)
    monkeypatch.setenv("AGENT_LAB_WISDOM_PATH", str(p))
    wisdom_append("Oldest")
    wisdom_append("Middle")
    wisdom_append("Newest")
    recent = wisdom_list_recent(limit=3, path=p)
    assert recent[0].content == "Newest"
    assert recent[-1].content == "Oldest"


def test_list_recent_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _path(tmp_path)
    monkeypatch.setenv("AGENT_LAB_WISDOM_PATH", str(p))
    for i in range(5):
        wisdom_append(f"Entry {i}")
    recent = wisdom_list_recent(limit=2, path=p)
    assert len(recent) == 2


def test_status_no_file(tmp_path: Path) -> None:
    p = tmp_path / "nonexistent.jsonl"
    status = wisdom_status(path=p)
    assert status["ok"] is True
    assert status["entry_count"] == 0
    assert status["exists"] is False
    assert status["newest_at"] is None


def test_status_with_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _path(tmp_path)
    monkeypatch.setenv("AGENT_LAB_WISDOM_PATH", str(p))
    wisdom_append("First")
    status = wisdom_status(path=p)
    assert status["ok"] is True
    assert status["entry_count"] == 1
    assert status["exists"] is True
    assert status["newest_at"] is not None


def test_load_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "empty.jsonl"
    p.write_text("", encoding="utf-8")
    assert wisdom_load(p) == []


def test_load_ignores_corrupt_lines(tmp_path: Path) -> None:
    p = tmp_path / "partial.jsonl"
    p.write_text(
        '{"id":"w-abc","timestamp":"2026-01-01T00:00:00+00:00","content":"Good","tags":[],"session_id":null,"source_ref":null}\nnot-json\n',
        encoding="utf-8",
    )
    entries = wisdom_load(p)
    assert len(entries) == 1
    assert entries[0].content == "Good"
