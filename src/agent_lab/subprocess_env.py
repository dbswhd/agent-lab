"""Minimal environment for CLI / bridge child processes (Centaur P0)."""

from __future__ import annotations

import os
from contextlib import contextmanager
from collections.abc import Iterator

_EXACT = frozenset(
    {
        "PATH",
        "HOME",
        "TMPDIR",
        "TMP",
        "TEMP",
        "TERM",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "USER",
        "LOGNAME",
        "SHELL",
        "CODEX_BIN",
        "CLAUDE_BIN",
        "CURSOR_SDK_BRIDGE_BIN",
        "CURSOR_SDK_BRIDGE_URL",
        "CURSOR_SDK_BRIDGE_TOKEN",
        "CURSOR_SDK_BRIDGE_AUTH_TOKEN",
        "CURSOR_API_KEY",
        "OPENAI_API_KEY",
        "AGENT_LAB_ROOT",
        "AGENT_LAB_DEV_ROOT",
        "AGENT_LAB_SESSIONS_DIR",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
    }
)
_PREFIXES = ("AGENT_LAB_", "CLAUDE_", "CODEX_", "CURSOR_")
_EXCLUDE = frozenset({"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"})


def subprocess_env(**overrides: str) -> dict[str, str]:
    """Copy only allowlisted keys from os.environ, then apply overrides."""
    out: dict[str, str] = {}
    for key, value in os.environ.items():
        if key in _EXCLUDE:
            continue
        if key in _EXACT or key.startswith(_PREFIXES):
            out[key] = value
    out.update(overrides)
    return out


@contextmanager
def isolated_process_env(**overrides: str) -> Iterator[None]:
    """Temporarily replace os.environ for SDK subprocess spawn (restore after)."""
    saved = dict(os.environ)
    filtered = subprocess_env(**overrides)
    try:
        os.environ.clear()
        os.environ.update(filtered)
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)
