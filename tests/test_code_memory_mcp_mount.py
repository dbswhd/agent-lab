from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.mcp_spec_export import build_claude_mcp_overlay, codex_mcp_stdio_config_args
from agent_lab.plugin_discovery import discover_plugins, reset_plugin_discovery_cache


def _only_code_memory_run() -> dict[str, object]:
    return {
        "agent_plugins": {
            "claude": {"enabled": ["claude:mcp:agent-lab-code-memory"]},
            "codex": {"enabled": ["codex:mcp:agent-lab-code-memory"]},
            "cursor": {"enabled": []},
        }
    }


def test_code_memory_discovery_rows_without_cursor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_CODE_MEMORY_MCP", "1")
    reset_plugin_discovery_cache()

    plugins = discover_plugins(tmp_path, mock=True)["plugins"]
    rows = [row for row in plugins if row.get("name") == "agent-lab-code-memory"]

    assert {row["id"] for row in rows} == {
        "claude:mcp:agent-lab-code-memory",
        "codex:mcp:agent-lab-code-memory",
    }
    assert {row["agent"] for row in rows} == {"claude", "codex"}
    assert all(row["kind"] == "mcp" for row in rows)
    assert all(row["status"] == "enabled" for row in rows)
    assert not any(row.get("agent") == "cursor" for row in rows)


def test_claude_overlay_uses_builtin_stdio_without_native_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_CODE_MEMORY_MCP", "1")
    reset_plugin_discovery_cache()

    def _native_fetch_called(_name: str) -> dict[str, object] | None:
        raise AssertionError("native Claude MCP fetch must not be called for built-in")

    monkeypatch.setattr("agent_lab.mcp_spec_export.fetch_claude_mcp_entry", _native_fetch_called)

    overlay = build_claude_mcp_overlay(tmp_path, _only_code_memory_run())

    assert overlay is not None
    data = json.loads(overlay.read_text(encoding="utf-8"))
    entry = data["mcpServers"]["agent-lab-code-memory"]
    assert entry["args"] == ["-m", "agent_lab.code_memory_mcp_server"]
    assert entry["env"]["AGENT_LAB_SESSION_FOLDER"] == str(tmp_path.resolve())
    assert entry["env"]["AGENT_LAB_CODE_MEMORY_MCP"] == "1"


def test_codex_args_use_builtin_stdio_without_native_fetch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_CODE_MEMORY_MCP", "1")
    reset_plugin_discovery_cache()

    def _native_fetch_called(_name: str) -> dict[str, object] | None:
        raise AssertionError("native Codex MCP fetch must not be called for built-in")

    monkeypatch.setattr("agent_lab.mcp_spec_export.fetch_codex_mcp_spec", _native_fetch_called)

    args = codex_mcp_stdio_config_args(tmp_path, _only_code_memory_run())
    joined = " ".join(args)

    assert 'mcp_servers."agent-lab-code-memory".command=' in joined
    assert 'mcp_servers."agent-lab-code-memory".args=["-m", "agent_lab.code_memory_mcp_server"]' in joined
    assert 'mcp_servers."agent-lab-code-memory".env.AGENT_LAB_CODE_MEMORY_MCP="1"' in joined
    assert 'mcp_servers."agent-lab-code-memory".enabled=true' in args
