from __future__ import annotations

from pathlib import Path


def test_slash_command_groups_util_exists() -> None:
    path = Path(__file__).resolve().parents[1] / "web/src/utils/slashCommandGroups.ts"
    text = path.read_text(encoding="utf-8")
    assert "groupSlashCommands" in text
    assert "defaultSlashGroupOpen" in text


def test_slash_command_group_list_component() -> None:
    path = Path(__file__).resolve().parents[1] / "web/src/components/SlashCommandGroupList.tsx"
    text = path.read_text(encoding="utf-8")
    assert "plugin-agent-group" in text
    assert "maxPerAgentGroup" in text
