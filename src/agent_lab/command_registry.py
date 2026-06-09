"""Unified slash command catalog and execution router."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.external_tools import load_external_tools
from agent_lab.runtime.external_runner import (
    external_runner_enabled,
    external_tool_catalog_row,
    external_tools_allowlist,
    run_external_command,
)
from agent_lab.goal_loop import check_session_goal, goal_loop_enabled
from agent_lab.plugin_discovery import (
    discover_plugins,
    is_plugin_enabled,
    merge_session_allowlist,
    mock_mode,
)
from agent_lab.run_meta import patch_run_meta, read_run_meta

_SLASH_RE = re.compile(r"^/([a-zA-Z0-9_-]+)(?:\s+(.*))?$", re.DOTALL)

_BUILTIN_COMMANDS: list[dict[str, Any]] = [
    {
        "id": "goal-check",
        "slash": "/goal-check",
        "label": "Oracle 목표 재검",
        "description": "세션 목표 대비 transcript Oracle 검증",
        "scope": "session",
        "kind": "server",
        "agent": None,
        "handler": "goal_check",
        "requires_env": ["AGENT_LAB_GOAL_LOOP"],
    },
    {
        "id": "stop",
        "slash": "/stop",
        "label": "실행 중지",
        "description": "현재 Room run 취소 (UI)",
        "scope": "session",
        "kind": "client",
        "agent": None,
        "handler": "stop_run",
    },
    {
        "id": "focus-composer",
        "slash": "/focus",
        "label": "Composer 포커스",
        "description": "메시지 입력창으로 포커스",
        "scope": "session",
        "kind": "client",
        "agent": None,
        "handler": "focus_composer",
    },
]


def _env_requirements_met(requires: list[str] | None) -> bool:
    if not requires:
        return True
    for key in requires:
        val = os.getenv(key, "").strip().lower()
        if val not in {"1", "true", "yes", "on"}:
            return False
    return True


def _plugin_as_commands(
    plugins: list[dict[str, Any]],
    allowlist: dict[str, list[str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in plugins:
        agent = str(row.get("agent") or "").lower()
        pid = str(row.get("id") or "")
        slash = row.get("slash") or f"/{row.get('name', pid).split(':')[-1]}"
        if not str(slash).startswith("/"):
            slash = f"/{slash}"
        enabled = is_plugin_enabled(pid, agent, allowlist)
        kind = "agent_invoke" if row.get("kind") == "skill" else "plugin"
        rows.append(
            {
                "id": pid,
                "slash": slash,
                "label": str(row.get("name") or pid),
                "description": str(row.get("description") or ""),
                "scope": "agent",
                "kind": kind,
                "agent": agent,
                "source": row.get("kind"),
                "enabled": enabled,
                "disabled_reason": None if enabled else "plugin_disabled_in_session",
                "native_add_hint": row.get("native_add_hint"),
            }
        )
    return rows


def list_commands(
    session_folder: Path | None = None,
    *,
    workspace: Path | None = None,
    mock: bool | None = None,
) -> dict[str, Any]:
    ws = workspace or Path(os.getenv("AGENT_LAB_ROOT", Path(__file__).resolve().parents[2]))
    discovery = discover_plugins(ws, mock=mock)
    plugins = discovery.get("plugins") or []
    run_meta = read_run_meta(session_folder) if session_folder else {}
    allowlist = merge_session_allowlist(run_meta, plugins)

    commands: list[dict[str, Any]] = []
    for row in _BUILTIN_COMMANDS:
        cmd = dict(row)
        cmd["enabled"] = _env_requirements_met(row.get("requires_env"))
        if not cmd["enabled"]:
            cmd["disabled_reason"] = "env_required"
        commands.append(cmd)

    commands.extend(_plugin_as_commands(plugins, allowlist))

    ext_allowlist = external_tools_allowlist(run_meta)
    for row in load_external_tools():
        commands.append(
            external_tool_catalog_row(row, allowlist=ext_allowlist),
        )

    return {
        "commands": commands,
        "plugins": plugins,
        "allowlist": allowlist,
        "external_tools": {
            "enabled": external_runner_enabled(),
            "allowlist": ext_allowlist,
            "registered": [r["id"] for r in load_external_tools()],
        },
        "discovery_mock": discovery.get("mock", False),
    }


def parse_slash_command(text: str) -> tuple[str, str] | None:
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    match = _SLASH_RE.match(stripped)
    if not match:
        return None
    return match.group(1), (match.group(2) or "").strip()


def find_command(catalog: dict[str, Any], slash_or_name: str) -> dict[str, Any] | None:
    needle = slash_or_name.strip().lstrip("/").lower()
    for row in catalog.get("commands") or []:
        slash = str(row.get("slash") or "").lstrip("/").lower()
        cid = str(row.get("id") or "").lower()
        if slash == needle or cid == needle or cid.endswith(f":{needle}"):
            return row
    return None


def _record_command_history(folder: Path, entry: dict[str, Any]) -> None:
    def _append(run: dict[str, Any]) -> dict[str, Any]:
        history = list(run.get("command_history") or [])
        history.append(entry)
        run["command_history"] = history[-50:]
        return run

    patch_run_meta(folder, _append)


def execute_command(
    session_folder: Path,
    command_id: str,
    *,
    args: str = "",
    confirm: bool = False,
    workspace: Path | None = None,
) -> dict[str, Any]:
    catalog = list_commands(session_folder, workspace=workspace)
    cmd = find_command(catalog, command_id)
    if not cmd:
        return {"ok": False, "detail": f"unknown command: {command_id}"}
    if cmd.get("enabled") is False:
        return {
            "ok": False,
            "detail": cmd.get("disabled_reason") or "command disabled",
            "command": cmd,
        }

    handler = cmd.get("handler")
    kind = cmd.get("kind")
    now = datetime.now(timezone.utc).isoformat()
    entry = {"at": now, "id": cmd["id"], "slash": cmd.get("slash"), "args": args}

    if kind == "client":
        _record_command_history(session_folder, {**entry, "result": "client_dispatch"})
        return {"ok": True, "kind": "client", "handler": handler, "command": cmd}

    if kind == "server" and handler == "goal_check":
        if not goal_loop_enabled():
            return {"ok": False, "detail": "goal loop is disabled"}
        result = check_session_goal(session_folder)
        _record_command_history(session_folder, {**entry, "result": result})
        return {"ok": True, "kind": "server", "result": result, "command": cmd}

    if kind == "external":
        result = run_external_command(
            session_folder,
            str(cmd["id"]),
            args=args,
            confirm=confirm,
            workspace=workspace,
        )
        _record_command_history(session_folder, {**entry, "result": result})
        ok = bool(result.get("ok"))
        if result.get("status") == "pending_human":
            ok = False
        return {"ok": ok, "kind": "external", "result": result, "command": cmd}

    if kind in {"agent_invoke", "plugin"}:
        agent = str(cmd.get("agent") or "claude").lower()
        if agent == "claude" and cmd.get("source") == "skill":
            from agent_lab import claude_cli

            skill_name = str(cmd.get("slash") or "").lstrip("/") or args
            prompt = f"/{skill_name}"
            if args:
                prompt = f"{prompt}\n\n{args}"
            try:
                text = claude_cli.invoke("oracle", prompt, scribe=True, room_turn=False)
            except RuntimeError as exc:
                return {"ok": False, "detail": str(exc), "command": cmd}
            _record_command_history(
                session_folder,
                {**entry, "result": {"text": text[:500]}},
            )
            return {
                "ok": True,
                "kind": "agent_invoke",
                "agent": agent,
                "text": text,
                "command": cmd,
            }
        _record_command_history(
            session_folder,
            {**entry, "result": "plugin_autonomous_only"},
        )
        return {
            "ok": True,
            "kind": "plugin",
            "detail": (
                f"{cmd.get('label')} is enabled for autonomous use during Room turns. "
                f"Add hint: {cmd.get('native_add_hint') or 'native app'}"
            ),
            "command": cmd,
        }

    return {"ok": False, "detail": f"unsupported command kind: {kind}"}


def mcp_allowed_for_agent(
    agent: str,
    run_meta: dict[str, Any] | None,
    *,
    workspace: Path | None = None,
) -> bool:
    ws = workspace or Path(os.getenv("AGENT_LAB_ROOT", Path(__file__).resolve().parents[2]))
    discovery = discover_plugins(ws, mock=mock_mode())
    plugins = discovery.get("plugins") or []
    allow = merge_session_allowlist(run_meta, plugins)
    for row in plugins:
        if str(row.get("agent")).lower() != agent.lower():
            continue
        if row.get("kind") != "mcp":
            continue
        if is_plugin_enabled(str(row["id"]), agent, allow):
            return True
    return False
