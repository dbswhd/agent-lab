"""Read/write run.json without a full room turn."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


def read_run_meta(folder: Path) -> dict[str, Any]:
    run_path = folder / "run.json"
    if not run_path.is_file():
        return {}
    try:
        return json.loads(run_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


_EPHEMERAL_RUN_KEYS = frozenset(
    {
        "_session_folder",
        "_session_id",
        "_active_turn_mode",
        "_active_synthesize",
        "_active_consensus",
    }
)


def persist_run_meta(run: dict[str, Any]) -> dict[str, Any]:
    """Drop in-memory-only keys before writing run.json."""
    return {k: v for k, v in run.items() if k not in _EPHEMERAL_RUN_KEYS}


def write_run_meta(folder: Path, run: dict[str, Any]) -> None:
    (folder / "run.json").write_text(
        json.dumps(persist_run_meta(run), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def patch_run_meta(
    folder: Path,
    updater: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    run = read_run_meta(folder)
    updated = updater(run)
    write_run_meta(folder, updated)
    return updated
