from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

INBOX_MCP_SERVER_NAME = "agent-lab-inbox"


def execute_inbox_mcp_enabled() -> bool:
    raw = os.getenv("AGENT_LAB_EXECUTE_INBOX", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _execute_inbox_mcp_enabled() -> bool:
    """Backward-compatible alias."""
    return execute_inbox_mcp_enabled()


def inbox_mcp_stdio_spec(session_folder: Path) -> dict[str, Any]:
    env = {
        **os.environ,
        "AGENT_LAB_SESSION_FOLDER": str(session_folder.resolve()),
    }
    return {
        "command": sys.executable,
        "args": ["-m", "agent_lab.inbox_mcp_server"],
        "env": env,
    }


def build_inbox_mcp_servers(session_folder: Path) -> dict[str, Any]:
    from cursor_sdk.types import StdioMcpServerConfig

    spec = inbox_mcp_stdio_spec(session_folder)
    return {
        INBOX_MCP_SERVER_NAME: StdioMcpServerConfig(
            command=spec["command"],
            args=spec["args"],
            env=spec["env"],
        )
    }


_CODEX_INBOX_ENV_KEYS = (
    "AGENT_LAB_SESSION_FOLDER",
    "AGENT_LAB_INBOX_TIMEOUT_SEC",
    "AGENT_LAB_INBOX_POLL_SEC",
    "AGENT_LAB_ROOT",
    "PYTHONPATH",
    "PATH",
    "HOME",
    "VIRTUAL_ENV",
)


def build_codex_inbox_mcp_config_args(session_folder: Path) -> list[str]:
    """Codex `exec -c` overrides for the stdio Human Inbox MCP server."""
    spec = inbox_mcp_stdio_spec(session_folder)
    server = INBOX_MCP_SERVER_NAME
    prefix = f'mcp_servers."{server}"'
    args: list[str] = [
        "-c",
        f"{prefix}.command={spec['command']!r}",
        "-c",
        f"{prefix}.args={json.dumps(spec['args'])}",
        "-c",
        f"{prefix}.enabled=true",
    ]
    for key in _CODEX_INBOX_ENV_KEYS:
        value = spec["env"].get(key)
        if value:
            args.extend(["-c", f'{prefix}.env.{key}="{value}"'])
    return args
