"""Adversarial gate for dry-run approve (mock-first; live Claude opt-in)."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

LGTM_TOKEN = "LGTM"
_MAX_DIFF = 2000


def mock_adversarial_note(*, action_what: str, diff: str) -> str:
    """Fixture-safe stand-in; no Claude/subprocess calls."""
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


def _prompt(*, action_what: str, action_verify: str, diff: str) -> str:
    snippet = (diff or "")[:_MAX_DIFF]
    return (
        f"다음 변경을 실행하려 합니다.\n\n"
        f"목적: {action_what}\n"
        f"검증 기준: {action_verify}\n\n"
        f"diff (요약):\n{snippet}\n\n"
        f"이 실행이 의도와 다르거나 실패할 수 있는 이유를 "
        f"최대 3가지만 간결하게 쓰세요. 없으면 '{LGTM_TOKEN}'만 쓰세요."
    )


def adversarial_review(
    *,
    action_what: str,
    action_verify: str,
    diff: str,
    adversarial_call: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """Return ``{note, source}`` for execution evidence (non-blocking)."""
    prompt = _prompt(
        action_what=action_what,
        action_verify=action_verify,
        diff=diff,
    )
    if adversarial_call is not None:
        raw = adversarial_call(prompt)
        source = "injected"
    elif os.getenv("AGENT_LAB_ADVERSARIAL_LIVE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        from agent_lab import claude_cli

        raw = claude_cli.invoke("adversarial-reviewer", prompt, scribe=True)
        source = "live"
    else:
        raw = mock_adversarial_note(action_what=action_what, diff=diff)
        source = "mock"
    note = str(raw or LGTM_TOKEN).strip() or LGTM_TOKEN
    return {"note": note, "source": source}
