"""Shared path parsing for plan execute snapshots."""

from __future__ import annotations

import re
from pathlib import Path

_PATH_EXTENSION = re.compile(
    r"\.(?:py|mjs|js|ts|tsx|json|css|md|html|pdf|txt|yaml|yml|sh|toml|cfg|ini)$",
    re.I,
)


def looks_like_file_path(token: str) -> bool:
    """True when a backtick span from plan '어디서' is likely a file path."""
    text = token.strip()
    if not text:
        return False
    if "→" in text or "->" in text:
        return False
    if text.startswith("/") or text.startswith("~"):
        return True
    if text.startswith("."):
        return True
    if "/" in text or "\\" in text:
        return True
    return bool(_PATH_EXTENSION.search(text))


def filter_file_paths(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for token in tokens:
        if not looks_like_file_path(token):
            continue
        norm = token.strip()
        if norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def paths_relative_to_workspace(cwd: Path, raw_paths: list[str]) -> list[str]:
    """Convert plan paths to cwd-relative posix paths for snapshot/diff."""
    cwd_resolved = cwd.resolve()
    rels: list[str] = []
    seen: set[str] = set()
    for raw in filter_file_paths(raw_paths):
        path = Path(raw).expanduser()
        if path.is_absolute():
            resolved = path.resolve()
            try:
                rel = resolved.relative_to(cwd_resolved)
                rel_str = rel.as_posix()
            except ValueError as e:
                raise ValueError(f"{raw!r} is not in the subpath of {cwd_resolved!r}") from e
        else:
            rel_str = raw.replace("\\", "/")
            if rel_str.startswith("./"):
                rel_str = rel_str[2:]
        if rel_str in seen:
            continue
        seen.add(rel_str)
        rels.append(rel_str)
    return rels


def paths_under_workspace(cwd: Path, rel_paths: list[str]) -> bool:
    """True when each relative path sits under cwd and parent dirs exist."""
    cwd_resolved = cwd.resolve()
    if not rel_paths:
        return False
    for rel in rel_paths:
        target = (cwd_resolved / rel).resolve()
        try:
            target.relative_to(cwd_resolved)
        except ValueError:
            return False
        if not target.parent.is_dir():
            return False
    return True


def normalize_snapshot_path(path: str, *, cwd: Path) -> str:
    """Normalize a path for snapshot operations under cwd."""
    raw = path.strip()
    if not raw:
        return raw
    expanded = Path(raw).expanduser()
    if expanded.is_absolute():
        return expanded.resolve().relative_to(cwd.resolve()).as_posix()
    rel = raw.replace("\\", "/")
    if rel.startswith("./"):
        rel = rel[2:]
    return rel
