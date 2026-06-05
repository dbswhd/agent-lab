"""External git tools / apps registry (Phase C stub)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

_AGENT_LAB_ROOT = Path(__file__).resolve().parents[2]

_DEFAULT_TOOLS: list[dict[str, Any]] = [
    {
        "id": "external:ulw-plan",
        "slash": "/ulw-plan",
        "label": "LazyCodex ulw-plan (stub)",
        "description": "Plan-only hook; external LazyCodex runner not wired yet",
        "scope": "external",
        "kind": "external",
        "agent": None,
        "requires_human_confirm": True,
        "status": "stub",
    },
]


def _tools_paths() -> list[Path]:
    paths: list[Path] = []
    for name in ("tools.json", "tools.yaml"):
        home = Path.home() / ".agent-lab" / name
        if home.is_file():
            paths.append(home)
        repo = _AGENT_LAB_ROOT / ".agent-lab" / name
        if repo.is_file():
            paths.append(repo)
    return paths


def _load_tools_file(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        data = json.loads(text)
    else:
        return []
    if not isinstance(data, dict):
        return []
    tools = data.get("tools") or []
    return [t for t in tools if isinstance(t, dict)]


def load_external_tools() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = list(_DEFAULT_TOOLS)
    for path in _tools_paths():
        try:
            items = _load_tools_file(path)
        except (OSError, json.JSONDecodeError):
            continue
        for item in items:
            tool_id = str(item.get("id") or "").strip()
            slash = str(item.get("slash") or f"/{tool_id.split(':')[-1]}").strip()
            rows.append(
                {
                    "id": tool_id or f"external:{slash.lstrip('/')}",
                    "slash": slash if slash.startswith("/") else f"/{slash}",
                    "label": str(item.get("label") or slash),
                    "description": str(item.get("description") or ""),
                    "scope": "external",
                    "kind": "external",
                    "agent": None,
                    "requires_human_confirm": bool(item.get("human_approve", True)),
                    "command": item.get("command"),
                    "status": "registered",
                }
            )
    return rows


def run_external_tool(tool_id: str, *, session_folder: Path) -> dict[str, Any]:
    for row in load_external_tools():
        if row["id"] != tool_id:
            continue
        if row.get("status") == "stub" or not row.get("command"):
            return {
                "ok": True,
                "status": "stub",
                "detail": (
                    f"{row['label']} is registered but not executed. "
                    "Configure command in ~/.agent-lab/tools.json (Phase C)."
                ),
            }
        cmd = row["command"]
        if isinstance(cmd, str):
            cmd_list = cmd.split()
        else:
            cmd_list = list(cmd)
        proc = subprocess.run(
            cmd_list,
            cwd=str(session_folder),
            capture_output=True,
            text=True,
            timeout=int(os.getenv("AGENT_LAB_EXTERNAL_TOOL_TIMEOUT", "120")),
        )
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "")[:4000],
            "stderr": (proc.stderr or "")[:2000],
        }
    return {"ok": False, "detail": f"unknown external tool: {tool_id}"}
