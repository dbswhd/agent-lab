"""CC-hooks: Claude Code dev-tool hooks in .claude/settings.json."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / ".claude" / "settings.json"
HOOKS = ROOT / ".claude" / "hooks"


def test_claude_settings_has_post_edit_and_stop():
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    hooks = data["hooks"]
    assert "PostEdit" in hooks
    assert "Stop" in hooks
    post = hooks["PostEdit"]
    matchers = {entry.get("matcher") for entry in post}
    assert "*.py" in matchers
    assert "*.tsx" in matchers


def test_claude_hook_scripts_exist_and_executable():
    for name in ("post-edit-ruff.sh", "post-edit-prettier.sh", "stop-pytest.sh"):
        path = HOOKS / name
        assert path.is_file(), name
        assert path.stat().st_mode & 0o111, f"{name} should be executable"
