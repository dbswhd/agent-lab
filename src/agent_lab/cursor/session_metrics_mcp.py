from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

SESSION_METRICS_MCP_SERVER_NAME = "agent-lab-session-metrics"


def session_metrics_mcp_enabled() -> bool:
    raw = (os.getenv("AGENT_LAB_SESSION_METRICS_MCP") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def session_metrics_mcp_stdio_spec(session_folder: Path) -> dict[str, Any]:
    env = {
        **os.environ,
        "AGENT_LAB_SESSION_FOLDER": str(session_folder.resolve()),
    }
    return {
        "command": sys.executable,
        "args": ["-m", "agent_lab.session.metrics_mcp_server"],
        "env": env,
    }


def build_session_metrics_mcp_servers(session_folder: Path) -> dict[str, Any]:
    try:
        from cursor_sdk.types import StdioMcpServerConfig
    except ImportError:
        from dataclasses import dataclass as _dc

        @_dc
        class StdioMcpServerConfig:  # type: ignore[no-redef]
            command: str
            args: list
            env: dict

    spec = session_metrics_mcp_stdio_spec(session_folder)
    return {
        SESSION_METRICS_MCP_SERVER_NAME: StdioMcpServerConfig(
            command=spec["command"],
            args=spec["args"],
            env=spec["env"],
        )
    }


def merge_room_mcp_servers(*server_maps: dict[str, Any] | None) -> dict[str, Any] | None:
    merged: dict[str, Any] = {}
    for block in server_maps:
        if block:
            merged.update(block)
    return merged or None


_CODEX_METRICS_ENV_KEYS = (
    "AGENT_LAB_SESSION_FOLDER",
    "AGENT_LAB_ROOT",
    "PYTHONPATH",
    "PATH",
    "HOME",
    "VIRTUAL_ENV",
)


def build_codex_session_metrics_config_args(session_folder: Path) -> list[str]:
    spec = session_metrics_mcp_stdio_spec(session_folder)
    server = SESSION_METRICS_MCP_SERVER_NAME
    prefix = f'mcp_servers."{server}"'
    args: list[str] = [
        "-c",
        f"{prefix}.command={spec['command']!r}",
        "-c",
        f"{prefix}.args={json.dumps(spec['args'])}",
        "-c",
        f"{prefix}.enabled=true",
    ]
    for key in _CODEX_METRICS_ENV_KEYS:
        value = spec["env"].get(key)
        if value:
            args.extend(["-c", f'{prefix}.env.{key}="{value}"'])
    return args


def build_claude_session_metrics_overlay(session_folder: Path) -> Path:
    spec = session_metrics_mcp_stdio_spec(session_folder)
    overlay_dir = session_folder / ".agent-lab"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    overlay = overlay_dir / "claude-session-metrics-mcp.json"
    entry: dict[str, Any] = {
        "command": spec["command"],
        "args": spec["args"],
    }
    if spec.get("env"):
        entry["env"] = spec["env"]
    overlay.write_text(
        json.dumps({"mcpServers": {SESSION_METRICS_MCP_SERVER_NAME: entry}}, indent=2) + "\n",
        encoding="utf-8",
    )
    return overlay


def ensure_session_metrics_mcp_overlays(session_folder: Path) -> None:
    """Materialize Claude metrics overlay so dogfood / Room can verify S1 mount."""
    if not session_metrics_mcp_enabled():
        return
    build_claude_session_metrics_overlay(session_folder)
