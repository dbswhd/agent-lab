"""Verification lane contracts."""

from __future__ import annotations

from pathlib import Path


def test_makefile_fast_lane_excludes_bridge_and_live() -> None:
    text = Path("Makefile").read_text(encoding="utf-8")

    assert "--lane fast" in text
    assert "not live and not integration and not bridge" in text


def test_makefile_has_dedicated_bridge_lane() -> None:
    text = Path("Makefile").read_text(encoding="utf-8")

    assert "test-bridge:" in text
    assert "--lane bridge" in text
    assert "bridge and not live" in text
