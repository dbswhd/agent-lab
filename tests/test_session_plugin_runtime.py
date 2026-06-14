from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.run_meta import patch_run_meta
from agent_lab.session_plugin_runtime import (
    claude_execute_extra_args,
    codex_execute_plugin_config_args,
    enrich_execute_permissions,
    execute_plugin_prompt_addon,
    execute_plugins_enabled,
)


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")


@pytest.fixture
def session_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "sess-plugins"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    return folder


def test_execute_plugins_enabled_with_mock_defaults(
    session_folder: Path, mock_env: None
) -> None:
    assert execute_plugins_enabled(session_folder) is True


def test_execute_plugins_disabled_when_allowlist_cleared(
    session_folder: Path, mock_env: None
) -> None:
    patch_run_meta(
        session_folder,
        lambda run: {
            **run,
            "agent_plugins": {
                "claude": {"enabled": []},
                "codex": {"enabled": []},
                "cursor": {"enabled": []},
            },
        },
    )
    assert execute_plugins_enabled(session_folder) is False


def test_enrich_execute_permissions_sets_flags(
    session_folder: Path, mock_env: None
) -> None:
    out = enrich_execute_permissions({}, session_folder)
    assert out["_execute_plugins"] is True
    assert out["_session_folder"] == str(session_folder.resolve())


def test_execute_plugin_prompt_addon_injects_block(
    session_folder: Path, mock_env: None
) -> None:
    user = execute_plugin_prompt_addon("do work", session_folder, "claude")
    assert "do work" in user
    assert "claude" in user.lower() or "plugin" in user.lower()


def test_claude_execute_extra_args_writes_overlay(
    session_folder: Path, mock_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CLAUDE_MCP_CONFIG", raising=False)
    perms = enrich_execute_permissions({}, session_folder)
    args = claude_execute_extra_args(perms)
    assert args[0] == "--mcp-config"
    cfg = Path(args[1])
    assert cfg.is_file()
    assert cfg.name in {"claude-mcp-allowlist.json", "claude-mcp-passthrough.json"}


def test_codex_execute_plugin_config_args_enables_allowlisted_mcp(
    session_folder: Path,
    mock_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_plugins = [
        {
            "id": "codex:mcp:test",
            "name": "test-mcp",
            "agent": "codex",
            "kind": "mcp",
            "enabled_default": True,
        }
    ]
    def stub(*_a, **_k):
        return {"plugins": fake_plugins}
    monkeypatch.setattr("agent_lab.session_plugin_runtime.discover_plugins", stub)
    monkeypatch.setattr("agent_lab.command_registry.discover_plugins", stub)
    monkeypatch.setattr("agent_lab.mcp_spec_export.discover_plugins", stub)
    monkeypatch.setattr(
        "agent_lab.mcp_spec_export.fetch_codex_mcp_spec",
        lambda _name: {
            "transport": {
                "type": "stdio",
                "command": "node",
                "args": ["/tmp/mcp.js"],
            }
        },
    )
    args = codex_execute_plugin_config_args(session_folder)
    assert 'mcp_servers."test-mcp".command=' in " ".join(args)
