"""Slash command feedback uses round-divider transcript chrome."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def test_slash_command_divider_in_transcript_and_composer() -> None:
    bubble = _read("web", "src", "components", "ChatBubble.tsx")
    slash_execute = _read("web", "src", "hooks", "useRoomSlashExecute.ts")
    composer_shell = _read("web", "src", "components", "RoomChatComposerShell.tsx")
    divider = _read("web", "src", "components", "SlashCommandDivider.tsx")
    assert "SlashCommandDivider" in bubble
    assert "[slash]" in bubble
    assert "[slash]" in slash_execute
    assert "SlashCommandDivider" in composer_shell
    assert "round-divider" in divider
    assert "SlashCommandNoticeCard" not in bubble


def test_toast_stack_uses_composer_notice_card() -> None:
    host = _read("web", "src", "components", "MacNotificationHost.tsx")
    assert "ComposerNoticeCard" in host
    assert "notify-card" not in host


def test_claude_recovery_action_labels_relogin() -> None:
    recovery = _read("web", "src", "utils", "recoveryItems.ts")
    recovery_handlers = _read("web", "src", "hooks", "useRoomRecoveryHandlers.ts")
    assert "Claude 재로그인" in recovery
    assert 'executeSlashCommand(loginCmd, "claude")' in recovery_handlers
