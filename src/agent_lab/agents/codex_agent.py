from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent_lab import codex_cli
from agent_lab.agents.prompts import CODEX_ROOM


def is_available() -> bool:
    return codex_cli.is_available()


def respond_session(
    system: str,
    prompts: list[str],
    *,
    permissions: dict | None = None,
    on_activity: Any | None = None,
    room_turn: bool = True,
    session_folder: str | Path | None = None,
    inbox_mcp: bool = False,
    gate_after: int | None = None,
    gate: Callable[[], bool] | None = None,
    extra_prompts_if_gate: list[str] | None = None,
    request_structured_envelope: bool = False,
) -> str:
    """Persistent Codex execution — plan-first gate matches ``cursor_agent.respond_session``."""
    bodies = [p.strip() for p in prompts if p and p.strip()]
    if not bodies:
        raise ValueError("respond_session requires at least one prompt")
    last = codex_cli.invoke(
        system or CODEX_ROOM,
        bodies[0],
        permissions=permissions,
        on_activity=on_activity,
        room_turn=room_turn,
        session_folder=session_folder,
        inbox_mcp=inbox_mcp,
        request_structured_envelope=request_structured_envelope,
    )
    if (
        gate_after is not None
        and gate_after == 0
        and gate is not None
        and extra_prompts_if_gate
        and gate()
    ):
        combined = "\n\n---\n\n".join(p.strip() for p in extra_prompts_if_gate if p.strip())
        if combined:
            last = codex_cli.invoke(
                system or CODEX_ROOM,
                combined,
                permissions=permissions,
                on_activity=on_activity,
                room_turn=False,
                session_folder=session_folder,
                inbox_mcp=inbox_mcp,
                request_structured_envelope=request_structured_envelope,
            )
    return last


def respond(
    system: str,
    user: str,
    *,
    permissions: dict | None = None,
    on_activity: Any | None = None,
    room_turn: bool = True,
    session_folder: str | Path | None = None,
    inbox_mcp: bool = False,
    request_structured_envelope: bool = False,
) -> str:
    return respond_session(
        system or CODEX_ROOM,
        [user],
        permissions=permissions,
        on_activity=on_activity,
        room_turn=room_turn,
        session_folder=session_folder,
        inbox_mcp=inbox_mcp,
        request_structured_envelope=request_structured_envelope,
    )
