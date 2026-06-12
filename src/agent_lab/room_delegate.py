"""Scoped DELEGATE — single-agent sub-call with artifact (Phase G3).

Backward-compatible re-exports; implementation lives in room_dispatch (CMD-RDP).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from agent_lab.room_dispatch import parse_delegate_from_message, run_single_delegate

__all__ = ["parse_delegate_from_message", "run_delegate_turn"]


def run_delegate_turn(
    *,
    topic: str,
    messages: list[Any],
    run_meta: dict[str, Any],
    folder: Path,
    agent: str,
    prompt: str,
    permissions: dict | None,
    on_event: Callable[[str, dict[str, Any]], None] | None = None,
    human_turn: int = 1,
) -> tuple[list[Any], dict[str, Any]]:
    """One agent call; store artifact + peer summary. Replaces full room round."""
    return run_single_delegate(
        topic=topic,
        messages=messages,
        run_meta=run_meta,
        folder=folder,
        agent=agent,
        prompt=prompt,
        permissions=permissions,
        on_event=on_event,
        human_turn=human_turn,
    )
