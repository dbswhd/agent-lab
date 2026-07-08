"""Session-scoped native hook configs (Codex / Claude / Cursor) — Phase 4 passthrough."""

from __future__ import annotations

import json
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, cast

from agent_lab.env_flags import env_bool


def agent_hooks_root(session_folder: Path) -> Path:
    return session_folder / ".agent-lab" / "agent-hooks"


def _native_hooks_enabled() -> bool:
    return env_bool("AGENT_LAB_NATIVE_HOOKS")


def write_codex_hooks(session_folder: Path, hooks: dict[str, Any]) -> Path:
    root = agent_hooks_root(session_folder) / "codex"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "hooks.json"
    path.write_text(json.dumps(hooks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def write_cursor_hooks(session_folder: Path, hooks: dict[str, Any]) -> Path:
    root = agent_hooks_root(session_folder) / "cursor"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "hooks.json"
    path.write_text(json.dumps(hooks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def write_claude_hooks_fragment(session_folder: Path, hooks: dict[str, Any]) -> Path:
    root = agent_hooks_root(session_folder) / "claude"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "settings.json"
    path.write_text(json.dumps({"hooks": hooks}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def write_manifest(session_folder: Path, manifest: dict[str, Any]) -> Path:
    root = agent_hooks_root(session_folder)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def materialize_agent_hooks(
    session_folder: Path,
    *,
    codex: dict[str, Any] | None = None,
    cursor: dict[str, Any] | None = None,
    claude: dict[str, Any] | None = None,
    enabled_agents: list[str] | None = None,
) -> dict[str, str]:
    written: dict[str, str] = {}
    agents = list(enabled_agents or [])
    if codex is not None:
        p = write_codex_hooks(session_folder, codex)
        written["codex"] = str(p.relative_to(session_folder))
        if "codex" not in agents:
            agents.append("codex")
    if cursor is not None:
        p = write_cursor_hooks(session_folder, cursor)
        written["cursor"] = str(p.relative_to(session_folder))
        if "cursor" not in agents:
            agents.append("cursor")
    if claude is not None:
        p = write_claude_hooks_fragment(session_folder, claude)
        written["claude"] = str(p.relative_to(session_folder))
        if "claude" not in agents:
            agents.append("claude")
    manifest_path = write_manifest(
        session_folder,
        {"agents": agents, "paths": written},
    )
    written["manifest"] = str(manifest_path.relative_to(session_folder))
    return written


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_json_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _resolve_template_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if path.is_file():
        return path
    return _repo_root() / raw


def _load_agent_hook_template(section: dict[str, Any], key: str) -> dict[str, Any] | None:
    raw = section.get(key)
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        return _load_json_file(_resolve_template_path(raw.strip()))
    return None


def ensure_session_agent_hooks_from_config(session_folder: Path) -> dict[str, Any] | None:
    manifest_path = agent_hooks_root(session_folder) / "manifest.json"
    if manifest_path.is_file():
        try:
            return cast(dict[str, Any], json.loads(manifest_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass

    from agent_lab.room.hooks import load_hooks_config

    cfg = load_hooks_config()
    section = cfg.get("agent_hooks")
    if not isinstance(section, dict) or section.get("enabled") is False:
        return None

    codex_hooks = _load_agent_hook_template(section, "codex")
    cursor_hooks = _load_agent_hook_template(section, "cursor")
    claude_raw = section.get("claude")
    claude_hooks: dict[str, Any] | None = None
    if isinstance(claude_raw, dict):
        claude_hooks = claude_raw.get("hooks", claude_raw)
    elif isinstance(claude_raw, str) and claude_raw.strip():
        loaded = _load_json_file(_resolve_template_path(claude_raw.strip()))
        if loaded is not None:
            claude_hooks = loaded.get("hooks", loaded)

    if codex_hooks is None and cursor_hooks is None and claude_hooks is None:
        return None

    written = materialize_agent_hooks(
        session_folder,
        codex=codex_hooks,
        cursor=cursor_hooks,
        claude=claude_hooks if isinstance(claude_hooks, dict) else None,
    )
    manifest = json.loads((agent_hooks_root(session_folder) / "manifest.json").read_text(encoding="utf-8"))
    return {"agents": manifest.get("agents", []), "paths": written}


def codex_hooks_source(session_folder: Path | None) -> Path | None:
    if session_folder is None:
        return None
    src = agent_hooks_root(Path(session_folder)) / "codex" / "hooks.json"
    return src if src.is_file() else None


def cursor_hooks_source(session_folder: Path | None) -> Path | None:
    if session_folder is None:
        return None
    src = agent_hooks_root(Path(session_folder)) / "cursor" / "hooks.json"
    return src if src.is_file() else None


def claude_hooks_source(session_folder: Path | None) -> Path | None:
    if session_folder is None:
        return None
    src = agent_hooks_root(Path(session_folder)) / "claude" / "settings.json"
    return src if src.is_file() else None


@contextmanager
def _stage_file_overlay(src: Path, dest: Path) -> Iterator[None]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    had_dest = dest.is_file()
    backup = dest.read_bytes() if had_dest else None
    shutil.copy2(src, dest)
    try:
        yield
    finally:
        if had_dest:
            if backup is not None:
                dest.write_bytes(backup)
        elif dest.is_file():
            dest.unlink()


@contextmanager
def native_codex_hooks_overlay(
    session_folder: str | Path | None,
    cwd: str,
) -> Iterator[None]:
    if not _native_hooks_enabled():
        yield
        return
    src = codex_hooks_source(Path(session_folder) if session_folder is not None else None)
    if src is None:
        yield
        return
    with _stage_file_overlay(src, Path(cwd) / ".codex" / "hooks.json"):
        yield


@contextmanager
def native_cursor_hooks_overlay(
    session_folder: str | Path | None,
    cwd: str,
) -> Iterator[None]:
    """Cursor SDK has no hooks API — stage ``.cursor/hooks.json`` into workspace cwd."""
    if not _native_hooks_enabled():
        yield
        return
    src = cursor_hooks_source(Path(session_folder) if session_folder is not None else None)
    if src is None:
        yield
        return
    with _stage_file_overlay(src, Path(cwd) / ".cursor" / "hooks.json"):
        yield


@contextmanager
def native_claude_hooks_overlay(
    session_folder: str | Path | None,
    cwd: str,
) -> Iterator[None]:
    if not _native_hooks_enabled():
        yield
        return
    src = claude_hooks_source(Path(session_folder) if session_folder is not None else None)
    if src is None:
        yield
        return
    dest = Path(cwd) / ".claude" / "settings.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    had_dest = dest.is_file()
    backup = dest.read_bytes() if had_dest else None
    try:
        fragment = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        yield
        return
    merged: dict[str, Any] = {}
    if had_dest and backup:
        try:
            existing = json.loads(backup.decode("utf-8"))
            if isinstance(existing, dict):
                merged = dict(existing)
        except json.JSONDecodeError:
            merged = {}
    if isinstance(fragment.get("hooks"), dict):
        merged["hooks"] = fragment["hooks"]
    else:
        merged.update(fragment)
    dest.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        yield
    finally:
        if had_dest:
            if backup is not None:
                dest.write_bytes(backup)
        elif dest.is_file():
            dest.unlink()


@contextmanager
def native_agent_hooks_overlay(
    agent: str,
    session_folder: str | Path | None,
    cwd: str,
) -> Iterator[None]:
    agent_l = str(agent or "").strip().lower()
    if agent_l == "codex":
        with native_codex_hooks_overlay(session_folder, cwd):
            yield
    elif agent_l == "cursor":
        with native_cursor_hooks_overlay(session_folder, cwd):
            yield
    elif agent_l == "claude":
        with native_claude_hooks_overlay(session_folder, cwd):
            yield
    else:
        yield
