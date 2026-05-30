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


def normalize_claude_permissions(
    permissions: dict[str, Any] | None,
) -> dict[str, Any]:
    """Room defaults: Claude Code read + edit + agent-lab root unless opted out."""
    out = dict(permissions or {})
    claude = dict(out.get("claude") or {})
    claude.setdefault("tools", True)
    claude.setdefault("write", True)
    claude.setdefault("local_agent_lab", True)
    claude.setdefault("local_pipeline", False)
    out["claude"] = claude
    return out


def claude_runtime_block(permissions: dict[str, Any] | None) -> str:
    """Explicit Claude Code CLI runtime for [고정 constraints] — matches claude_cli.invoke."""
    from agent_lab.claude_cli import resolve_claude_roots

    perms = normalize_claude_permissions(permissions)
    block = perms.get("claude") or {}
    if not block.get("tools", True):
        return (
            "Claude Code runtime: text-only this turn (tools disabled by human)."
        )
    roots = resolve_claude_roots(perms)
    root_lines = "\n".join(f"  - {p}" for p in roots) or "  - (project root)"
    edit = "acceptEdits (file edits allowed)" if block.get("write", True) else "read-only"
    return (
        "Claude Code runtime (Agent Lab — `claude -p`, NOT claude.ai / NOT MCP-only):\n"
        "- NOT Claude Desktop chat; NOT limited to Figma MCP; do not suggest adding server-filesystem MCP.\n"
        f"- Built-in tools: Read, Edit, Bash, Glob, Grep, … (--tools default)\n"
        f"- --add-dir roots:\n{root_lines}\n"
        f"- Permission mode: {edit}; verify files with Read/Grep in this turn."
    )


def permission_preamble(permissions: dict[str, Any] | None, agent: str) -> str:
    """Extra instructions appended when user granted capabilities."""
    if agent == "claude":
        return claude_runtime_block(permissions)

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
    if not lines:
        return ""
    return "Human-granted permissions this turn:\n" + "\n".join(f"- {x}" for x in lines)
