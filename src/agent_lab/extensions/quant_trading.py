"""Optional quant-pipeline + agentic-trading integration (extension layer).

Agent-lab core (Room, sessions, agents) must not depend on these repos.
Trading Mission / MCP market tools call into this module and degrade gracefully
when sibling repos are absent.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_EXTENSION = "quant_trading"


def _home() -> Path:
    return Path.home()


def _expand_dir(raw: str) -> Path | None:
    text = (raw or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    return path.resolve() if path.is_dir() else None


def optional_pipeline_root() -> Path | None:
    """Resolve quant research pipeline checkout (optional)."""
    for raw in (
        os.getenv("QUANT_PIPELINE_ROOT", "").strip(),
        str(_home() / "Projects" / "quant-pipeline"),
        str(_home() / "Desktop" / "pipeline"),
    ):
        found = _expand_dir(raw)
        if found is not None:
            return found
    return None


def quant_pipeline_available() -> bool:
    return optional_pipeline_root() is not None


def require_pipeline_root() -> Path:
    root = optional_pipeline_root()
    if root is None:
        raise FileNotFoundError("quant-pipeline extension: set QUANT_PIPELINE_ROOT to the research pipeline checkout")
    return root


def _src_has_quant_pipeline(src: Path) -> bool:
    return (src / "quant_pipeline").is_dir()


def optional_agentic_src() -> Path | None:
    """Resolve quant-agentic-trading (quant_pipeline package) src root (optional)."""
    for key in ("AGENTIC_QUANT_PIPELINE_SRC", "QUANT_PIPELINE_AGENTIC_SRC"):
        raw = (os.getenv(key) or "").strip()
        if raw:
            path = Path(raw).expanduser().resolve()
            if _src_has_quant_pipeline(path):
                return path

    pipeline = optional_pipeline_root()
    candidates: list[Path] = [
        _home() / "Projects" / "quant-agentic-trading" / "src",
        _home() / "Documents" / "New project" / "src",
        _home() / "Projects" / "quant-pipeline" / "src",
    ]
    if pipeline is not None:
        candidates.insert(0, pipeline / "src")

    for path in candidates:
        resolved = path.expanduser().resolve()
        if _src_has_quant_pipeline(resolved):
            return resolved
    return None


def agentic_trading_available() -> bool:
    return optional_agentic_src() is not None


def require_agentic_src() -> Path:
    src = optional_agentic_src()
    if src is None:
        raise FileNotFoundError(
            "agentic-trading extension: set AGENTIC_QUANT_PIPELINE_SRC to quant-agentic-trading/src"
        )
    return src


def optional_agentic_db() -> Path | None:
    """Resolve control-plane SQLite (optional; extension ingest only)."""
    for key in ("AGENTIC_TRADING_DB", "CONTROL_PLANE_DB"):
        raw = (os.getenv(key) or "").strip()
        if raw:
            path = Path(raw).expanduser().resolve()
            if path.is_file():
                return path
            return path

    for candidate in (
        _home() / "Projects" / "quant-agentic-trading" / "data" / "agentic_trading" / "control_plane.sqlite3",
        _home() / "Documents" / "New project" / "data" / "agentic_trading" / "control_plane.sqlite3",
        _home() / ".agent-lab" / "control_plane.sqlite3",
    ):
        if candidate.is_file():
            return candidate.resolve()
    return None


def extension_unavailable(
    extension: str,
    reason: str,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Standard MCP / tool response when an optional extension repo is missing."""
    payload: dict[str, Any] = {
        "ok": False,
        "extension": extension,
        "reason": reason,
        "hint": "Install/configure the quant extension repos or set the documented env vars.",
    }
    if extra:
        payload.update(extra)
    return payload
