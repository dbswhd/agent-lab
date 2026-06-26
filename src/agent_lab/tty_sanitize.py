"""Strip PTY/CLI control noise from text shown in the UI."""

from __future__ import annotations

import re

# ESC … final byte (CSI, OSC, etc.)
_ANSI_ESCAPE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
# Bare CSI when ESC was dropped (e.g. "[?25h" show-cursor from Claude/Codex CLI)
_BARE_CSI = re.compile(r"\[[\?0-9;]*[a-zA-Z]")


def sanitize_tty_text(text: str) -> str:
    """Remove ANSI cursor/screen control sequences from PTY output."""
    if not text:
        return text
    cleaned = _ANSI_ESCAPE.sub("", text)
    cleaned = _BARE_CSI.sub("", cleaned)
    return cleaned.replace("\r", "")
