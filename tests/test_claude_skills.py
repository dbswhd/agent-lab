"""CC-skills: Claude Code skills under .claude/skills/."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".claude" / "skills"


def test_smoke_and_score_skill():
    path = SKILLS / "smoke-and-score" / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    assert "name: smoke-and-score" in text
    assert "make score-session" in text
    assert "smoke_room_e2e" in text or "make smoke-e2e" in text


def test_regression_check_skill():
    path = SKILLS / "regression-check" / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    assert "name: regression-check" in text
    assert "pytest tests/" in text


def test_skill_frontmatter_has_description():
    for sub in ("smoke-and-score", "regression-check"):
        text = (SKILLS / sub / "SKILL.md").read_text(encoding="utf-8")
        assert text.startswith("---\n")
        assert "description:" in text.split("---", 2)[1]
