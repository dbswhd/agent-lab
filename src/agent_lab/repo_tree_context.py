"""Repo tree + per-dir AGENTS.md context (Track C)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from agent_lab.context.layers import repo_tree_layer_enabled

_PATH_HINT_RE = re.compile(
    r"`([^`]+\.(?:py|ts|tsx|js|md|json|yaml|yml|rs|go))`|"
    r"(?:^|\s)((?:src|app|web|tests|docs)/[\w./-]+)",
    re.MULTILINE,
)


def _workspace_root(run_meta: dict[str, Any] | None) -> Path | None:
    binding = (run_meta or {}).get("workspace_binding")
    if not isinstance(binding, dict):
        return None
    raw = binding.get("path")
    if not raw:
        return None
    path = Path(str(raw)).expanduser()
    return path.resolve() if path.is_dir() else None


def build_repo_tree_block(
    run_meta: dict[str, Any] | None,
    *,
    max_entries: int = 36,
) -> str:
    if not repo_tree_layer_enabled(run_meta):
        return ""
    root = _workspace_root(run_meta)
    if root is None:
        return ""
    lines: list[str] = [f"[Repo tree] `{root}`"]
    count = 0
    try:
        entries = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        return ""
    for entry in entries:
        if entry.name.startswith("."):
            continue
        suffix = "/" if entry.is_dir() else ""
        lines.append(f"- {entry.name}{suffix}")
        count += 1
        if count >= max_entries:
            lines.append("- …")
            break
    if count == 0:
        return ""
    return "\n".join(lines)


def _plan_path_hints(plan_md: str) -> list[Path]:
    hints: list[Path] = []
    seen: set[str] = set()
    for match in _PATH_HINT_RE.finditer(plan_md or ""):
        raw = (match.group(1) or match.group(2) or "").strip()
        if not raw or raw in seen:
            continue
        seen.add(raw)
        hints.append(Path(raw))
    return hints


def _agents_md_chain(root: Path, hint: Path) -> list[Path]:
    """Walk from plan path up to workspace root collecting AGENTS.md files."""
    target = root / hint
    current = target.parent if target.suffix else target
    chain: list[Path] = []
    while True:
        try:
            current.relative_to(root)
        except ValueError:
            break
        agents = current / "AGENTS.md"
        if agents.is_file():
            chain.append(agents)
        if current == root:
            break
        current = current.parent
    return chain


def _plan_action_path_hints(plan_md: str) -> list[Path]:
    """Structured paths from parsed plan actions (stage-2 per-dir memory)."""
    try:
        from agent_lab.plan.actions import parse_plan_actions
    except ImportError:
        return []
    hints: list[Path] = []
    seen: set[str] = set()
    for action in parse_plan_actions(plan_md):
        for raw in action.expected_paths():
            text = str(raw or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            hints.append(Path(text))
    return hints


def _collect_per_dir_agents_files(root: Path, plan_md: str) -> list[Path]:
    ordered: list[Path] = []
    seen: set[str] = set()
    hints = _plan_path_hints(plan_md) + _plan_action_path_hints(plan_md)
    for hint in hints:
        for agents in reversed(_agents_md_chain(root, hint)):
            key = str(agents.resolve())
            if key in seen:
                continue
            seen.add(key)
            ordered.append(agents)
    return ordered


def build_per_dir_agents_block(
    run_meta: dict[str, Any] | None,
    plan_md: str = "",
    *,
    max_chars: int = 900,
) -> str:
    root = _workspace_root(run_meta)
    if root is None:
        return ""
    chunks: list[str] = []
    used = 0
    for agents in _collect_per_dir_agents_files(root, plan_md):
        try:
            rel = agents.relative_to(root)
        except ValueError:
            rel = agents
        try:
            body = agents.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not body:
            continue
        room = max_chars - used
        if room < 80:
            break
        tail = body[-room:] if len(body) > room else body
        chunks.append(f"[{rel}]\n{tail}")
        used += len(tail)
        if used >= max_chars:
            break
    if not chunks:
        return ""
    return "[Per-dir AGENTS.md]\n" + "\n\n".join(chunks)
