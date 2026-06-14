"""Read-only workspace file browser + scoped (attachments-only) writes.

Powers the Files tab: a tree/view over the session folder and the session's
bound workspace roots. Reads are free; writes are restricted to the session
folder's ``attachments/`` so the worktree/Oracle safety loop is never bypassed
(repo edits must go through execute).
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_lab.attachments import (
    MAX_FILE_BYTES,
    MAX_TEXT_CHARS,
    TEXT_SUFFIXES,
    attachments_dir,
)
from agent_lab.run_meta import read_run_meta
from agent_lab.session import SESSIONS_DIR
from agent_lab.workspace_roots import resolve_workspace_roots, workspace_label

# Directory/file names hidden from the tree everywhere (vcs/build/cache noise).
_EXCLUDE_NAMES = {
    ".git",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".DS_Store",
    ".venv",
    "venv",
}


class WorkspaceFileError(Exception):
    """Base for workspace-file access failures."""


class RootNotFound(WorkspaceFileError):
    """Unknown root_id for this session → 404."""


class PathNotAllowed(WorkspaceFileError):
    """Resolved path escapes the root (traversal) → 403."""


class WriteNotAllowed(WorkspaceFileError):
    """Write target outside the session attachments allowlist → 409."""


@dataclass
class RootInfo:
    root_id: str
    label: str
    kind: str  # "session" | "workspace"
    path: Path
    is_primary: bool
    missing: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_id": self.root_id,
            "label": self.label,
            "kind": self.kind,
            "is_primary": self.is_primary,
            "missing": self.missing,
        }


def _session_folder(session_id: str) -> Path:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise RootNotFound(f"session not found: {session_id}")
    return folder


def _session_permissions(run_meta: dict[str, Any]) -> dict[str, Any]:
    """Permissions live at top-level or on the latest turn; prefer either."""
    perms = run_meta.get("permissions")
    if isinstance(perms, dict) and perms:
        return perms
    turns = run_meta.get("turns")
    if isinstance(turns, list):
        for turn in reversed(turns):
            if isinstance(turn, dict) and isinstance(turn.get("permissions"), dict):
                if turn["permissions"]:
                    return turn["permissions"]
    return {}


def _binding_path(run_meta: dict[str, Any]) -> Path | None:
    binding = run_meta.get("workspace_binding")
    if isinstance(binding, dict) and binding.get("path"):
        return Path(str(binding["path"])).expanduser()
    return None


def _root_id_for(path: Path, kind: str) -> str:
    if kind == "session":
        return "session"
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:8]
    return f"ws-{digest}"


def _build_roots(folder: Path) -> list[RootInfo]:
    """session folder + binding + permission-derived workspace roots (deduped)."""
    run_meta = read_run_meta(folder)
    perms = _session_permissions(run_meta)
    binding = _binding_path(run_meta)

    session_root = folder.resolve()
    roots: list[RootInfo] = [
        RootInfo(
            root_id="session",
            label="session",
            kind="session",
            path=session_root,
            is_primary=False,
            missing=False,
        )
    ]

    # Ordered workspace candidates: binding first (primary), then resolved roots.
    candidates: list[Path] = []
    if binding is not None:
        candidates.append(binding)
    candidates.extend(resolve_workspace_roots(perms))

    seen: set[str] = {str(session_root)}
    primary_assigned = False
    for cand in candidates:
        key = str(cand.resolve()) if cand.exists() else str(cand)
        if key in seen:
            continue
        seen.add(key)
        missing = not cand.is_dir()
        is_primary = False
        if not missing and not primary_assigned:
            is_primary = True
            primary_assigned = True
        roots.append(
            RootInfo(
                root_id=_root_id_for(cand if missing else cand.resolve(), "workspace"),
                label=workspace_label(cand) if not missing else (cand.name or str(cand)),
                kind="workspace",
                path=cand if missing else cand.resolve(),
                is_primary=is_primary,
                missing=missing,
            )
        )

    # If no workspace root could be primary, the session root becomes primary.
    if not primary_assigned:
        roots[0].is_primary = True

    _disambiguate_labels(roots)
    return roots


def _disambiguate_labels(roots: list[RootInfo]) -> None:
    """When two roots share a label, append a short path suffix to each."""
    counts: dict[str, int] = {}
    for r in roots:
        counts[r.label] = counts.get(r.label, 0) + 1
    for r in roots:
        if counts.get(r.label, 0) > 1:
            r.label = f"{r.label} ({r.path})"


def _root_by_id(folder: Path, root_id: str) -> RootInfo:
    for r in _build_roots(folder):
        if r.root_id == root_id:
            return r
    raise RootNotFound(f"unknown root_id: {root_id}")


def _resolve_within(root: Path, rel_path: str) -> Path:
    """Resolve rel_path under root, rejecting traversal/symlink escapes."""
    base = root.resolve()
    candidate = (base / (rel_path or "")).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise PathNotAllowed(f"path escapes root: {rel_path}") from exc
    return candidate


def _is_excluded(entry: Path) -> bool:
    if entry.name in _EXCLUDE_NAMES:
        return True
    if entry.name.startswith("."):
        return True
    # Never leak other sessions when browsing the agent-lab repo root.
    if entry.is_dir() and entry.resolve() == SESSIONS_DIR.resolve():
        return True
    return False


def _git_status_map(root: Path) -> dict[str, str]:
    """Relative path → single-letter git status for workspace roots."""
    if not (root / ".git").exists():
        return {}
    try:
        from agent_lab.subprocess_env import subprocess_env

        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "-uall"],
            env=subprocess_env(),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            return {}
        out: dict[str, str] = {}
        for line in result.stdout.splitlines():
            if len(line) < 4:
                continue
            code = line[:2].strip() or "?"
            rel = line[3:].strip().strip('"')
            if " -> " in rel:
                rel = rel.split(" -> ", 1)[1].strip()
            out[rel] = code[0] if code else "?"
        return out
    except (OSError, subprocess.SubprocessError):
        return {}


def list_roots(session_id: str) -> dict[str, Any]:
    folder = _session_folder(session_id)
    return {"roots": [r.to_dict() for r in _build_roots(folder)]}


def list_dir(session_id: str, root_id: str, rel_path: str = "") -> dict[str, Any]:
    folder = _session_folder(session_id)
    root = _root_by_id(folder, root_id)
    if root.missing:
        raise RootNotFound(f"root path missing on disk: {root_id}")
    target = _resolve_within(root.path, rel_path)
    if not target.is_dir():
        raise PathNotAllowed(f"not a directory: {rel_path}")
    entries: list[dict[str, Any]] = []
    git_map = _git_status_map(root.path) if root.kind == "workspace" else {}
    rel_prefix = rel_path.strip("/")
    for child in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        if _is_excluded(child):
            continue
        try:
            stat = child.stat()
        except OSError:
            continue
        child_rel = f"{rel_prefix}/{child.name}" if rel_prefix else child.name
        entry: dict[str, Any] = {
            "name": child.name,
            "type": "dir" if child.is_dir() else "file",
            "size": stat.st_size if child.is_file() else None,
            "mtime": stat.st_mtime,
        }
        if git_map and child.is_file():
            status = git_map.get(child_rel)
            if status:
                entry["git_status"] = status
        entries.append(entry)
    return {
        "root_id": root_id,
        "path": rel_path,
        "entries": entries,
    }


def read_file(session_id: str, root_id: str, rel_path: str) -> dict[str, Any]:
    folder = _session_folder(session_id)
    root = _root_by_id(folder, root_id)
    if root.missing:
        raise RootNotFound(f"root path missing on disk: {root_id}")
    target = _resolve_within(root.path, rel_path)
    if not target.is_file():
        raise PathNotAllowed(f"not a file: {rel_path}")
    size = target.stat().st_size
    suffix = target.suffix.lower()
    if size > MAX_FILE_BYTES or suffix not in TEXT_SUFFIXES:
        return {
            "root_id": root_id,
            "path": rel_path,
            "kind": "binary" if suffix not in TEXT_SUFFIXES else "large",
            "size": size,
            "content": None,
        }
    text = target.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > MAX_TEXT_CHARS
    if truncated:
        text = text[:MAX_TEXT_CHARS]
    return {
        "root_id": root_id,
        "path": rel_path,
        "kind": "text",
        "size": size,
        "content": text,
        "truncated": truncated,
    }


def resolve_readable_file(session_id: str, root_id: str, rel_path: str) -> Path:
    """Return the safe absolute path of a readable file (for raw byte serving)."""
    folder = _session_folder(session_id)
    root = _root_by_id(folder, root_id)
    if root.missing:
        raise RootNotFound(f"root path missing on disk: {root_id}")
    target = _resolve_within(root.path, rel_path)
    if not target.is_file():
        raise PathNotAllowed(f"not a file: {rel_path}")
    return target


def write_session_file(
    session_id: str,
    root_id: str,
    rel_path: str,
    content: str,
) -> dict[str, Any]:
    """Write is allowed ONLY under the session folder's attachments/."""
    folder = _session_folder(session_id)
    if root_id != "session":
        raise WriteNotAllowed("writes are only allowed under the session attachments/")
    target = _resolve_within(folder, rel_path)
    allowed_dir = attachments_dir(folder).resolve()
    try:
        target.resolve().relative_to(allowed_dir)
    except ValueError as exc:
        raise WriteNotAllowed(
            "writes are only allowed under the session attachments/"
        ) from exc
    if target.name.startswith("."):
        raise WriteNotAllowed("hidden files are not writable")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {
        "root_id": root_id,
        "path": rel_path,
        "size": target.stat().st_size,
        "ok": True,
    }
