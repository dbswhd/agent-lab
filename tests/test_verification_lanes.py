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


def test_core_integration_lane_excludes_quant_extension() -> None:
    makefile = Path("Makefile").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    marker = "integration and not quant and not live and not bridge"
    assert marker in makefile
    assert marker in workflow


def test_makefile_has_opt_in_quant_compatibility_lane() -> None:
    text = Path("Makefile").read_text(encoding="utf-8")

    assert "test-quant:" in text
    assert 'pytest tests/ -q -ra -m "quant and not live"' in text
