from typing import Any

from agent_lab import codex_cli
from agent_lab.agents.prompts import CODEX_ROOM


def is_available() -> bool:
    return codex_cli.is_available()


def respond(
    system: str,
    user: str,
    *,
    permissions: dict | None = None,
    on_activity: Any | None = None,
    room_turn: bool = True,
) -> str:
    return codex_cli.invoke(
        system or CODEX_ROOM,
        user,
        permissions=permissions,
        on_activity=on_activity,
        room_turn=room_turn,
    )
