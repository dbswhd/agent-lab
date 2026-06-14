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


def normalize_codex_permissions(
    permissions: dict[str, Any] | None,
) -> dict[str, Any]:
    """Room defaults: Codex CLI on unless opted out."""
    out = dict(permissions or {})
    codex = dict(out.get("codex") or {})
    codex.setdefault("cli", True)
    out["codex"] = codex
    return out


def normalize_cursor_permissions(
    permissions: dict[str, Any] | None,
) -> dict[str, Any]:
    """Room defaults: full Cursor access unless opted out."""
    out = dict(permissions or {})
    cursor = dict(out.get("cursor") or {})
    cursor.setdefault("tools", True)
    cursor.setdefault("local_agent_lab", True)
    cursor.setdefault("local_pipeline", True)
    cursor.setdefault("local_lecture_script", True)
    out["cursor"] = cursor
    return out


def normalize_agent_permissions(
    permissions: dict[str, Any] | None,
) -> dict[str, Any]:
    return normalize_codex_permissions(normalize_claude_permissions(normalize_cursor_permissions(permissions)))


def normalize_claude_permissions(
    permissions: dict[str, Any] | None,
) -> dict[str, Any]:
    """Room defaults: full Claude Code access unless opted out."""
    out = dict(permissions or {})
    claude = dict(out.get("claude") or {})
    claude.setdefault("tools", True)
    claude.setdefault("write", True)
    claude.setdefault("local_agent_lab", True)
    claude.setdefault("local_pipeline", True)
    claude.setdefault("local_lecture_script", True)
    out["claude"] = claude
    return out


def claude_runtime_block(
    permissions: dict[str, Any] | None,
    *,
    mcp_allowed: bool = False,
) -> str:
    """Explicit Claude Code CLI runtime for [고정 constraints] — matches claude_cli.invoke."""
    from agent_lab.claude_cli import resolve_claude_roots

    perms = normalize_claude_permissions(permissions)
    block = perms.get("claude") or {}
    if not block.get("tools", True):
        return "Claude Code runtime: text-only this turn (tools disabled by human)."
    roots = resolve_claude_roots(perms)
    root_lines = "\n".join(f"  - {p}" for p in roots) or "  - (project root)"
    edit = "acceptEdits (file edits allowed)" if block.get("write", True) else "read-only"
    mcp_line = (
        "- Session allowlist includes MCP servers — you may call enabled MCP tools when needed.\n"
        if mcp_allowed
        else "- Do not tell the human to add MCP servers unless a required integration is missing from the allowlist.\n"
    )
    return (
        "Claude Code runtime (Agent Lab — `claude -p`):\n"
        f"{mcp_line}"
        f"- Built-in tools: Read, Edit, Bash, Glob, Grep, … (--tools default)\n"
        f"- --add-dir roots:\n{root_lines}\n"
        f"- Permission mode: {edit}; verify files with Read/Grep in this turn."
    )


def cursor_runtime_block(permissions: dict[str, Any] | None) -> str:
    """Explicit Cursor SDK runtime for [고정 constraints]."""
    from agent_lab.workspace_roots import resolve_workspace_roots

    perms = normalize_cursor_permissions(permissions)
    block = perms.get("cursor") or {}
    if not block.get("tools", True):
        return "Cursor SDK runtime: text-only this turn (tools disabled by human)."
    roots = resolve_workspace_roots(perms)
    root_lines = "\n".join(f"  - {p}" for p in roots) or "  - (project root)"
    return (
        "Cursor SDK runtime (Agent Lab — local agent with tools, NOT text-only chat):\n"
        f"- Primary `cwd` and readable roots:\n{root_lines}\n"
        "- Use file/shell tools in this turn when the task is about code, paths, builds, or verification.\n"
        "- After edits: re-read or run checks before claiming done."
    )


def codex_runtime_block(permissions: dict[str, Any] | None) -> str:
    """Explicit Codex CLI runtime for [고정 constraints]."""
    from agent_lab.workspace_roots import resolve_workspace_roots

    perms = normalize_codex_permissions(permissions)
    if not (perms.get("codex") or {}).get("cli", True):
        return "Codex runtime: text-only this turn (CLI disabled by human)."
    roots = resolve_workspace_roots(perms)
    root_lines = "\n".join(f"  - {p}" for p in roots) or "  - (project root)"
    return (
        "Codex CLI runtime (Agent Lab — workspace-write when CLI allowed):\n"
        f"- Project roots:\n{root_lines}\n"
        "- Read/search/edit and run shell when debate needs verification or prototypes.\n"
        "- Follow [Multi-agent coordination] when peers edit the same files."
    )


def apply_discuss_executor_policy(
    permissions: dict[str, Any] | None,
    *,
    discuss: bool = True,
) -> dict[str, Any]:
    """Discuss turns: read-only Codex/Claude; file edits via Cursor execute only."""
    out = dict(permissions or {})
    if not discuss:
        return out
    out["_discuss_mode"] = True
    claude = dict(out.get("claude") or {})
    claude["write"] = False
    out["claude"] = claude
    codex = dict(out.get("codex") or {})
    codex["cli"] = True
    out["codex"] = codex
    return out


def permission_preamble(
    permissions: dict[str, Any] | None,
    agent: str,
    run_meta: dict[str, Any] | None = None,
) -> str:
    """Extra instructions appended when user granted capabilities."""
    perms = normalize_agent_permissions(permissions)
    discuss = bool((permissions or {}).get("_discuss_mode"))
    if agent == "claude":
        mcp_allowed = False
        if run_meta is not None:
            from agent_lab.command_registry import mcp_allowed_for_agent

            mcp_allowed = mcp_allowed_for_agent("claude", run_meta)
        block = claude_runtime_block(perms, mcp_allowed=mcp_allowed)
        if discuss:
            block += (
                "\n- **Discuss mode:** read-only — use Read/Grep to verify; "
                "do not Edit/write files or claim you patched the repo."
            )
        return block
    if agent == "cursor":
        return cursor_runtime_block(perms)
    if agent == "codex":
        block = codex_runtime_block(perms)
        if discuss:
            block += (
                "\n- **Discuss mode:** read-only sandbox — verify with read/grep/shell; "
                "propose edits as `[PROPOSED:]` text; file writes belong to Cursor execute."
            )
        return block

    if not perms:
        return ""
