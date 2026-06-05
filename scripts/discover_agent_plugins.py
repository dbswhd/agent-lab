#!/usr/bin/env python3
"""Phase A spike: list Claude/Codex plugins & MCP (read-only). See docs/PLUGIN-DISCOVERY.md."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], *, timeout: int = 60) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=ROOT,
        )
    except FileNotFoundError:
        return 127, f"not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def _skills(workspace: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(workspace.glob(".claude/skills/*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        name = path.parent.name
        desc = ""
        if text.startswith("---"):
            end = text.find("---", 3)
            if end > 0:
                block = text[3:end]
                for line in block.splitlines():
                    if line.startswith("description:"):
                        desc = line.split(":", 1)[1].strip()
                    elif line.startswith("name:"):
                        name = line.split(":", 1)[1].strip()
        rows.append(
            {
                "slash": f"/{name}",
                "name": name,
                "description": desc,
                "path": str(path.relative_to(workspace)),
            }
        )
    return rows


def main() -> int:
    workspace = Path(
        subprocess.check_output(
            [sys.executable, "-c", "from agent_lab.workspace_roots import discuss_primary_workspace; print(discuss_primary_workspace({}))"],
            cwd=ROOT,
            text=True,
        ).strip()
        or ROOT
    )

    claude_mcp = _run(["claude", "mcp", "list"])
    claude_plugins = _run(["claude", "plugin", "list"])
    codex_plugins = _run(["codex", "plugin", "list"])
    codex_mcp = _run(["codex", "mcp", "list"])

    payload = {
        "workspace": str(workspace),
        "skills_agent_lab": _skills(ROOT),
        "skills_workspace": _skills(workspace) if workspace != ROOT else [],
        "claude": {
            "mcp_list": {"exit": claude_mcp[0], "output": claude_mcp[1][:4000]},
            "plugin_list": {"exit": claude_plugins[0], "output": claude_plugins[1][:2000]},
        },
        "codex": {
            "plugin_list": {"exit": codex_plugins[0], "output": codex_plugins[1][:4000]},
            "mcp_list": {"exit": codex_mcp[0], "output": codex_mcp[1][:4000]},
        },
        "cursor": {
            "note": "No list CLI in Agent Lab; MCP/plugins inherit from Cursor IDE bridge.",
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
