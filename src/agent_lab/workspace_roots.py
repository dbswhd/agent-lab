"""Shared workspace roots for Cursor, Codex, and Claude Code in the 3-agent room."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def project_root() -> Path:
    root = os.getenv("AGENT_LAB_ROOT")
    if root and Path(root).is_dir():
        return Path(root).resolve()
    return PROJECT_ROOT.resolve()


def resolve_workspace_roots(permissions: dict[str, Any] | None) -> list[Path]:
    """Directories agents may read when permissions allow (unified across backends)."""
    home = Path.home()
    perms = permissions or {}
    roots: list[Path] = []

    cursor = perms.get("cursor") or {}
    claude = perms.get("claude") or {}
    codex = perms.get("codex") or {}

    if cursor.get("local_agent_lab", True) or claude.get("local_agent_lab", True):
        roots.append(project_root())
    if cursor.get("local_pipeline") or claude.get("local_pipeline"):
        pipeline = Path(
            os.getenv("QUANT_PIPELINE_ROOT", str(home / "Projects" / "quant-pipeline"))
        ).expanduser()
        if pipeline.is_dir():
            roots.append(pipeline.resolve())

    if not roots:
        roots.append(project_root())

    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        key = str(root.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(root.resolve())
    return unique


def primary_workspace(permissions: dict[str, Any] | None) -> Path:
    return resolve_workspace_roots(permissions)[0]


def workspace_roots_block(permissions: dict[str, Any] | None) -> str:
    roots = resolve_workspace_roots(permissions)
    lines = "\n".join(f"  - {p}" for p in roots)
    return f"Workspace roots (Cursor / Codex / Claude):\n{lines}"
