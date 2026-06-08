from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.mcp_spec_export import (
    _parse_claude_mcp_get_text,
    build_claude_mcp_overlay,
    codex_transport_config_args,
    fetch_codex_mcp_spec,
)


def test_parse_claude_mcp_get_http() -> None:
    text = """figma:
  Type: http
  URL: https://mcp.figma.com/mcp
"""
    entry = _parse_claude_mcp_get_text(text)
    assert entry == {"url": "https://mcp.figma.com/mcp", "type": "http"}


def test_codex_transport_config_args_stdio() -> None:
    transport = {
        "type": "stdio",
        "command": "node",
        "args": ["/tmp/mcp.js", "mcp"],
        "cwd": "/work",
    }
    args = codex_transport_config_args("lsp", transport)
    assert 'mcp_servers."lsp".command=' in " ".join(args)
    assert 'mcp_servers."lsp".args=' in " ".join(args)
    assert 'mcp_servers."lsp".enabled=true' in args


def test_codex_transport_config_args_http() -> None:
    transport = {"type": "streamable_http", "url": "https://mcp.example.com/mcp"}
    args = codex_transport_config_args("ctx", transport)
    assert 'mcp_servers."ctx".url="https://mcp.example.com/mcp"' in args


def test_fetch_codex_mcp_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "name": "lsp",
        "transport": {"type": "stdio", "command": "node", "args": ["mcp.js"]},
    }

    def _fake(cmd: list[str], *, timeout: int = 45) -> tuple[int, str]:
        assert cmd[:4] == ["codex", "mcp", "get", "lsp"]
        return 0, json.dumps(payload)

    monkeypatch.setattr("agent_lab.mcp_spec_export._run_cli", _fake)
    spec = fetch_codex_mcp_spec("lsp")
    assert spec is not None
    assert spec["transport"]["command"] == "node"


def test_build_claude_mcp_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_plugins = [
        {
            "id": "claude:mcp:figma",
            "name": "figma",
            "agent": "claude",
            "kind": "mcp",
            "enabled_default": True,
        }
    ]
    monkeypatch.setattr(
        "agent_lab.mcp_spec_export.discover_plugins",
        lambda *_a, **_k: {"plugins": fake_plugins},
    )
    monkeypatch.setattr(
        "agent_lab.mcp_spec_export.fetch_claude_mcp_entry",
        lambda _name: {"url": "https://mcp.figma.com/mcp", "type": "http"},
    )
    session = tmp_path / "sess"
    session.mkdir()
    (session / "run.json").write_text("{}", encoding="utf-8")
    overlay = build_claude_mcp_overlay(session, {})
    assert overlay is not None
    data = json.loads(overlay.read_text(encoding="utf-8"))
    assert "figma" in data["mcpServers"]
