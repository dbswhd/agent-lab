"""Mock-only adversarial gate for Layer 4 fixture skeleton (no live LLM)."""

from __future__ import annotations

LGTM_TOKEN = "LGTM"


def mock_adversarial_note(*, action_what: str, diff: str) -> str:
    """Fixture-safe adversarial reviewer stand-in; no Claude/subprocess calls."""
    _ = action_what
    stripped = (diff or "").strip()
    if not stripped:
        return LGTM_TOKEN
    lower = stripped.lower()
    if "todo" in lower or "fixme" in lower:
        return "Diff contains TODO/FIXME markers that may ship incomplete work."
    return LGTM_TOKEN


def badge_tone(adversarial_note: str) -> str:
    """Non-blocking UI badge tone: lgtm (green) vs warning (yellow)."""
    note = (adversarial_note or "").strip()
    if not note or note.upper() == LGTM_TOKEN:
        return "lgtm"
    return "warning"
