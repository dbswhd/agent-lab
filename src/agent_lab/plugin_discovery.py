"""Discover agent plugins, MCP servers, and Claude skills for inventory + allowlist."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

_AGENT_LAB_ROOT = Path(__file__).resolve().parents[2]

_MOCK_PLUGINS: list[dict[str, Any]] = [
    {
        "id": "mock-figma-mcp",
        "name": "figma",
        "agent": "claude",
        "kind": "mcp",
        "description": "Mock Figma MCP (CI)",
        "status": "connected",
        "enabled_default": True,
        "native_add_hint": "claude mcp add … or Claude Code settings",
    },
    {
        "id": "browser@openai-bundled",
        "name": "browser@openai-bundled",
        "agent": "codex",
        "kind": "plugin",
        "description": "Mock Codex browser plugin (CI)",
        "status": "enabled",
        "enabled_default": True,
        "native_add_hint": "codex plugin add browser@openai-bundled",
    },
    {
        "id": "cursor-ide-inherited",
        "name": "Cursor IDE",
        "agent": "cursor",
        "kind": "plugin",
        "description": "MCP/plugins inherit from Cursor IDE bridge (no list API)",
        "status": "implicit",
        "enabled_default": True,
        "native_add_hint": "Cursor → Settings → MCP",
    },
]

_CURSOR_NATIVE_HINT = "Cursor → Settings → Features → MCP"
_CLAUDE_MCP_HINT = "claude mcp add … or Claude Desktop import"
_CODEX_PLUGIN_HINT = "codex plugin add <name@marketplace>"
_CODEX_MCP_HINT = "codex mcp add …"


def mock_mode() -> bool:
    return os.getenv("AGENT_LAB_MOCK_AGENTS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _run_cli(cmd: list[str], *, timeout: int = 45) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=_AGENT_LAB_ROOT,
        )
    except FileNotFoundError:
        return 127, f"not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def _parse_skill(path: Path, workspace: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    name = path.parent.name
    desc = ""
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            for line in text[3:end].splitlines():
                if line.startswith("description:"):
                    desc = line.split(":", 1)[1].strip()
                elif line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
    skill_id = f"claude:skill:{name}"
    return {
        "id": skill_id,
        "name": name,
        "agent": "claude",
        "kind": "skill",
        "description": desc or f"Claude skill /{name}",
        "status": "available",
        "enabled_default": True,
        "slash": f"/{name}",
        "native_add_hint": f".claude/skills/{name}/SKILL.md in workspace",
        "path": str(path.relative_to(workspace)) if path.is_relative_to(workspace) else str(path),
    }


def scan_skills(*roots: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob(".claude/skills/*/SKILL.md")):
            row = _parse_skill(path, root)
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            rows.append(row)
    return rows


def _parse_claude_mcp(output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("Checking"):
            continue
        if ": http" not in line and "(HTTP)" not in line:
            continue
        name_part = line.split(":", 1)[0].strip()
        name = name_part.replace("claude.ai ", "").strip()
        if not name:
            continue
        status = "connected" if "✓" in line else "needs_auth" if "!" in line else "unknown"
        rows.append(
            {
                "id": f"claude:mcp:{name}",
                "name": name,
                "agent": "claude",
                "kind": "mcp",
                "description": f"Claude MCP server ({name})",
                "status": status,
                "enabled_default": status == "connected",
                "native_add_hint": _CLAUDE_MCP_HINT,
            }
        )
    return rows


def _parse_codex_plugins(output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        if "@" not in line or "PLUGIN" in line or "Marketplace" in line:
            continue
        parts = line.split()
        if not parts:
            continue
        plugin_id = parts[0]
        if "@" not in plugin_id:
            continue
        status = "enabled" if "enabled" in line else "disabled" if "disabled" in line else "available"
        if "not installed" in line:
            status = "not_installed"
        rows.append(
            {
                "id": f"codex:plugin:{plugin_id}",
                "name": plugin_id,
                "agent": "codex",
                "kind": "plugin",
                "description": f"Codex plugin {plugin_id}",
                "status": status,
                "enabled_default": status == "enabled",
                "native_add_hint": _CODEX_PLUGIN_HINT,
            }
        )
    return rows


def _parse_codex_mcp(output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    in_table = False
    for line in output.splitlines():
        if line.strip().startswith("Name ") and "Command" in line:
            in_table = True
            continue
        if in_table:
            if not line.strip():
                in_table = False
                continue
            if line.strip().startswith("Name ") and "Url" in line:
                continue
            parts = line.split()
            if not parts:
                continue
            name = parts[0]
            if name in {"Name", "-"}:
                continue
            status = "enabled" if "enabled" in line else "disabled"
            rows.append(
                {
                    "id": f"codex:mcp:{name}",
                    "name": name,
                    "agent": "codex",
                    "kind": "mcp",
                    "description": f"Codex MCP {name}",
                    "status": status,
                    "enabled_default": status == "enabled",
                    "native_add_hint": _CODEX_MCP_HINT,
                }
            )
    return rows


def discover_plugins(
    workspace: Path,
    *,
    mock: bool | None = None,
) -> dict[str, Any]:
    """Return grouped plugin inventory for all agents."""
    if mock if mock is not None else mock_mode():
        plugins = list(_MOCK_PLUGINS) + scan_skills(_AGENT_LAB_ROOT, workspace)
        return {
            "workspace": str(workspace),
            "mock": True,
            "agents": _group_by_agent(plugins),
            "plugins": plugins,
        }

    plugins: list[dict[str, Any]] = []
    plugins.extend(scan_skills(_AGENT_LAB_ROOT, workspace))
    plugins.append(
        {
            "id": "cursor:ide-inherited",
            "name": "Cursor IDE MCP/plugins",
            "agent": "cursor",
            "kind": "plugin",
            "description": "Inherited from Cursor IDE via SDK bridge",
            "status": "implicit",
            "enabled_default": True,
            "native_add_hint": _CURSOR_NATIVE_HINT,
        }
    )

    code, out = _run_cli(["claude", "mcp", "list"])
    if code == 0:
        plugins.extend(_parse_claude_mcp(out))
    code, out = _run_cli(["claude", "plugin", "list"])
    if code == 0 and "No plugins installed" not in out:
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("No plugins"):
                continue
            plugins.append(
                {
                    "id": f"claude:plugin:{line.split()[0]}",
                    "name": line.split()[0],
                    "agent": "claude",
                    "kind": "plugin",
                    "description": line,
                    "status": "installed",
                    "enabled_default": True,
                    "native_add_hint": "claude plugin install …",
                }
            )

    code, out = _run_cli(["codex", "plugin", "list"])
    if code == 0:
        plugins.extend(_parse_codex_plugins(out))
    code, out = _run_cli(["codex", "mcp", "list"])
    if code == 0:
        plugins.extend(_parse_codex_mcp(out))

    return {
        "workspace": str(workspace),
        "mock": False,
        "agents": _group_by_agent(plugins),
        "plugins": plugins,
    }


def _group_by_agent(plugins: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {
        "cursor": [],
        "codex": [],
        "claude": [],
    }
    for row in plugins:
        agent = str(row.get("agent") or "").lower()
        if agent in grouped:
            grouped[agent].append(row)
    return grouped


def read_agent_plugins(run_meta: dict[str, Any] | None) -> dict[str, Any]:
    raw = (run_meta or {}).get("agent_plugins")
    return dict(raw) if isinstance(raw, dict) else {}


def default_allowlist(plugins: list[dict[str, Any]]) -> dict[str, list[str]]:
    allow: dict[str, list[str]] = {"cursor": [], "codex": [], "claude": []}
    for row in plugins:
        agent = str(row.get("agent") or "").lower()
        if agent not in allow:
            continue
        if row.get("enabled_default", True):
            allow[agent].append(str(row["id"]))
    return allow


def merge_session_allowlist(
    run_meta: dict[str, Any] | None,
    plugins: list[dict[str, Any]],
) -> dict[str, list[str]]:
    stored = read_agent_plugins(run_meta)
    if not stored:
        return default_allowlist(plugins)
    merged: dict[str, list[str]] = {"cursor": [], "codex": [], "claude": []}
    for agent in merged:
        entry = stored.get(agent)
        if isinstance(entry, dict) and isinstance(entry.get("enabled"), list):
            merged[agent] = [str(x) for x in entry["enabled"]]
        elif isinstance(entry, list):
            merged[agent] = [str(x) for x in entry]
    return merged


def is_plugin_enabled(
    plugin_id: str,
    agent: str,
    allowlist: dict[str, list[str]],
) -> bool:
    enabled = allowlist.get(agent.lower(), [])
    if not enabled:
        return False
    if "*" in enabled:
        return True
    return plugin_id in enabled


def patch_agent_plugins(
    run_meta: dict[str, Any],
    agent: str,
    enabled_ids: list[str],
) -> dict[str, Any]:
    plugins = dict(run_meta.get("agent_plugins") or {})
    plugins[agent.lower()] = {"enabled": list(enabled_ids)}
    run_meta["agent_plugins"] = plugins
    return run_meta


def build_plugin_allowlist_block(
    agent: str,
    run_meta: dict[str, Any] | None,
    plugins: list[dict[str, Any]] | None = None,
) -> str:
    if plugins is None:
        plugins = discover_plugins(_AGENT_LAB_ROOT).get("plugins") or []
    allow = merge_session_allowlist(run_meta, plugins)
    agent_ids = [
        row["name"]
        for row in plugins
        if str(row.get("agent")).lower() == agent.lower()
        and is_plugin_enabled(str(row["id"]), agent, allow)
    ]
    if not agent_ids:
        return (
            f"[{agent} plugins]\n"
            "- Session plugin allowlist is empty. Human can enable plugins in the Plugin panel.\n"
            "- Built-in CLI tools remain available per permissions."
        )
    lines = "\n".join(f"- {name}" for name in agent_ids[:24])
    extra = ""
    if len(agent_ids) > 24:
        extra = f"\n- … and {len(agent_ids) - 24} more"
    return (
        f"[{agent} plugins — session allowlist]\n"
        f"- Human enabled these plugins/MCP/skills for this session:\n{lines}{extra}\n"
        "- You may use them autonomously when the task requires it.\n"
        "- When Human sends an explicit `/command`, prioritize that invocation."
    )
