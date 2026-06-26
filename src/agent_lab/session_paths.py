"""Lightweight SESSIONS_DIR — no heavy dependencies.

Importable without langgraph/langchain_core so test patching works.
Resolved lazily via ``refresh_sessions_dir()`` (called from API bootstrap).
"""

from __future__ import annotations

import os
from pathlib import Path

from agent_lab.app_config import resolve_sessions_dir

SESSIONS_DIR: Path | None = None


def refresh_sessions_dir() -> Path:
    """Resolve and cache the sessions directory from env + config."""
    global SESSIONS_DIR
    from agent_lab.app_config import apply_config_env

    apply_config_env()
    SESSIONS_DIR = Path(os.getenv("AGENT_LAB_SESSIONS_DIR", str(resolve_sessions_dir())))
    return SESSIONS_DIR


def sessions_dir() -> Path:
    """Return SESSIONS_DIR, resolving on first access if bootstrap has not run."""
    return active_sessions_dir()


def active_sessions_dir() -> Path:
    """Resolved sessions root, honoring test patches on deps/session modules."""
    import sys

    for mod_name in ("app.server.deps", "agent_lab.session", "agent_lab.workspace_files"):
        mod = sys.modules.get(mod_name)
        if mod is not None:
            patched = getattr(mod, "SESSIONS_DIR", None)
            if patched is not None:
                return patched
    if SESSIONS_DIR is not None:
        return SESSIONS_DIR
    return refresh_sessions_dir()
