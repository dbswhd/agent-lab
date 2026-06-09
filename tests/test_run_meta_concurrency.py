"""run.json patch safety under parallel agent writes."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent_lab.run_meta import patch_run_meta, read_run_meta, write_run_meta


def test_parallel_patch_run_meta_preserves_mission_loop(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    write_run_meta(
        folder,
        {
            "workflow_id": "room.parallel",
            "mission_loop": {"enabled": True, "phase": "DISCUSS"},
            "completed_steps": [],
        },
    )

    def _record(agent: str) -> None:
        patch_run_meta(
            folder,
            lambda run: {
                **run,
                "completed_steps": [
                    *(run.get("completed_steps") or []),
                    {"step": f"turn_1_round_1_{agent}", "agent": agent},
                ],
            },
        )

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(_record, ["cursor", "codex", "claude"]))

    run = read_run_meta(folder)
    assert run.get("mission_loop", {}).get("enabled") is True
    assert len(run.get("completed_steps") or []) == 3
