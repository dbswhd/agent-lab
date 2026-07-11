from __future__ import annotations

from pathlib import Path
from typing import Final

TRACE_SCHEMA_VERSION: Final = 2


def episode_fields(folder: Path | None, human_turn: int | None) -> dict[str, str | int | None]:
    if folder is None:
        return {
            "trace_schema_version": TRACE_SCHEMA_VERSION,
            "episode_id": None,
            "attempt_id": None,
        }
    episode_id = folder.name or str(folder)
    attempt = f"{episode_id}:turn:{human_turn}" if human_turn is not None else f"{episode_id}:sidecar"
    return {
        "trace_schema_version": TRACE_SCHEMA_VERSION,
        "episode_id": episode_id,
        "attempt_id": attempt,
    }
