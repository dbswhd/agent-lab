"""MD-PLATFORM: PLATFORM.md injection."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_platform_md_file_exists():
    path = ROOT / ".agent-lab" / "PLATFORM.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "Speech-act" in text
    assert len(text) <= 1000


def test_platform_injection_cap():
    from agent_lab.platform_md import PLATFORM_INJECT_CAP, read_platform_md_for_injection

    block = read_platform_md_for_injection()
    assert block
    assert len(block) <= PLATFORM_INJECT_CAP


def test_session_guidance_includes_platform():
    from agent_lab.session_guidance import build_session_guidance_block

    block = build_session_guidance_block({})
    assert "PLATFORM.md" in block
    assert "Speech-act" in block
