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


def test_slash_picker_keyboard_contract():
    composer = _read("web/src/components/ChatComposer.tsx")
    menu = _read("web/src/components/SlashCommandMenu.tsx")
    for key in ("ArrowDown", "ArrowUp", "PageDown", "PageUp", "Enter", "Escape"):
        assert key in composer
    assert 'role="listbox"' in menu
    assert 'role="option"' in menu
    assert "onHighlightChange" in menu


def test_login_secret_and_auth_panel_contract():
    room = _read("web/src/components/RoomChat.tsx")
    auth = _read("web/src/components/AuthFlowPanel.tsx")
    assert 'type="password"' in room
    assert 'setSecretValue("")' in room
    assert "AuthFlowPanel" in room
    for event in ("output", "auth_url", "completed", "failed", "cancelled"):
        assert event in auth
    assert 'type: "cancel"' in auth


def test_settings_account_surface_is_readonly():
    settings = _read("web/src/components/SettingsPage.tsx")
    panel = _read("web/src/components/ProviderStatusPanel.tsx")
    assert "ProviderStatusPanel" in settings
    assert "AgentCredentialsPanel" not in settings
    assert "보기 전용" in panel
    assert "fetchProviderAuth" in panel
