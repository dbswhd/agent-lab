"""Mission / runtime → discuss invocations."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

OnAgentEvent = Callable[[str, dict[str, Any]], None]


def continue_room_round(
    folder: Path,
    user_message: str,
    *,
    agents: list[str] | None = None,
    synthesize: bool = False,
    parallel_rounds: int = 1,
    permissions: dict[str, Any] | None = None,
    turn_profile: str = "discuss",
    research_mode: bool = False,
    on_event: OnAgentEvent | None = None,
    **kwargs: Any,
) -> tuple[list[Any], str]:
    from agent_lab.room import continue_room_round as _continue

    return _continue(
        folder,
        user_message,
        agents=agents,  # type: ignore[arg-type]
        synthesize=synthesize,
        parallel_rounds=parallel_rounds,
        permissions=permissions,
        turn_profile=turn_profile,
        research_mode=research_mode,
        on_event=on_event,
        **kwargs,
    )
