"""Session plan file paths — keep core plan.md separate from extension plans."""

from __future__ import annotations

from pathlib import Path
from typing import Any

TRADING_MISSION_PLAN_REL = "artifacts/plans/trading-mission.md"
LEGACY_TRADING_SECTION_MARKERS = (
    "ingest_ready",
    "freshness.blocking",
    "proposal_delta.json",
    "kr_kospi_v1",
    "Trading Mission",
)


def session_plan_path(folder: Path) -> Path:
    return folder / "plan.md"


def extension_plan_path(folder: Path, domain: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in domain.strip().lower())
    safe = safe.strip("-") or "extension"
    return folder / "artifacts" / "plans" / f"{safe}.md"


def trading_mission_plan_path(folder: Path) -> Path:
    return folder / TRADING_MISSION_PLAN_REL


def is_trading_mission_run(run_meta: dict[str, Any] | None) -> bool:
    if not isinstance(run_meta, dict):
        return False
    template = str(run_meta.get("session_template") or "").strip().lower()
    if template in {"trading-mission", "trading-thin", "trading-offline"}:
        return True
    mission_kind = str(run_meta.get("mission_kind") or "").strip().lower()
    return mission_kind.startswith("trading")


def read_trading_plan_md(folder: Path) -> str:
    """Prefer extension plan; fall back to legacy plan.md trading sections."""
    ext = trading_mission_plan_path(folder)
    if ext.is_file():
        return ext.read_text(encoding="utf-8")
    legacy = session_plan_path(folder)
    if not legacy.is_file():
        return ""
    text = legacy.read_text(encoding="utf-8")
    if any(marker in text for marker in LEGACY_TRADING_SECTION_MARKERS):
        return text
    return ""


def write_trading_plan_md(folder: Path, content: str) -> Path:
    path = trading_mission_plan_path(folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return path
