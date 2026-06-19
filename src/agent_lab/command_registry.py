"""Unified slash command catalog and execution router."""

from __future__ import annotations

import os
import json


def _emit_slash_chat_line(folder: Path, summary: str) -> None:
    """Append a visible transcript entry for slash-command results (gajae-code style)."""
    chat_path = folder / "chat.jsonl"
    try:
        if not chat_path.is_file():
            chat_path.write_text("", encoding="utf-8")
        line = json.dumps(
            {
                "role": "system",
                "agent": None,
                "content": f"[slash] {summary}",
                "ts": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
        )
        with chat_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
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
from agent_lab.agent_roster import dynamic_room_enabled
from agent_lab.plugin_discovery import (
    discover_plugins,
    discover_plugins_fast,
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


# Dynamic resilient room management commands (G005). Exposed in the composer
# command catalog only when AGENT_LAB_DYNAMIC_ROOM is on; each delegates to
# agent_lab.slash_commands.dispatch via the "dynamic_room:<name>" handler.
_DYNAMIC_ROOM_COMMANDS: list[dict[str, Any]] = [
    {
        "id": "login",
        "slash": "/login",
        "label": "Provider 로그인",
        "description": "/login <provider> [key] — 계정 추가/로그인 (oauth는 CLI 안내)",
        "scope": "room",
        "kind": "server",
        "agent": None,
        "handler": "dynamic_room:login",
    },
    {
        "id": "logout",
        "slash": "/logout",
        "label": "Provider 로그아웃",
        "description": "/logout <provider> — 저장된 계정 비우기",
        "scope": "room",
        "kind": "server",
        "agent": None,
        "handler": "dynamic_room:logout",
    },
    {
        "id": "accounts",
        "slash": "/accounts",
        "label": "계정 관리",
        "description": "/accounts <provider> [list|add <label> <secret>|remove <label>]",
        "scope": "room",
        "kind": "server",
        "agent": None,
        "handler": "dynamic_room:accounts",
    },
    {
        "id": "model",
        "slash": "/model",
        "label": "Room 모델 구성",
        "description": "/model [a,b,c] — roster 구성 조회/변경",
        "scope": "room",
        "kind": "server",
        "agent": None,
        "handler": "dynamic_room:model",
    },
    {
        "id": "usage",
        "slash": "/usage",
        "label": "사용량/쿨다운",
        "description": "/usage [provider] — 계정 쿨다운/노출 상태",
        "scope": "room",
        "kind": "server",
        "agent": None,
        "handler": "dynamic_room:usage",
    },
    {
        "id": "agents",
        "slash": "/agents",
        "label": "활성 Roster",
        "description": "/agents — 현재 활성 에이전트와 역할 배치",
        "scope": "room",
        "kind": "server",
        "agent": None,
        "handler": "dynamic_room:agents",
    },
]
_ACCOUNT_COMMANDS = frozenset({"login", "logout", "accounts"})


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
    discovery = discover_plugins_fast(ws, mock=mock)
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

    for row in _DYNAMIC_ROOM_COMMANDS:
        if dynamic_room_enabled() or row["id"] in _ACCOUNT_COMMANDS:
            commands.append({**row, "enabled": True})

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
        "discovery_refreshing": discovery.get("refreshing", False),
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


def _format_dynamic_room(name: str, res: dict[str, Any]) -> str:
    """Compact human-readable summary of a slash_commands.dispatch result."""

    def _accts(rows: list[dict[str, Any]]) -> str:
        return ", ".join(f"{a.get('label')}={a.get('masked')}" for a in rows) or "(없음)"

    if name == "login":
        if res.get("prompt"):
            return str(res["prompt"])
        prov = res.get("provider", "")
        if res.get("note"):
            return f"/login {prov}: {res['note']}"
        return f"/login {prov}: {_accts(res.get('accounts') or [])}"
    if name == "logout":
        if res.get("prompt"):
            return str(res["prompt"])
        prov = res.get("provider", "")
        if res.get("auth_kind") == "oauth":
            return f"/logout {prov}: CLI 로그아웃 시작"
        return f"/logout {prov}: 계정 비움"
    if name == "accounts":
        prov = res.get("provider", "")
        delta = ""
        if res.get("added"):
            delta = f" (+{res['added']})"
        elif res.get("removed"):
            delta = f" (-{res['removed']})"
        return f"/accounts {prov}{delta}: {_accts(res.get('accounts') or [])}"
    if name == "model":
        if res.get("prompt"):
            return str(res["prompt"])
        comp = ", ".join(res.get("composition") or [])
        sub = ", ".join(res.get("substitution") or [])
        if res.get("note"):
            return f"/model: {res['note']}"
        verb = "변경됨" if res.get("updated") else "현재"
        return f"/model {verb}: [{comp}] · 대체 [{sub}]"
    if name == "usage":
        if res.get("prompt"):
            return str(res["prompt"])
        rows = res.get("rows") or []
        if not rows:
            return "/usage: 등록된 계정 없음"
        return "/usage: " + " | ".join(
            f"{r.get('provider')}/{r.get('label')}" + ("(cooldown)" if r.get('cooldown_active') else "") for r in rows
        )
    if name == "agents":
        if res.get("prompt"):
            return str(res["prompt"])
        roster = ", ".join(res.get("roster") or [])
        roles = res.get("roles") or {}
        roles_s = ", ".join(f"{k}:{v}" for k, v in roles.items())
        return f"/agents roster: [{roster}] · roles: {roles_s}"
    return f"/{name} 실행됨"



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
    history_args = "[redacted]" if command_id == "login" and args.startswith("api ") else args
    entry = {"at": now, "id": cmd["id"], "slash": cmd.get("slash"), "args": history_args}

    if kind == "client":
        _record_command_history(session_folder, {**entry, "result": "client_dispatch"})
        return {"ok": True, "kind": "client", "handler": handler, "command": cmd}

    if kind == "server" and handler == "goal_check":
        if not goal_loop_enabled():
            return {"ok": False, "detail": "goal loop is disabled"}
        result = check_session_goal(session_folder)
        _record_command_history(session_folder, {**entry, "result": result})
        return {"ok": True, "kind": "server", "result": result, "command": cmd}

    if kind == "server" and str(handler or "").startswith("dynamic_room:"):
        name = str(handler).split(":", 1)[1]
        if not dynamic_room_enabled() and name not in _ACCOUNT_COMMANDS:
            return {"ok": False, "detail": "dynamic room disabled", "command": cmd}
        from agent_lab.slash_commands import dispatch as _slash_dispatch

        text_in = str(cmd.get("slash") or f"/{name}")
        if args:
            text_in = f"{text_in} {args}"
        res = _slash_dispatch(text_in, session_folder=session_folder)
        if not res.get("ok"):
            _record_command_history(session_folder, {**entry, "result": {"error": res.get("error")}})
            return {
                "ok": False,
                "detail": res.get("error") or "command failed",
                "command": cmd,
            }
        if name == "login" and res.get("auth_kind") == "oauth" and res.get("provider"):
            from agent_lab.auth_runs import provider_login_status, start_auth_run

            try:
                state, _ = provider_login_status(str(res["provider"]))
                if state == "logged_in":
                    res["note"] = f"{res['provider']}는 이미 로그인되어 있습니다."
                else:
                    res["auth_run"] = start_auth_run(str(res["provider"]), "login")
                    res["note"] = "CLI 로그인을 시작했습니다."
            except RuntimeError as exc:
                return {"ok": False, "detail": str(exc), "command": cmd}
        if name == "logout" and res.get("provider") and res.get("auth_kind") == "oauth":
            from agent_lab.auth_runs import start_auth_run

            try:
                res["auth_run"] = start_auth_run(str(res["provider"]), "logout")
            except RuntimeError as exc:
                return {"ok": False, "detail": str(exc), "command": cmd}
        summary = _format_dynamic_room(name, res)
        _record_command_history(session_folder, {**entry, "result": {"summary": summary}})
        # Staged picker steps (stage present) should not be written to the transcript;
        # only final actions (login stored, model updated, usage rows, etc.) are emitted.
        if not res.get("stage"):
            _emit_slash_chat_line(session_folder, summary)
        return {
            "ok": True,
            "kind": "server",
            "handler": handler,
            "text": summary,
            "result": {**res, "summary": summary},
            "command": cmd,
        }

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


def invoke_tool(
    session_folder: Path,
    tool_id: str,
    *,
    args: str = "",
    confirm: bool = False,
    workspace: Path | None = None,
):
    """Unified front-door: dispatch a tool and return a normalized ``ToolResult``.

    Wraps :func:`execute_command` (reusing its dispatch + history), normalizes the
    heterogeneous result into one envelope, and records a G5 ``kind:"tool"`` trace
    span. ``execute_command`` itself is unchanged for raw-dict back-compat callers.
    """
    import time

    from agent_lab.tool_envelope import ToolDescriptor, normalize_tool_result
    from agent_lab.trace_recorder import record_tool_span

    t0 = time.monotonic()
    raw = execute_command(session_folder, tool_id, args=args, confirm=confirm, workspace=workspace)
    dur_ms = round((time.monotonic() - t0) * 1000.0, 1)
    row = raw.get("command") if isinstance(raw.get("command"), dict) else None
    descriptor = ToolDescriptor.from_row(row) if row else None
    result = normalize_tool_result(raw, descriptor=descriptor, duration_ms=dur_ms)
    record_tool_span(
        session_folder,
        name=result.tool_id or tool_id,
        dur_ms=dur_ms,
        status=result.status or ("ok" if result.ok else "error"),
    )
    return result


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
