"""PATH and tool env for GUI / minimal-PATH API processes (Tauri, uvicorn)."""

from __future__ import annotations

import glob
import os
from pathlib import Path


def _prepend_path(*dirs: str) -> None:
    cur = os.environ.get("PATH", "")
    parts = [p for p in cur.split(os.pathsep) if p]
    for d in reversed(dirs):
        if d and d not in parts:
            parts.insert(0, d)
    os.environ["PATH"] = os.pathsep.join(parts)


def _candidate_venv_bins() -> list[Path]:
    roots: list[Path] = []
    for key in ("AGENT_LAB_DEV_ROOT", "AGENT_LAB_ROOT"):
        raw = (os.getenv(key) or "").strip()
        if raw:
            roots.append(Path(raw).expanduser())
    try:
        from agent_lab.workspace.roots import project_root, user_agent_lab_root

        roots.append(user_agent_lab_root())
        roots.append(project_root())
    except Exception:
        pass
    home_lab = Path.home() / "Projects" / "agent-lab"
    if home_lab.is_dir():
        roots.append(home_lab)

    seen: set[Path] = set()
    bins: list[Path] = []
    for root in roots:
        root = root.resolve()
        if root in seen:
            continue
        seen.add(root)
        for rel in (
            ".venv/bin",
            "web/src-tauri/bundled-runtime/venv/bin",
            "runtime/venv/bin",
        ):
            candidate = (root / rel).resolve()
            if candidate.is_dir() and candidate not in bins:
                bins.append(candidate)
    return bins


def _candidate_node_bins() -> list[str]:
    out: list[str] = []
    home = Path.home()
    for pattern in (
        str(home / ".nvm/versions/node/*/bin"),
        "/opt/homebrew/bin",
        "/usr/local/bin",
    ):
        if "*" in pattern:
            matches = sorted(glob.glob(pattern), reverse=True)
            out.extend(m for m in matches if Path(m).is_dir())
        elif Path(pattern).is_dir():
            out.append(pattern)
    return out


def _set_cursor_bridge_bin() -> None:
    if (os.getenv("CURSOR_SDK_BRIDGE_BIN") or "").strip():
        return
    try:
        from cursor_sdk._vendor import _bundled_launcher_path, resolve_bridge_path

        bundled = _bundled_launcher_path()
        if bundled is not None:
            os.environ["CURSOR_SDK_BRIDGE_BIN"] = str(bundled)
            return
        os.environ["CURSOR_SDK_BRIDGE_BIN"] = resolve_bridge_path()
    except Exception:
        for venv_bin in _candidate_venv_bins():
            script = venv_bin / "cursor-sdk-bridge"
            if script.is_file():
                # Prefer bundled native launcher inside the wheel, not the console script.
                try:
                    from cursor_sdk._vendor import _bundled_launcher_path

                    bundled = _bundled_launcher_path()
                    if bundled is not None:
                        os.environ["CURSOR_SDK_BRIDGE_BIN"] = str(bundled)
                        return
                except Exception:
                    pass


def _set_cli_bins() -> None:
    from agent_lab import claude_cli, codex_cli

    if not (os.getenv("CODEX_BIN") or "").strip():
        codex = codex_cli.resolve_codex_bin()
        if codex:
            os.environ["CODEX_BIN"] = codex
    if not (os.getenv("CLAUDE_BIN") or "").strip():
        claude = claude_cli.resolve_claude_bin()
        if claude:
            os.environ["CLAUDE_BIN"] = claude


def configure_subprocess_path() -> None:
    """Idempotent: widen PATH and set CURSOR_SDK_BRIDGE_BIN / CODEX_BIN / CLAUDE_BIN."""
    dirs: list[str] = []
    for venv_bin in _candidate_venv_bins():
        dirs.append(str(venv_bin))
    dirs.extend(_candidate_node_bins())
    if dirs:
        _prepend_path(*dirs)
    _set_cursor_bridge_bin()
    _set_cli_bins()
    # Codex is a Node script; ensure node is on PATH even when CODEX_BIN is preset.
    codex = (os.getenv("CODEX_BIN") or "").strip()
    if codex:
        parent = str(Path(codex).expanduser().parent)
        _prepend_path(parent)
