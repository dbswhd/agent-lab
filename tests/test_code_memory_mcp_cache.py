from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.plugin_discovery import discover_plugins, reset_plugin_discovery_cache


def _code_memory_ids(payload: dict[str, object]) -> set[str]:
    plugins = payload["plugins"]
    assert isinstance(plugins, list)
    return {str(row["id"]) for row in plugins if row.get("name") == "agent-lab-code-memory"}


def test_code_memory_flag_toggle_invalidates_discovery_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.delenv("AGENT_LAB_CODE_MEMORY_MCP", raising=False)
    reset_plugin_discovery_cache()

    off_payload = discover_plugins(tmp_path, mock=True)
    monkeypatch.setenv("AGENT_LAB_CODE_MEMORY_MCP", "1")
    on_payload = discover_plugins(tmp_path, mock=True)
    monkeypatch.delenv("AGENT_LAB_CODE_MEMORY_MCP", raising=False)
    off_again_payload = discover_plugins(tmp_path, mock=True)

    assert _code_memory_ids(off_payload) == set()
    assert _code_memory_ids(on_payload) == {
        "claude:mcp:agent-lab-code-memory",
        "codex:mcp:agent-lab-code-memory",
    }
    assert _code_memory_ids(off_again_payload) == set()


def test_code_memory_mode_toggle_uses_distinct_cache_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_CODE_MEMORY_MCP", "1")
    reset_plugin_discovery_cache()

    monkeypatch.setenv("AGENT_LAB_CODE_MEMORY_MODE", "mock")
    mock_payload = discover_plugins(tmp_path, mock=True)
    monkeypatch.setenv("AGENT_LAB_CODE_MEMORY_MODE", "index")
    index_payload = discover_plugins(tmp_path, mock=True)

    assert _code_memory_ids(mock_payload) == {
        "claude:mcp:agent-lab-code-memory",
        "codex:mcp:agent-lab-code-memory",
    }
    assert _code_memory_ids(index_payload) == _code_memory_ids(mock_payload)
    assert mock_payload is not index_payload
