from collections.abc import Callable
from pathlib import Path
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
    on_bridge_event: Any | None = None,
    session_folder: str | Path | None = None,
    request_structured_envelope: bool = False,
    inbox_mcp: bool = False,
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
        on_bridge_event=on_bridge_event,
        session_folder=session_folder,
        request_structured_envelope=request_structured_envelope,
        inbox_mcp=inbox_mcp,
    )
