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


def plan_inbox_mcp_enabled() -> bool:
    """Inbox MCP for plan-workflow CLARIFY turns (discuss lane)."""
    raw = (os.getenv("AGENT_LAB_PLAN_INBOX") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return execute_inbox_mcp_enabled()


def discuss_inbox_mcp_enabled(run_meta: dict[str, Any] | None = None) -> bool:
    """True when Room should pass ``inbox_mcp=True`` to agent invoke.

    - plan-workflow CLARIFY turns (via ``plan_workflow_wants_inbox_mcp``)
    - Loop discuss lane uses the same gate from ``room_agent_invoke`` (execute lane excluded)

    Fast / quick sessions skip discuss-lane inbox MCP (orchestrator harvest also skipped).
    When ``AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST=0`` (default), supervisor discuss uses
    peer ``ask_human`` MCP instead of post-turn harvest.
    """
    from agent_lab.room_preset import is_fast_room_session

    if run_meta and is_fast_room_session(run_meta):
        return False
    from agent_lab.plan_workflow import plan_workflow_wants_inbox_mcp

    if run_meta and plan_workflow_wants_inbox_mcp(run_meta):
        return plan_inbox_mcp_enabled()
    from agent_lab.inbox_harvest import orchestrator_inbox_harvest_enabled

    if run_meta and not orchestrator_inbox_harvest_enabled():
        return execute_inbox_mcp_enabled()
    return False


def mount_inbox_mcp_when_requested(inbox_mcp: bool) -> bool:
    """True when callers pass ``inbox_mcp=True`` and either lane allows MCP mount.

    Room gates plan CLARIFY via ``discuss_inbox_mcp_enabled``; this helper ensures
    ``AGENT_LAB_EXECUTE_INBOX=0`` + ``AGENT_LAB_PLAN_INBOX=1`` still mounts for
    Cursor/Codex when ``inbox_mcp=True``.
    """
    if not inbox_mcp:
        return False
    return execute_inbox_mcp_enabled() or plan_inbox_mcp_enabled()


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
    try:
        from cursor_sdk.types import StdioMcpServerConfig
    except ImportError:
        from dataclasses import dataclass as _dc

        @_dc
        class StdioMcpServerConfig:  # type: ignore[no-redef]
            command: str
            args: list
            env: dict

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


def build_claude_inbox_mcp_overlay(session_folder: Path) -> Path:
    """Write Claude `--mcp-config` JSON for the stdio Human Inbox MCP server."""
    spec = inbox_mcp_stdio_spec(session_folder)
    overlay_dir = session_folder / ".agent-lab"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    overlay = overlay_dir / "claude-inbox-mcp.json"
    entry: dict[str, Any] = {
        "command": spec["command"],
        "args": spec["args"],
    }
    if spec.get("env"):
        entry["env"] = spec["env"]
    overlay.write_text(
        json.dumps({"mcpServers": {INBOX_MCP_SERVER_NAME: entry}}, indent=2) + "\n",
        encoding="utf-8",
    )
    return overlay
