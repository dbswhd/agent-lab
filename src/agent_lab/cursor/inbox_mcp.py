from __future__ import annotations

from agent_lab.run.state import RunStateLike
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


def discuss_inbox_mcp_enabled(
    run_meta: RunStateLike | None = None,
    *,
    agent_id: str | None = None,
) -> bool:
    """True when Room should pass ``inbox_mcp=True`` to agent invoke.

    - plan-workflow CLARIFY turns (via ``plan_workflow_wants_inbox_mcp``)
    - MCP-first discuss: inbox gate owner only (cursor excluded)

    Orchestrator harvest stays off on Fast; peer ``ask_human`` / ``propose_build`` MCP is allowed
    for the session team lead. Plan-workflow CLARIFY inbox remains off on Fast.
    """
    from agent_lab.inbox.mcp_policy import (
        discuss_inbox_mcp_agent_allowed,
        discuss_inbox_mcp_lane_enabled,
    )

    if agent_id is not None:
        return discuss_inbox_mcp_agent_allowed(run_meta, agent_id)
    return discuss_inbox_mcp_lane_enabled(run_meta)


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


def inbox_mcp_stdio_spec(
    session_folder: Path,
    *,
    caller_agent: str | None = None,
    policy_lane: str | None = None,
) -> dict[str, Any]:
    from agent_lab.inbox.mcp_policy import inbox_mcp_env_overrides

    env = {
        **os.environ,
        "AGENT_LAB_SESSION_FOLDER": str(session_folder.resolve()),
        **inbox_mcp_env_overrides(caller_agent=caller_agent, policy_lane=policy_lane),
    }
    return {
        "command": sys.executable,
        "args": ["-m", "agent_lab.inbox.mcp_server"],
        "env": env,
    }


def inbox_mcp_build_kwargs(permissions: dict[str, Any] | None) -> dict[str, str | None]:
    perms = permissions or {}
    caller = str(perms.get("_inbox_caller_agent") or "").strip().lower()
    lane = str(perms.get("_inbox_policy_lane") or "").strip().lower()
    return {
        "caller_agent": caller or None,
        "policy_lane": lane or None,
    }


def build_inbox_mcp_servers(
    session_folder: Path,
    *,
    caller_agent: str | None = None,
    policy_lane: str | None = None,
) -> dict[str, Any]:
    try:
        from cursor_sdk.types import StdioMcpServerConfig
    except ImportError:
        from dataclasses import dataclass as _dc

        @_dc
        class StdioMcpServerConfig:  # type: ignore[no-redef]
            command: str
            args: list
            env: dict

    spec = inbox_mcp_stdio_spec(
        session_folder,
        caller_agent=caller_agent,
        policy_lane=policy_lane,
    )
    return {
        INBOX_MCP_SERVER_NAME: StdioMcpServerConfig(
            command=spec["command"],
            args=spec["args"],
            env=spec["env"],
        )
    }


_CODEX_INBOX_ENV_KEYS = (
    "AGENT_LAB_SESSION_FOLDER",
    "AGENT_LAB_INBOX_CALLER_AGENT",
    "AGENT_LAB_INBOX_POLICY_LANE",
    "AGENT_LAB_INBOX_TIMEOUT_SEC",
    "AGENT_LAB_INBOX_POLL_SEC",
    "AGENT_LAB_ROOT",
    "PYTHONPATH",
    "PATH",
    "HOME",
    "VIRTUAL_ENV",
)


def build_codex_inbox_mcp_config_args(
    session_folder: Path,
    *,
    caller_agent: str | None = None,
    policy_lane: str | None = None,
) -> list[str]:
    """Codex `exec -c` overrides for the stdio Human Inbox MCP server."""
    spec = inbox_mcp_stdio_spec(
        session_folder,
        caller_agent=caller_agent,
        policy_lane=policy_lane,
    )
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


def build_claude_inbox_mcp_overlay(
    session_folder: Path,
    *,
    caller_agent: str | None = None,
    policy_lane: str | None = None,
) -> Path:
    """Write Claude `--mcp-config` JSON for the stdio Human Inbox MCP server."""
    spec = inbox_mcp_stdio_spec(
        session_folder,
        caller_agent=caller_agent,
        policy_lane=policy_lane,
    )
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
