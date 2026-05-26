"""Per-turn agent permission flags (from UI)."""

from __future__ import annotations

from typing import Any

AgentId = str


def _perm(permissions: dict[str, Any] | None, agent: str, key: str) -> bool:
    if not permissions:
        return False
    block = permissions.get(agent) or {}
    return bool(block.get(key))


def codex_cli_allowed(permissions: dict[str, Any] | None) -> bool:
    return _perm(permissions, "codex", "cli")


def claude_tools_allowed(permissions: dict[str, Any] | None) -> bool:
    return _perm(permissions, "claude", "tools")


def claude_write_allowed(permissions: dict[str, Any] | None) -> bool:
    return _perm(permissions, "claude", "write")


def permission_preamble(permissions: dict[str, Any] | None, agent: str) -> str:
    """Extra instructions appended when user granted capabilities."""
    if not permissions:
        return ""
    lines: list[str] = []
    if agent == "cursor":
        if _perm(permissions, "cursor", "tools"):
            lines.append(
                "The human allowed you to use tools (read/search files) for this turn."
            )
        if _perm(permissions, "cursor", "local_agent_lab"):
            lines.append(
                "You may read files under the agent-lab project when relevant."
            )
        if _perm(permissions, "cursor", "local_pipeline"):
            lines.append(
                "You may read files under quant-pipeline when the human mentions Pipeline."
            )
    if agent == "codex" and _perm(permissions, "codex", "cli"):
        lines.append(
            "The human allowed Codex CLI for this turn — you may read/search/edit "
            "files and run shell commands in the project when needed."
        )
    if agent == "claude":
        if _perm(permissions, "claude", "tools"):
            lines.append(
                "The human allowed Claude Code read/search for this turn under granted "
                "project roots (--add-dir)."
            )
        if _perm(permissions, "claude", "write"):
            lines.append(
                "The human allowed Claude Code to edit files (acceptEdits) under granted "
                "roots only."
            )
        if _perm(permissions, "claude", "local_agent_lab"):
            lines.append("You may access files under the agent-lab project.")
        if _perm(permissions, "claude", "local_pipeline"):
            lines.append("You may access files under quant-pipeline when relevant.")
    if not lines:
        return ""
    return "Human-granted permissions this turn:\n" + "\n".join(f"- {x}" for x in lines)
