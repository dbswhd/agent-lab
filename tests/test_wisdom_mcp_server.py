"""Tests for wisdom MCP server tool surface."""

from __future__ import annotations

from pathlib import Path

import pytest

import agent_lab.wisdom_mcp_server as wm
from agent_lab.wisdom_store import wisdom_load


def test_wisdom_recall_returns_hits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_WISDOM_PATH", str(tmp_path / "wisdom.jsonl"))
    wm.wisdom_record("JWT uses RS256 for authentication", tags="auth,jwt")
    result = wm.wisdom_recall("JWT auth")
    assert result["ok"] is True
    assert result["hit_count"] >= 1
    assert result["hits"][0]["content"] == "JWT uses RS256 for authentication"


def test_wisdom_recall_no_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_WISDOM_PATH", str(tmp_path / "wisdom.jsonl"))
    wm.wisdom_record("PostgreSQL schema details", tags="db")
    result = wm.wisdom_recall("machine learning")
    assert result["ok"] is True
    assert result["hit_count"] == 0
    assert result["hits"] == []


def test_wisdom_record_returns_id_and_tags(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_WISDOM_PATH", str(tmp_path / "wisdom.jsonl"))
    result = wm.wisdom_record("Cache uses LRU strategy", tags="cache,performance", source_ref="src/cache.py:10-30")
    assert result["ok"] is True
    assert result["id"].startswith("w-")
    assert "cache" in result["tags"]
    assert result["source_ref"] == "src/cache.py:10-30"
    entries = wisdom_load(tmp_path / "wisdom.jsonl")
    assert len(entries) == 1


def test_wisdom_list_returns_recent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_WISDOM_PATH", str(tmp_path / "wisdom.jsonl"))
    wm.wisdom_record("Entry A")
    wm.wisdom_record("Entry B")
    result = wm.wisdom_list(limit=5)
    assert result["ok"] is True
    assert result["entry_count"] == 2
    assert result["entries"][0]["content"] == "Entry B"


def test_wisdom_index_status_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_WISDOM_PATH", str(tmp_path / "wisdom.jsonl"))
    result = wm.wisdom_index_status()
    assert result["ok"] is True
    assert "entry_count" in result
    assert "exists" in result
    assert "path" in result


def test_wisdom_recall_k_clamped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_WISDOM_PATH", str(tmp_path / "wisdom.jsonl"))
    for i in range(5):
        wm.wisdom_record(f"pattern about auth variant {i}", tags="auth")
    result = wm.wisdom_recall("auth pattern", k=2)
    assert result["hit_count"] <= 2
