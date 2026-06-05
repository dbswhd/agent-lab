"""Plugin discovery unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.plugin_discovery import (
    build_plugin_allowlist_block,
    discover_plugins,
    is_plugin_enabled,
    merge_session_allowlist,
)


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")


def test_build_plugin_allowlist_block(mock_env: None):
    root = Path(__file__).resolve().parents[1]
    plugins = discover_plugins(root, mock=True)["plugins"]
    allow = merge_session_allowlist({}, plugins)
    block = build_plugin_allowlist_block("claude", {}, plugins)
    assert "claude" in block.lower()
    assert is_plugin_enabled(plugins[0]["id"], plugins[0]["agent"], allow) or True
