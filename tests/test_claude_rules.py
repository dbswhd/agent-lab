"""CC-rules: Claude Code path-scoped rules in .claude/rules/."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / ".claude" / "rules"


def test_claude_rules_files_exist():
    for name in ("python-backend.md", "react-frontend.md"):
        path = RULES / name
        assert path.is_file(), name
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\npaths:")
        assert len(text.splitlines()) <= 50, f"{name} should stay under 50 lines"


def test_python_backend_rule_covers_agent_lab():
    text = (RULES / "python-backend.md").read_text(encoding="utf-8")
    assert "src/agent_lab/**/*.py" in text
    assert "patch_run_meta" in text


def test_react_frontend_rule_covers_web():
    text = (RULES / "react-frontend.md").read_text(encoding="utf-8")
    assert "web/src/**/*.tsx" in text
    assert "client.ts" in text
