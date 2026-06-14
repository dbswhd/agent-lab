"""Fetch MCP server specs and build session-scoped CLI overlays (Track B)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_lab.plugin_discovery import (
    discover_plugins,
    is_plugin_enabled,
    merge_session_allowlist,
    mock_mode,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_cli(cmd: list[str], *, timeout: int = 45) -> tuple[int, str]:
    from agent_lab.plugin_discovery import _run_cli as _discover_run_cli

    return _discover_run_cli(cmd, timeout=timeout)


def fetch_codex_mcp_spec(name: str) -> dict[str, Any] | None:
    """Return parsed `codex mcp get NAME --json` payload or None."""
    code, out = _run_cli(["codex", "mcp", "get", name, "--json"])
    if code != 0 or not out.strip():
        return None
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def fetch_claude_mcp_entry(name: str) -> dict[str, Any] | None:
    """Build Claude `--mcp-config` server entry from `claude mcp get`."""
    code, out = _run_cli(["claude", "mcp", "get", name])
    if code != 0 or not out.strip():
        return None
    return _parse_claude_mcp_get_text(out)


def _parse_claude_mcp_get_text(text: str) -> dict[str, Any] | None:
    entry: dict[str, Any] = {}
    transport = ""
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("Type:"):
            transport = line.split(":", 1)[1].strip().lower()
        elif line.startswith("URL:"):
            entry["url"] = line.split(":", 1)[1].strip()
        elif line.startswith("Command:"):
            entry["command"] = line.split(":", 1)[1].strip()
        elif line.startswith("Args:"):
            args_raw = line.split(":", 1)[1].strip()
            entry["args"] = json.loads(args_raw) if args_raw.startswith("[") else [args_raw]
    if entry.get("url"):
        if transport == "http":
            entry.setdefault("type", "http")
        return entry
    if entry.get("command"):
        return entry
    return None


def codex_transport_config_args(server_name: str, transport: dict[str, Any]) -> list[str]:
    """Codex `exec -c` overrides for one MCP transport block."""
    prefix = f'mcp_servers."{server_name}"'
    args: list[str] = []
    typ = str(transport.get("type") or "").lower()
    if typ == "stdio":
        command = transport.get("command")
        if command:
            args.extend(["-c", f"{prefix}.command={command!r}"])
        raw_args = transport.get("args")
        if raw_args:
            args.extend(["-c", f"{prefix}.args={json.dumps(raw_args)}"])
        cwd = transport.get("cwd")
        if cwd:
            args.extend(["-c", f"{prefix}.cwd={cwd!r}"])
        env = transport.get("env")
        if isinstance(env, dict):
            for key, value in env.items():
                if value is not None:
                    args.extend(["-c", f'{prefix}.env.{key}="{value}"'])
    elif typ in {"http", "streamable_http"}:
        url = transport.get("url")
        if url:
            args.extend(["-c", f'{prefix}.url="{url}"'])
    args.extend(["-c", f"{prefix}.enabled=true"])
    return args


def _allowlisted_mcp_names(
    run: dict[str, Any] | None,
    agent: str,
) -> list[str]:
    discovery = discover_plugins(_PROJECT_ROOT, mock=mock_mode())
    plugins = discovery.get("plugins") or []
    allow = merge_session_allowlist(run, plugins)
    names: list[str] = []
    for row in plugins:
        if str(row.get("agent")).lower() != agent.lower():
            continue
        if row.get("kind") != "mcp":
            continue
        if not is_plugin_enabled(str(row["id"]), agent, allow):
            continue
        name = str(row.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def build_claude_mcp_overlay(session_folder: Path, run: dict[str, Any] | None) -> Path | None:
    """Write allowlist-filtered Claude MCP JSON for `--mcp-config`."""
    servers: dict[str, Any] = {}
    for name in _allowlisted_mcp_names(run, "claude"):
        entry = fetch_claude_mcp_entry(name)
        if entry:
            servers[name] = entry
    if not servers:
        return None
    overlay_dir = session_folder / ".agent-lab"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    overlay = overlay_dir / "claude-mcp-allowlist.json"
    overlay.write_text(
        json.dumps({"mcpServers": servers}, indent=2) + "\n",
        encoding="utf-8",
    )
    return overlay


def codex_mcp_stdio_config_args(
    session_folder: Path | None,
    run: dict[str, Any] | None,
) -> list[str]:
    """Full Codex MCP transport overrides for allowlisted servers."""
    if session_folder is None:
        return []
    args: list[str] = []
    for name in _allowlisted_mcp_names(run, "codex"):
        spec = fetch_codex_mcp_spec(name)
        transport = (spec or {}).get("transport") if isinstance(spec, dict) else None
        if isinstance(transport, dict) and transport.get("type"):
            args.extend(codex_transport_config_args(name, transport))
        else:
            args.extend(["-c", f'mcp_servers."{name}".enabled=true'])
    return args


def write_session_mcp_export_manifest(
    session_folder: Path,
    run: dict[str, Any] | None,
) -> Path:
    """Persist resolved MCP export metadata for debugging / UI."""
    manifest = {
        "claude": _allowlisted_mcp_names(run, "claude"),
        "codex": _allowlisted_mcp_names(run, "codex"),
    }
    overlay_dir = session_folder / ".agent-lab"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    path = overlay_dir / "mcp-export-manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path
