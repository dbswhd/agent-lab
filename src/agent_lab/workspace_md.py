"""Workspace-root AGENTS.md and SHARED_CONTEXT.md injection (MD-P3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

AGENTS_MD_CAP = 800
SHARED_CONTEXT_CAP = 600


def _workspace_root(run_meta: dict[str, Any]) -> Path | None:
    binding = run_meta.get("workspace_binding")
    if not isinstance(binding, dict):
        return None
    raw = binding.get("path")
    if not raw:
        return None
    root = Path(str(raw)).expanduser().resolve()
    return root if root.is_dir() else None


def read_agents_md_for_injection(run_meta: dict[str, Any]) -> str:
    root = _workspace_root(run_meta)
    if root is None:
        return ""
    path = root / "AGENTS.md"
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()[:AGENTS_MD_CAP]
    except OSError:
        return ""


def read_shared_context_for_injection(run_meta: dict[str, Any]) -> str:
    root = _workspace_root(run_meta)
    if root is None:
        return ""
    path = root / "SHARED_CONTEXT.md"
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()[:SHARED_CONTEXT_CAP]
    except OSError:
        return ""
