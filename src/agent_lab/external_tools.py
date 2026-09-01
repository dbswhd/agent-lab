"""External git tools / apps registry (Phase C — tools.yaml opt-in)."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from agent_lab.subprocess_env import subprocess_env

_AGENT_LAB_ROOT = Path(__file__).resolve().parents[2]


def resolve_external_tool_cwd(
    *,
    cwd_mode: str,
    session_folder: Path,
    workspace: Path | None = None,
    run: dict[str, Any] | None = None,
) -> tuple[Path | None, str | None]:
    """Resolve external tool working directory.

    Modes:
      session   — session folder (default)
      workspace — explicit workspace override, else session folder
      worktree  — open execution's worktree_path (delegate spike)
    """
    mode = str(cwd_mode or "session").strip().lower()
    if mode == "session":
        return session_folder, None
    if mode == "workspace":
        return workspace or session_folder, None
    if mode == "worktree":
        from agent_lab.core.execution_status_scopes import find_open_merge_pending_execution
        from agent_lab.run.meta import read_run_meta

        meta = run if run is not None else read_run_meta(session_folder)
        pending = find_open_merge_pending_execution(meta)
        if not pending:
            return None, "no open execution for worktree cwd"
        wt_path = pending.get("worktree_path")
        if not wt_path:
            return None, "open execution has no worktree_path"
        path = Path(str(wt_path))
        if not path.is_dir():
            return None, f"worktree path not found: {path}"
        return path, None
    return workspace or session_folder, None


def _expand_command_placeholders(
    parts: list[str],
    *,
    session_folder: Path,
    args: str,
    worktree_path: Path | None,
) -> list[str]:
    worktree = str(worktree_path) if worktree_path is not None else ""
    return [
        part.replace("{session_id}", session_folder.name).replace("{args}", args).replace("{worktree_path}", worktree)
        for part in parts
    ]


_DEFAULT_TOOLS: list[dict[str, Any]] = [
    {
        "id": "external:gjc-ralplan",
        "slash": "/gjc-ralplan",
        "label": "GJC ralplan",
        "description": "gajae-code ralplan (Planner→Architect→Critic). Configure in ~/.agent-lab/tools.yaml",
        "scope": "external",
        "kind": "external",
        "agent": None,
        "requires_human_confirm": True,
        "status": "stub",
    },
    {
        "id": "external:gjc-ultragoal",
        "slash": "/gjc-ultragoal",
        "label": "GJC ultragoal",
        "description": "gajae-code ultragoal multi-goal execution. Configure in ~/.agent-lab/tools.yaml",
        "scope": "external",
        "kind": "external",
        "agent": None,
        "requires_human_confirm": True,
        "status": "stub",
    },
    {
        "id": "external:gjc-team",
        "slash": "/gjc-team",
        "label": "GJC team",
        "description": "gajae-code parallel team workers. Configure in ~/.agent-lab/tools.yaml",
        "scope": "external",
        "kind": "external",
        "agent": None,
        "requires_human_confirm": True,
        "status": "stub",
    },
    {
        "id": "external:ulw-plan",
        "slash": "/ulw-plan",
        "label": "LazyCodex ulw-plan (stub)",
        "description": "Plan-only hook; configure command in ~/.agent-lab/tools.yaml",
        "scope": "external",
        "kind": "external",
        "agent": None,
        "requires_human_confirm": True,
        "status": "stub",
    },
    {
        "id": "external:codex-delegate",
        "slash": "/codex-delegate",
        "label": "Codex worktree delegate",
        "description": "Run codex exec in session worktree; stdout handoff JSON attaches to execution",
        "scope": "external",
        "kind": "external",
        "agent": None,
        "requires_human_confirm": True,
        "status": "stub",
    },
    {
        "id": "external:claude-delegate",
        "slash": "/claude-delegate",
        "label": "Claude worktree delegate",
        "description": "Run claude -p in session worktree; stdout handoff JSON attaches to execution",
        "scope": "external",
        "kind": "external",
        "agent": None,
        "requires_human_confirm": True,
        "status": "stub",
    },
]


def _tools_paths() -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for name in ("tools.yaml", "tools.json"):
        for base in (Path.home() / ".agent-lab", _AGENT_LAB_ROOT / ".agent-lab"):
            path = base / name
            if path.is_file() and path not in seen:
                paths.append(path)
                seen.add(path)
    return paths


def _yaml_scalar(raw: str) -> Any:
    text = raw.strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


def _parse_tools_yaml(text: str) -> list[dict[str, Any]]:
    """Parse minimal tools.yaml list schema (no PyYAML dependency)."""
    tools: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    list_key: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "tools:":
            continue
        indent = len(line) - len(line.lstrip(" "))
        if stripped.startswith("- "):
            if indent >= 6 and list_key and current is not None:
                items = current.setdefault(list_key, [])
                if isinstance(items, list):
                    items.append(_yaml_scalar(stripped[2:]))
                continue
            if current is not None:
                tools.append(current)
            current = {}
            list_key = None
            rest = stripped[2:].strip()
            if rest and ":" in rest:
                key, value = rest.split(":", 1)
                current[key.strip()] = _yaml_scalar(value)
            continue
        if current is None:
            continue
        if stripped.endswith(":") and indent <= 4:
            list_key = stripped[:-1].strip()
            current.setdefault(list_key, [])
            continue
        if ":" in stripped:
            key, value = stripped.split(":", 1)
            current[key.strip()] = _yaml_scalar(value)
            if key.strip() != list_key:
                list_key = None
    if current is not None:
        tools.append(current)
    return tools


def _normalize_tool_row(item: dict[str, Any]) -> dict[str, Any]:
    tool_id = str(item.get("id") or "").strip()
    slash = str(item.get("slash") or f"/{tool_id.split(':')[-1]}").strip()
    command = item.get("command")
    if isinstance(command, str) and command.strip():
        command = shlex.split(command)
    return {
        "id": tool_id or f"external:{slash.lstrip('/')}",
        "slash": slash if slash.startswith("/") else f"/{slash}",
        "label": str(item.get("label") or slash),
        "description": str(item.get("description") or ""),
        "scope": "external",
        "kind": "external",
        "agent": None,
        "requires_human_confirm": bool(item.get("human_approve", True)),
        "command": command,
        "cwd": str(item.get("cwd") or "session").strip().lower(),
        "status": "registered" if command else "stub",
    }


def _load_tools_file(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        data = json.loads(text)
        if not isinstance(data, dict):
            return []
        tools = data.get("tools") or []
        return [t for t in tools if isinstance(t, dict)]
    return _parse_tools_yaml(text)


def load_external_tools() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for path in _tools_paths():
        try:
            items = _load_tools_file(path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        for item in items:
            row = _normalize_tool_row(item)
            if row["id"] in seen_ids:
                continue
            seen_ids.add(row["id"])
            rows.append(row)
    if not rows:
        rows = list(_DEFAULT_TOOLS)
    return rows


def run_external_tool(
    tool_id: str,
    *,
    session_folder: Path,
    args: str = "",
    workspace: Path | None = None,
) -> dict[str, Any]:
    for row in load_external_tools():
        if row["id"] != tool_id:
            continue
        if row.get("status") == "stub" or not row.get("command"):
            return {
                "ok": True,
                "status": "stub",
                "detail": (
                    f"{row['label']} is registered but not executed. Configure command in ~/.agent-lab/tools.yaml"
                ),
            }
        cmd = row["command"]
        if isinstance(cmd, str):
            cmd_list = shlex.split(cmd)
        else:
            cmd_list = [str(part) for part in cmd]
        cwd_mode = str(row.get("cwd") or "session")
        cwd, cwd_err = resolve_external_tool_cwd(
            cwd_mode=cwd_mode,
            session_folder=session_folder,
            workspace=workspace,
        )
        if cwd_err or cwd is None:
            return {
                "ok": False,
                "status": "worktree_cwd_unavailable",
                "detail": cwd_err or "worktree cwd unavailable",
            }
        cmd_list = _expand_command_placeholders(
            cmd_list,
            session_folder=session_folder,
            args=args,
            worktree_path=cwd if cwd_mode == "worktree" else None,
        )
        proc = subprocess.run(
            cmd_list,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            env=subprocess_env(
                AGENT_LAB_SESSION_ID=session_folder.name,
                AGENT_LAB_EXTERNAL_TOOL_ARGS=args,
            ),
            timeout=int(os.getenv("AGENT_LAB_EXTERNAL_TOOL_TIMEOUT", "120")),
        )
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "")[:4000],
            "stderr": (proc.stderr or "")[:2000],
        }
    return {"ok": False, "detail": f"unknown external tool: {tool_id}"}
