from __future__ import annotations

from agent_lab.tty_sanitize import sanitize_tty_text


def test_sanitize_tty_text_strips_show_cursor_csi() -> None:
    assert sanitize_tty_text("Login successful.\n\x1b[?25h") == "Login successful.\n"
    assert sanitize_tty_text("[?25h") == ""


def test_sanitize_tty_text_strips_carriage_returns() -> None:
    assert sanitize_tty_text("line\r\n") == "line\n"
