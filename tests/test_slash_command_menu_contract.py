"""Slash command menu UI contract."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_chat_composer_wires_slash_command_menu():
    text = _read("web/src/components/ChatComposer.tsx")
    assert "SlashCommandMenu" in text
    assert "slashCommands" in text
    assert 'data-testid="slash-command-menu"' in _read("web/src/components/SlashCommandMenu.tsx")


def test_room_chat_fetches_commands_and_plugin_panel():
    room = _read("web/src/components/RoomChat.tsx")
    settings = _read("web/src/components/SettingsPage.tsx")
    assert "fetchCommands" in room
    assert "matchSlashCommand" in room
    assert "PluginPanel" in settings
    assert "runSessionCommand" in room


def test_plugin_panel_contract():
    text = _read("web/src/components/PluginPanel.tsx")
    assert 'data-testid="plugin-panel"' in text
    assert "patchSessionAgentPlugins" in text
    assert "res.agents" in text
    assert "accordionInitRef" in text
    assert "useEffect(() => {\n    setOpenAgents" not in text
