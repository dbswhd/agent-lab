"""Load `.agent-lab/PLATFORM.md` for agent payload injection."""

from __future__ import annotations

import os
from pathlib import Path

PLATFORM_INJECT_CAP = 500
PLATFORM_FILE_CAP = 1000

_read_cache: dict[Path, tuple[float, str]] = {}


def platform_md_path() -> Path:
    root = (os.getenv("AGENT_LAB_ROOT") or "").strip()
    if root:
        return Path(root) / ".agent-lab" / "PLATFORM.md"
    return Path(__file__).resolve().parents[2] / ".agent-lab" / "PLATFORM.md"


def read_platform_md_for_injection() -> str:
    path = platform_md_path()
    if not path.is_file():
        return ""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return ""
    cached = _read_cache.get(path)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if len(text) > PLATFORM_FILE_CAP:
        text = text[: PLATFORM_FILE_CAP - 1] + "…"
    result = text[:PLATFORM_INJECT_CAP]
    _read_cache[path] = (mtime, result)
    return result
