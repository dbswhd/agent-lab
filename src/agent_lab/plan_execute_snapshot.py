"""Local file snapshots for thin execute dry-run (no git)."""

from __future__ import annotations

import difflib
import json
import shutil
from pathlib import Path
from typing import Any


from agent_lab.plan_execute_paths import normalize_snapshot_path


def normalize_path(path: str, *, cwd: Path | None = None) -> str:
    """Normalize path for snapshot ops; pass cwd when paths may be absolute."""
    if cwd is None:
        raw = path.strip().replace("\\", "/")
        if raw.startswith("./"):
            raw = raw[2:]
        return raw
    return normalize_snapshot_path(path, cwd=cwd)


def _resolve_under(cwd: Path, rel: str) -> Path:
    norm = normalize_path(rel, cwd=cwd)
    target = (cwd / norm).resolve()
    cwd_resolved = cwd.resolve()
    if target != cwd_resolved and cwd_resolved not in target.parents:
        raise ValueError(f"path escapes workspace: {rel}")
    return target


def parent_dirs(expected_paths: list[str], *, cwd: Path) -> list[str]:
    dirs: set[str] = set()
    for path in expected_paths:
        norm = normalize_path(path, cwd=cwd)
        parent = str(Path(norm).parent)
        if not parent or parent == ".":
            dirs.add(".")
        else:
            dirs.add(parent)
    return sorted(dirs)


def snapshot_dir_for(folder: Path, exec_id: str) -> Path:
    return folder / ".execute-snapshots" / exec_id


def create_snapshot(
    folder: Path,
    *,
    exec_id: str,
    cwd: Path,
    expected_paths: list[str],
) -> dict[str, Any]:
    snap_root = snapshot_dir_for(folder, exec_id)
    files_root = snap_root / "files"
    files_root.mkdir(parents=True, exist_ok=True)

    files_meta: dict[str, dict[str, Any]] = {}
    for rel in expected_paths:
        norm = normalize_path(rel, cwd=cwd)
        target = _resolve_under(cwd, norm)
        if target.is_file():
            dest = files_root / norm
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, dest)
            files_meta[norm] = {
                "existed": True,
                "snapshot_file": f"files/{norm}",
            }
        else:
            files_meta[norm] = {"existed": False}

    dir_listings: dict[str, list[str]] = {}
    for parent in parent_dirs(expected_paths, cwd=cwd):
        parent_path = _resolve_under(cwd, parent)
        if parent_path.is_dir():
            dir_listings[parent] = sorted(entry.name for entry in parent_path.iterdir() if entry.is_file())

    manifest: dict[str, Any] = {
        "exec_id": exec_id,
        "cwd": str(cwd.resolve()),
        "files": files_meta,
        "dir_listings": dir_listings,
    }
    (snap_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def load_manifest(folder: Path, exec_id: str) -> dict[str, Any]:
    path = snapshot_dir_for(folder, exec_id) / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"snapshot manifest not found: {exec_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_current_bytes(cwd: Path, rel: str) -> bytes | None:
    target = _resolve_under(cwd, rel)
    if target.is_file():
        return target.read_bytes()
    return None


def _read_snapshot_bytes(folder: Path, exec_id: str, entry: dict[str, Any]) -> bytes | None:
    if not entry.get("existed"):
        return None
    snap_file = entry.get("snapshot_file")
    if not snap_file:
        return None
    path = snapshot_dir_for(folder, exec_id) / snap_file
    if path.is_file():
        return path.read_bytes()
    return None


def compute_touched_paths(
    folder: Path,
    *,
    exec_id: str,
    cwd: Path,
    manifest: dict[str, Any],
    expected_paths: list[str],
) -> list[str]:
    touched: list[str] = []
    files_meta: dict[str, dict[str, Any]] = manifest.get("files") or {}

    for rel in expected_paths:
        norm = normalize_path(rel, cwd=cwd)
        entry = files_meta.get(norm, {"existed": False})
        before = _read_snapshot_bytes(folder, exec_id, entry)
        after = _read_current_bytes(cwd, norm)
        if before != after:
            touched.append(norm)

    dir_listings: dict[str, list[str]] = manifest.get("dir_listings") or {}
    for parent, before_names in dir_listings.items():
        parent_path = _resolve_under(cwd, parent)
        if not parent_path.is_dir():
            continue
        after_names = {entry.name for entry in parent_path.iterdir() if entry.is_file()}
        before_set = set(before_names)
        for name in sorted(after_names - before_set):
            rel = normalize_path(str(Path(parent) / name), cwd=cwd)
            if rel not in touched:
                touched.append(rel)

    return touched


def _decode_text(data: bytes | None) -> list[str]:
    if data is None:
        return []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return []
    if text.endswith("\n"):
        return text.splitlines(keepends=True)
    if not text:
        return []
    return text.splitlines(keepends=True) + [""]


def unified_diff_for_path(
    folder: Path,
    *,
    exec_id: str,
    cwd: Path,
    rel: str,
    entry: dict[str, Any],
) -> str:
    before = _read_snapshot_bytes(folder, exec_id, entry)
    after = _read_current_bytes(cwd, rel)
    if before == after:
        return ""
    before_lines = _decode_text(before)
    after_lines = _decode_text(after)
    diff_lines = difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=f"a/{rel}",
        tofile=f"b/{rel}",
    )
    return "".join(diff_lines)


def build_diff(
    folder: Path,
    *,
    exec_id: str,
    cwd: Path,
    manifest: dict[str, Any],
    touched_paths: list[str],
) -> tuple[str, str]:
    files_meta: dict[str, dict[str, Any]] = manifest.get("files") or {}
    chunks: list[str] = []
    stat_rows: list[tuple[str, int, int]] = []

    for rel in touched_paths:
        norm = normalize_path(rel, cwd=cwd)
        entry = files_meta.get(norm, {"existed": False})
        chunk = unified_diff_for_path(
            folder,
            exec_id=exec_id,
            cwd=cwd,
            rel=norm,
            entry=entry,
        )
        if chunk:
            chunks.append(chunk if chunk.endswith("\n") else chunk + "\n")
            adds = dels = 0
            for line in chunk.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    adds += 1
                elif line.startswith("-") and not line.startswith("---"):
                    dels += 1
            stat_rows.append((norm, adds, dels))

    diff = "".join(chunks)
    if not stat_rows:
        return diff, ""
    width = max(len(row[0]) for row in stat_rows)
    lines = [f" {row[0].ljust(width)} | +{row[1]} -{row[2]}" for row in stat_rows]
    total_adds = sum(row[1] for row in stat_rows)
    total_dels = sum(row[2] for row in stat_rows)
    summary = f" {len(stat_rows)} file(s) changed, {total_adds} insertion(s)(+), {total_dels} deletion(s)(-)"
    return diff, "\n".join(lines) + "\n" + summary


def restore_snapshot(
    folder: Path,
    *,
    exec_id: str,
    cwd: Path,
    manifest: dict[str, Any],
) -> None:
    files_meta: dict[str, dict[str, Any]] = manifest.get("files") or {}
    snap_root = snapshot_dir_for(folder, exec_id)

    for rel, entry in files_meta.items():
        norm = normalize_path(rel, cwd=cwd)
        target = _resolve_under(cwd, norm)
        if entry.get("existed"):
            snap_file = entry.get("snapshot_file")
            if not snap_file:
                continue
            src = snap_root / snap_file
            if src.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
            elif target.is_file():
                target.unlink()
        elif target.is_file():
            target.unlink()

    dir_listings: dict[str, list[str]] = manifest.get("dir_listings") or {}
    expected_norm = {normalize_path(p, cwd=cwd) for p in files_meta}
    for parent, before_names in dir_listings.items():
        parent_path = _resolve_under(cwd, parent)
        if not parent_path.is_dir():
            continue
        before_set = set(before_names)
        for entry in parent_path.iterdir():
            if not entry.is_file():
                continue
            rel = normalize_path(str(entry.relative_to(cwd.resolve())), cwd=cwd)
            if rel in expected_norm:
                continue
            if entry.name not in before_set:
                entry.unlink()


def delete_snapshot(folder: Path, exec_id: str) -> None:
    snap_root = snapshot_dir_for(folder, exec_id)
    if snap_root.is_dir():
        shutil.rmtree(snap_root)
    parent = snap_root.parent
    if parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()
