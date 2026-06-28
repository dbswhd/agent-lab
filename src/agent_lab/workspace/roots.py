"""Shared workspace roots for Cursor, Codex, and Claude Code in the 3-agent room."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agent_lab.plan.execute_paths import filter_file_paths, looks_like_file_path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _discuss_cwd_from_permissions(permissions: dict[str, Any] | None) -> Path | None:
    from agent_lab.session.guidance import discuss_cwd_from_permissions

    return discuss_cwd_from_permissions(permissions)


def is_bundled_app_runtime(path: Path | str) -> bool:
    """True when path is the embedded Python bundle inside Agent Lab.app."""
    norm = str(path).replace("\\", "/")
    return "Agent Lab.app" in norm and "/Resources/runtime" in norm


def resolve_user_agent_lab_root() -> Path | None:
    """User's agent-lab repo — not the embedded .app runtime copy."""
    from agent_lab.app_config import _expand_path, load_config

    cfg = load_config(create_default=False)
    paths = cfg.get("paths") if isinstance(cfg.get("paths"), dict) else {}
    if isinstance(paths, dict):
        lab = _expand_path(str(paths.get("agent_lab") or ""))
        if lab is not None:
            return lab
    home_lab = Path.home() / "Projects" / "agent-lab"
    if home_lab.is_dir():
        return home_lab.resolve()
    return None


def user_agent_lab_root() -> Path:
    """Workspace root for agent-lab preset and local_agent_lab permissions."""
    explicit = (os.getenv("AGENT_LAB_DEV_ROOT") or "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_dir():
            return path.resolve()
    runtime = project_root()
    if not is_bundled_app_runtime(runtime):
        return runtime
    resolved = resolve_user_agent_lab_root()
    if resolved is not None:
        return resolved
    return runtime


def project_root() -> Path:
    root = os.getenv("AGENT_LAB_ROOT")
    if root and Path(root).is_dir():
        return Path(root).resolve()
    return PROJECT_ROOT.resolve()


def resolve_workspace_roots(permissions: dict[str, Any] | None) -> list[Path]:
    """Directories agents may read when permissions allow (unified across backends)."""
    perms = permissions or {}
    roots: list[Path] = []

    cursor = perms.get("cursor") or {}
    claude = perms.get("claude") or {}

    if cursor.get("local_agent_lab", True) or claude.get("local_agent_lab", True):
        roots.append(user_agent_lab_root())
    if cursor.get("local_pipeline") or claude.get("local_pipeline"):
        pipe = pipeline_root()
        if pipe is not None:
            roots.append(pipe)
    if cursor.get("local_lecture_script") or claude.get("local_lecture_script"):
        lecture = lecture_script_root()
        if lecture is not None:
            roots.append(lecture)

    bound = _discuss_cwd_from_permissions(perms)
    if bound is not None:
        key = str(bound)
        if key not in {str(r.resolve()) for r in roots}:
            roots.append(bound)

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


def discuss_primary_workspace(permissions: dict[str, Any] | None) -> Path:
    """Primary cwd for discuss rounds — prefers session-bound book root."""
    from agent_lab.session.guidance import discuss_cwd_from_permissions

    bound = discuss_cwd_from_permissions(permissions)
    if bound is not None:
        return bound
    perms = permissions or {}
    lecture = lecture_script_root()
    if lecture is not None:
        for block in (perms.get("cursor"), perms.get("claude"), perms.get("codex")):
            if block and block.get("local_lecture_script"):
                return lecture
    return primary_workspace(permissions)


def pipeline_root() -> Path | None:
    from agent_lab.app_config import apply_config_env
    from agent_lab.extensions.quant_trading import optional_pipeline_root

    apply_config_env()
    return optional_pipeline_root()


def lecture_script_root() -> Path | None:
    home = Path.home()
    default = home / "Desktop" / "강의 스크립트" / "공수 기말 범위" / "book"
    raw = os.getenv("LECTURE_SCRIPT_ROOT", str(default)).strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if path.is_dir():
        return path.resolve()
    return None


def workspace_label(path: Path) -> str:
    resolved = path.resolve()
    if resolved == project_root().resolve():
        return "agent-lab"
    pipe = pipeline_root()
    if pipe is not None and resolved == pipe:
        return "quant-pipeline"
    lecture = lecture_script_root()
    if lecture is not None and resolved == lecture:
        return "lecture-script"
    if lecture is not None:
        try:
            resolved.relative_to(lecture)
            return "lecture-script"
        except ValueError:
            pass
    return resolved.name or str(resolved)


_LECTURE_BASENAME_HINTS = (
    "lecturenote",
    "extract_lecturenote",
    "build.mjs",
    "lecture.css",
)


def _path_exists_under(root: Path, rel_path: str) -> bool:
    candidate = (root / rel_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return False
    return candidate.is_file()


def _score_root(root: Path, expected_paths: list[str]) -> int:
    return sum(1 for p in expected_paths if _path_exists_under(root, p))


def _basename_suggests_lecture_script(expected_paths: list[str]) -> bool:
    for rel in expected_paths:
        base = Path(rel).name.lower()
        if any(hint in base for hint in _LECTURE_BASENAME_HINTS):
            return True
    return False


def _normalize_expected_paths(
    expected_paths: list[str],
) -> tuple[list[str], Path | None]:
    """Split absolute plan paths into a workspace root hint + relative names."""
    rels: list[str] = []
    explicit_root: Path | None = None
    for raw in filter_file_paths(expected_paths):
        path = Path(raw).expanduser()
        if path.is_absolute():
            if path.is_dir():
                explicit_root = path.resolve()
            elif path.is_file() or looks_like_file_path(raw):
                if explicit_root is None:
                    explicit_root = path.parent.resolve()
                rels.append(path.name)
            continue
        rel = raw.replace("\\", "/")
        if rel.startswith("./"):
            rel = rel[2:]
        rels.append(rel)
    return rels, explicit_root


def _enable_cursor_flag(
    effective: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    cursor = dict(effective.get("cursor") or {})
    if not cursor.get(key):
        cursor[key] = True
        effective["cursor"] = cursor
    return effective


def resolve_execute_workspace(
    permissions: dict[str, Any] | None,
    expected_paths: list[str],
) -> tuple[Path, dict[str, Any]]:
    """Pick cwd for thin execute from expected plan paths and workspace roots."""
    effective: dict[str, Any] = dict(permissions or {})
    rel_paths, explicit_root = _normalize_expected_paths(expected_paths)

    bound = _discuss_cwd_from_permissions(effective)
    if bound is not None and bound.is_dir():
        if not rel_paths or _score_root(bound, rel_paths) >= 0:
            effective = _enable_cursor_flag(effective, "local_custom")
            return bound, effective

    agent_lab = user_agent_lab_root()
    pipe = pipeline_root()
    lecture = lecture_script_root()

    candidates: list[tuple[Path, str, str]] = []
    if agent_lab.is_dir():
        candidates.append((agent_lab, "local_agent_lab", "agent-lab"))
    if pipe is not None:
        candidates.append((pipe, "local_pipeline", "quant-pipeline"))
    if lecture is not None:
        candidates.append((lecture, "local_lecture_script", "lecture-script"))

    if explicit_root is not None:
        for root, perm_key, _ in candidates:
            try:
                explicit_root.relative_to(root)
            except ValueError:
                continue
            effective = _enable_cursor_flag(effective, perm_key)
            return root, effective
        if explicit_root.is_dir():
            effective = _enable_cursor_flag(effective, "local_lecture_script")
            return explicit_root, effective

    best_root = agent_lab
    best_score = -1
    best_perm = "local_agent_lab"
    for root, perm_key, _ in candidates:
        score = _score_root(root, rel_paths)
        if score > best_score:
            best_root, best_score, best_perm = root, score, perm_key

    if best_score == 0 and rel_paths and _basename_suggests_lecture_script(rel_paths):
        if lecture is not None:
            best_root, best_perm = lecture, "local_lecture_script"

    effective = _enable_cursor_flag(effective, best_perm)
    return best_root, effective


def execute_workspace_info(
    permissions: dict[str, Any] | None,
    expected_paths: list[str],
) -> dict[str, Any]:
    cwd, _ = resolve_execute_workspace(permissions, expected_paths)
    return workspace_path_info(cwd, expected_paths)


def workspace_path_info(cwd: Path, expected_paths: list[str]) -> dict[str, Any]:
    """Path existence check for an explicit execute cwd (no re-resolution)."""
    cwd = cwd.resolve()
    rel_paths, _ = _normalize_expected_paths(expected_paths)
    found: list[str] = []
    missing: list[str] = []
    for rel in rel_paths:
        if _path_exists_under(cwd, rel):
            found.append(rel)
        else:
            missing.append(rel)
    return {
        "path": str(cwd),
        "label": workspace_label(cwd),
        "paths_found": found,
        "paths_missing": missing,
    }


def workspace_roots_block(permissions: dict[str, Any] | None) -> str:
    roots = resolve_workspace_roots(permissions)
    lines = "\n".join(f"  - {p}" for p in roots)
    return f"Workspace roots (Cursor / Codex / Claude):\n{lines}"
