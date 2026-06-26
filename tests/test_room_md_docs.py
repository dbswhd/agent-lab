"""Room + MD system design docs stay aligned with shipped state."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOM = ROOT / "docs" / "archive" / "rfcs" / "ROOM-REINFORCEMENT.md"
MD_SYSTEM = ROOT / "docs" / "archive" / "legacy" / "MD-SYSTEM-DESIGN.md"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing doc: {path}"
    return path.read_text(encoding="utf-8")


def test_room_reinforcement_shipped_queue_empty():
    text = _read(ROOM)
    assert "implementation queue is empty" in text.lower()
    assert "EXTERNAL-REFS-TRACEABILITY.md" in text
    assert "20" in text and "smoke" in text.lower()
    assert "E2-analyze" in text
    assert "Phase E" in text and "✅ Shipped" in text


def test_md_system_design_tracked_and_repo_shipped():
    text = _read(MD_SYSTEM)
    assert "MD-WRITING-PLAN.md" in text
    assert "EXTERNAL-REFS-TRACEABILITY.md" in text
    assert "Agent Lab repo" in text and "shipped" in text.lower()
    assert "CC-CLAUDE" in text
    assert "⬜ per workspace" in text or "workspace" in text.lower()
    assert "routers/ 분리 예정" not in text
