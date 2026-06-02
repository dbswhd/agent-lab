from collections.abc import Callable
from typing import Any

from agent_lab import claude_cli
from agent_lab.agents.prompts import CLAUDE_ROOM, claude_handoff_block


def is_available() -> bool:
    return claude_cli.is_available()


def respond(
    system: str,
    user: str,
    *,
    permissions: dict[str, Any] | None = None,
    scribe: bool = False,
    on_activity: Callable[[str], None] | None = None,
) -> str:
    parts = [system or CLAUDE_ROOM]
    handoff = claude_handoff_block()
    if handoff:
        parts.append(handoff)
    # Permissions live in room user payload [고정 constraints] — avoid duplicating in system.
    system_block = "\n\n".join(parts)
    return claude_cli.invoke(
        system_block,
        user,
        permissions=permissions,
        scribe=scribe,
        on_activity=on_activity,
    )
