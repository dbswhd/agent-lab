"""Per-turn agent permission flags (from UI)."""

from __future__ import annotations

from typing import Any

AgentId = str


def _perm(permissions: dict[str, Any] | None, agent: str, key: str) -> bool:
    if not permissions:
        return False
    block = permissions.get(agent) or {}
    return bool(block.get(key))


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
            "The human allowed Codex CLI capabilities for this turn when needed."
        )
    if not lines:
        return ""
    return "Human-granted permissions this turn:\n" + "\n".join(f"- {x}" for x in lines)
