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


def write_run_meta(folder: Path, run: dict[str, Any]) -> None:
    (folder / "run.json").write_text(
        json.dumps(run, indent=2, ensure_ascii=False) + "\n",
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
