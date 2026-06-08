"""Execute/repair plugin allowlist pass-through (Track B)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agent_lab.command_registry import mcp_allowed_for_agent
from agent_lab.plugin_discovery import (
    build_plugin_allowlist_block,
    discover_plugins,
    merge_session_allowlist,
    mock_mode,
)
from agent_lab.run_meta import read_run_meta

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def execute_plugins_enabled(session_folder: Path | None) -> bool:
    if session_folder is None:
        return False
    run = read_run_meta(session_folder)
    discovery = discover_plugins(_PROJECT_ROOT, mock=mock_mode())
    allow = merge_session_allowlist(run, discovery.get("plugins") or [])
    return any(bool(ids) for ids in allow.values())


def enrich_execute_permissions(
    permissions: dict[str, Any] | None,
    session_folder: Path | None,
) -> dict[str, Any]:
    out = dict(permissions or {})
    if session_folder is None:
        return out
    out["_session_folder"] = str(session_folder.resolve())
    if execute_plugins_enabled(session_folder):
        out["_execute_plugins"] = True
    return out


def execute_plugin_prompt_addon(
    user: str,
    session_folder: Path | None,
    agent_id: str,
) -> str:
    if session_folder is None or not execute_plugins_enabled(session_folder):
        return user
    run = read_run_meta(session_folder)
    block = build_plugin_allowlist_block(agent_id, run)
    if not block.strip():
        return user
    return f"{user.rstrip()}\n\n{block.strip()}"


def resolve_claude_mcp_config_path(session_folder: Path | None) -> str | None:
    """Resolve --mcp-config file when session allowlist enables MCP."""
    if session_folder is None:
        return None
    run = read_run_meta(session_folder)
    if not mcp_allowed_for_agent("claude", run):
        return None
    from agent_lab.mcp_spec_export import (
        build_claude_mcp_overlay,
        write_session_mcp_export_manifest,
    )

    overlay = build_claude_mcp_overlay(session_folder, run)
    write_session_mcp_export_manifest(session_folder, run)
    if overlay is not None:
        return str(overlay.resolve())
    explicit = (os.getenv("CLAUDE_MCP_CONFIG") or "").strip()
    if explicit and Path(explicit).expanduser().is_file():
        return str(Path(explicit).expanduser().resolve())
    for candidate in (
        _PROJECT_ROOT / ".mcp.json",
        Path.home() / ".claude" / "mcp.json",
        Path.home() / ".config" / "claude" / "mcp.json",
    ):
        if candidate.is_file():
            return str(candidate.resolve())
    overlay_dir = session_folder / ".agent-lab"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    overlay = overlay_dir / "claude-mcp-passthrough.json"
    if not overlay.is_file():
        overlay.write_text(
            json.dumps({"mcpServers": {}}, indent=2) + "\n",
            encoding="utf-8",
        )
    return str(overlay.resolve())


def claude_execute_extra_args(permissions: dict[str, Any] | None) -> list[str]:
    if not (permissions or {}).get("_execute_plugins"):
        return []
    raw = (permissions or {}).get("_session_folder")
    if not raw:
        return []
    cfg = resolve_claude_mcp_config_path(Path(str(raw)))
    if not cfg:
        return []
    return ["--mcp-config", cfg]


def codex_execute_plugin_config_args(session_folder: Path | None) -> list[str]:
    """Export allowlisted Codex MCP servers with full stdio/HTTP transport specs."""
    if session_folder is None or not execute_plugins_enabled(session_folder):
        return []
    run = read_run_meta(session_folder)
    if not mcp_allowed_for_agent("codex", run):
        return []
    from agent_lab.mcp_spec_export import (
        codex_mcp_stdio_config_args,
        write_session_mcp_export_manifest,
    )

    write_session_mcp_export_manifest(session_folder, run)
    return codex_mcp_stdio_config_args(session_folder, run)


def merge_codex_execute_config_overrides(
    session_folder: Path | None,
    base: list[str] | None,
) -> list[str]:
    merged = list(base or [])
    merged.extend(codex_execute_plugin_config_args(session_folder))
    return merged
