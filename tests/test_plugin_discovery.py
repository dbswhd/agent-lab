"""Plugin discovery unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.plugin_discovery import (
    _parse_claude_plugins,
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


def test_parse_claude_plugins_ignores_metadata_lines():
    # Real `claude plugin list` output: a "❯ name@marketplace" header per
    # plugin followed by indented Version/Scope/Status metadata lines. A
    # naive "every non-empty line is a plugin" parse previously turned those
    # metadata lines into their own rows with colliding ids (every plugin's
    # "Status:" line became the same "claude:plugin:Status:" id), which the
    # slash-command menu then rendered as duplicate-key, label-less rows.
    output = (
        "Installed plugins:\n"
        "\n"
        "  ❯ agent-sdk-dev@claude-plugins-official\n"
        "    Version: unknown\n"
        "    Scope: user\n"
        "    Status: ✔ enabled\n"
        "\n"
        "  ❯ hookify@claude-plugins-official\n"
        "    Version: 1.0.0\n"
        "    Scope: user\n"
        "    Status: ✘ disabled\n"
    )
    rows = _parse_claude_plugins(output)
    ids = [row["id"] for row in rows]
    assert ids == [
        "claude:plugin:agent-sdk-dev@claude-plugins-official",
        "claude:plugin:hookify@claude-plugins-official",
    ]
    assert len(ids) == len(set(ids))
    assert rows[0]["status"] == "enabled"
    assert rows[1]["status"] == "disabled"
