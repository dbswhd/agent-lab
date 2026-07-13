from __future__ import annotations

import json
from pathlib import Path

from scripts.mission_dogfood_dual_read import project_execute_success_shadow


def test_dogfood_shadow_projection_is_replayable(tmp_path: Path) -> None:
    folder = tmp_path / "dogfood"
    folder.mkdir()
    (folder / "run.json").write_text(
        json.dumps(
            {
                "mission_loop": {"phase": "MISSION_DONE"},
                "plan_workflow": {"phase": "APPROVED", "plan_hash_at_approval": "dogfood"},
                "executions": [
                    {
                        "id": "exec-dogfood-live",
                        "status": "merged",
                        "oracle": {"verdict": "pass"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    project_execute_success_shadow(folder)

    events = (folder / ".agent-lab" / "mission-events.jsonl").read_text(encoding="utf-8")
    assert "PlanApproved" in events
    assert "MergeCommitted" in events
    assert "OraclePassed" in events
