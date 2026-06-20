from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.mcp_spec_export import (
    build_claude_mcp_overlay,
    codex_mcp_stdio_config_args,
    write_session_mcp_export_manifest,
)
from agent_lab.plugin_discovery import discover_plugins, reset_plugin_discovery_cache


def _code_memory_disabled_run() -> dict[str, object]:
    return {
        "agent_plugins": {
            "claude": {"enabled": ["claude:mcp:agent-lab-code-memory"]},
            "codex": {"enabled": ["codex:mcp:agent-lab-code-memory"]},
            "cursor": {"enabled": []},
        }
    }


def test_code_memory_off_discovery_has_no_rows_and_is_stable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.delenv("AGENT_LAB_CODE_MEMORY_MCP", raising=False)
    reset_plugin_discovery_cache()

    before = discover_plugins(tmp_path, mock=True)
    reset_plugin_discovery_cache()
    after = discover_plugins(tmp_path, mock=True)

    assert before == after
    assert not any(row.get("name") == "agent-lab-code-memory" for row in after["plugins"])
    assert not any(row.get("name") == "agent-lab-code-memory" for rows in after["agents"].values() for row in rows)


def test_code_memory_off_exports_no_mounts_or_manifest_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.delenv("AGENT_LAB_CODE_MEMORY_MCP", raising=False)
    reset_plugin_discovery_cache()

    run = _code_memory_disabled_run()
    overlay = build_claude_mcp_overlay(tmp_path, run)
    args = codex_mcp_stdio_config_args(tmp_path, run)
    manifest = write_session_mcp_export_manifest(tmp_path, run)
    data = json.loads(manifest.read_text(encoding="utf-8"))

    assert overlay is None
    assert not any("agent-lab-code-memory" in arg for arg in args)
    assert "agent-lab-code-memory" not in data["claude"]
    assert "agent-lab-code-memory" not in data["codex"]
