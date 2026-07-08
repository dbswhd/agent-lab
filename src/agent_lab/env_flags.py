"""Canonical env-var truthy parsing — SSOT for the ``_TRUE``/``env_bool`` idiom
that was independently reimplemented across ~60 modules (2026-07-09 cleanup).

No internal ``agent_lab.*`` imports — safe to import from any module,
including low-level CLI adapters (``claude/cli.py``, ``codex/cli.py``) that
must not depend on higher-level packages.
"""

from __future__ import annotations

import os

TRUTHY = frozenset({"1", "true", "yes", "on"})
FALSY = frozenset({"0", "false", "no", "off"})


def is_truthy(raw: str | None) -> bool:
    """True if ``raw`` (already fetched, e.g. from a param or another lookup)
    is one of the project's truthy string spellings."""
    return (raw or "").strip().lower() in TRUTHY


def is_falsy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in FALSY


def env_bool(name: str, default: bool = False) -> bool:
    """Read an ``AGENT_LAB_*``-style boolean env var. Unset *or* empty-string
    -> ``default`` (matches every pre-existing call site's treatment of
    ``FOO=""`` the same as an absent ``FOO``)."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return is_truthy(raw)


def optional_env_int(*env_keys: str) -> int | None:
    """First set-and-non-empty env var among ``env_keys``, as an int.

    Byte-for-byte the same helper claude/cli.py and codex/cli.py each
    reimplemented as ``_optional_timeout_sec`` (only the docstring differed).
    """
    for key in env_keys:
        raw = (os.getenv(key) or "").strip()
        if raw:
            return int(raw)
    return None
