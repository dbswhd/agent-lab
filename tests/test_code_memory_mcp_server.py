from __future__ import annotations

import json
from pathlib import Path

from agent_lab import code_memory_mcp_server as cm

HIT_KEYS = {
    "path",
    "start_line",
    "end_line",
    "source_ref",
    "snippet",
    "score",
    "kind",
    "symbol",
    "file_mtime_ns",
    "fresh",
}
STATUS_KEYS = {
    "ok",
    "enabled",
    "mode",
    "root",
    "repo_rev",
    "built_at",
    "index_revision",
    "file_count",
    "chunk_count",
    "fresh",
    "last_error",
}


def _enable(monkeypatch):
    monkeypatch.setenv("AGENT_LAB_CODE_MEMORY_MCP", "1")
    cm._INDEX_CACHE.clear()


def test_mock_search_is_deterministic(tmp_path: Path, monkeypatch):
    _enable(monkeypatch)
    first = cm.code_memory_search_payload(tmp_path, "alpha beta", k=3, mode="mock")
    second = cm.code_memory_search_payload(tmp_path, "alpha beta", k=3, mode="mock")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["hit_count"] == 3
    for hit in first["hits"]:
        assert set(hit) == HIT_KEYS
        assert hit["kind"] == "mock"


def test_search_schema_every_hit_has_source_refs(tmp_path: Path, monkeypatch):
    _enable(monkeypatch)
    result = cm.code_memory_search_payload(tmp_path, "schema refs", k=2, mode="mock")
    assert set(result) == {"ok", "enabled", "mode", "query", "hit_count", "stale_hit_count", "hits", "index"}
    for hit in result["hits"]:
        assert set(hit) == HIT_KEYS
        assert hit["start_line"] <= hit["end_line"]
        assert hit["source_ref"] == f"{hit['path']}:{hit['start_line']}-{hit['end_line']}"
        assert hit["fresh"] is True


def test_index_search_is_deterministic_with_equal_scores(tmp_path: Path, monkeypatch):
    _enable(monkeypatch)
    (tmp_path / "b.py").write_text("needle\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("needle\n", encoding="utf-8")
    (tmp_path / "c.txt").write_text("needle\n", encoding="utf-8")
    first = cm.code_memory_search_payload(tmp_path, "needle", k=10, mode="index")
    second = cm.code_memory_search_payload(tmp_path, "needle", k=10, mode="index")
    assert [hit["source_ref"] for hit in first["hits"]] == [hit["source_ref"] for hit in second["hits"]]
    order_keys = [
        (-hit["score"], hit["path"], hit["start_line"], hit["end_line"], hit["symbol"] is None, hit["symbol"] or "")
        for hit in first["hits"]
    ]
    assert order_keys == sorted(order_keys)


def test_index_search_restats_drops_stale_hits_and_counts_them(tmp_path: Path, monkeypatch):
    _enable(monkeypatch)
    one = tmp_path / "one.py"
    two = tmp_path / "two.py"
    one.write_text("needle one\n", encoding="utf-8")
    two.write_text("needle two\n", encoding="utf-8")
    initial = cm.code_memory_search_payload(tmp_path, "needle", k=10, mode="index")
    assert initial["hit_count"] == 2
    one.write_text("needle one changed with more bytes\n", encoding="utf-8")
    two.unlink()
    stale = cm.code_memory_search_payload(tmp_path, "needle", k=10, mode="index")
    assert stale["hits"] == []
    assert stale["hit_count"] == 0
    assert stale["stale_hit_count"] == 2


def test_status_payload_shape(tmp_path: Path, monkeypatch):
    _enable(monkeypatch)
    (tmp_path / "sample.py").write_text("def thing():\n    return 'needle'\n", encoding="utf-8")
    mock_status = cm.code_memory_status_payload(tmp_path, mode="mock")
    index_status = cm.code_memory_status_payload(tmp_path, mode="index")
    assert set(mock_status) == STATUS_KEYS
    assert set(index_status) == STATUS_KEYS
    assert mock_status["file_count"] == 0
    assert mock_status["chunk_count"] == 0
    assert mock_status["fresh"] is True
    assert index_status["file_count"] == 1
    assert index_status["chunk_count"] >= 1


def test_flag_helpers_default_off(monkeypatch):
    monkeypatch.delenv("AGENT_LAB_CODE_MEMORY_MCP", raising=False)
    monkeypatch.delenv("AGENT_LAB_CODE_MEMORY_MODE", raising=False)
    assert cm.code_memory_mcp_enabled() is False
    assert cm.code_memory_mode() == "mock"
    for value in ("1", "true", "on"):
        monkeypatch.setenv("AGENT_LAB_CODE_MEMORY_MCP", value)
        assert cm.code_memory_mcp_enabled() is True
    monkeypatch.setenv("AGENT_LAB_CODE_MEMORY_MODE", "invalid")
    assert cm.code_memory_mode() == "mock"
    monkeypatch.setenv("AGENT_LAB_CODE_MEMORY_MODE", "")
    assert cm.code_memory_mode() == "mock"
    monkeypatch.setenv("AGENT_LAB_CODE_MEMORY_MODE", "index")
    assert cm.code_memory_mode() == "index"
