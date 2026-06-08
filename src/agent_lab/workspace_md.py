"""Workspace-root AGENTS.md and SHARED_CONTEXT.md injection (MD-P3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

AGENTS_MD_CAP = 800
AGENTS_HIERARCHY_CAP = 900
SHARED_CONTEXT_CAP = 600

PER_DIR_AGENTS_GUIDANCE_HEADER = "[AGENTS.md — per-dir hierarchy]"


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


def read_agents_md_hierarchy_for_injection(
    run_meta: dict[str, Any],
    plan_md: str = "",
    *,
    max_chars: int = AGENTS_HIERARCHY_CAP,
) -> str:
    """Ancestor-chain AGENTS.md from plan path hints (LazyCodex §1.7 / MD-PROJECT)."""
    from agent_lab.repo_tree_context import build_per_dir_agents_block

    block = build_per_dir_agents_block(run_meta, plan_md, max_chars=max_chars)
    if not block.strip():
        return ""
    body = block.strip()
    if body.startswith("[Per-dir AGENTS.md]"):
        body = body[len("[Per-dir AGENTS.md]") :].strip()
    return body


def resolve_agents_md_for_guidance(
    run_meta: dict[str, Any],
    plan_md: str = "",
) -> tuple[str, str]:
    """Return (header_label, body) for session_guidance — hierarchy preferred when plan has paths."""
    hierarchy = read_agents_md_hierarchy_for_injection(run_meta, plan_md)
    if hierarchy:
        return PER_DIR_AGENTS_GUIDANCE_HEADER, hierarchy
    flat = read_agents_md_for_injection(run_meta)
    if flat:
        return "[AGENTS.md — Codex workspace guide]", flat
    return "", ""


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
