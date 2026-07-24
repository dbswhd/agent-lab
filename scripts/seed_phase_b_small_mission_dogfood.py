#!/usr/bin/env python3
"""Seed Small Mission dogfood sessions for Phase B (MC-TT) B1–B4 surfaces.

Sessions (English → Dogfood tab):
  - phase-b-small-gate      HUMAN_PENDING + cost ledger + open decision_latency
  - phase-b-small-evidence  pending_approval + diff/oracle for evidence strip

Usage:
  .venv/bin/python scripts/seed_phase_b_small_mission_dogfood.py --sessions-dir /tmp/phase-b-small
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

PLAN_MD = """## Goal
Phase B Small Mission dogfood — Time-to-trust surfaces.

## Now
1.
   - What: exercise B1–B4 chips and evidence strip
   - Where: `web/e2e/phase-b-small-mission-dogfood.spec.ts`
   - Verify: live Playwright green
"""

SESSIONS: tuple[tuple[str, str], ...] = (
    ("phase-b-small-gate", "Phase B small gate"),
    ("phase-b-small-evidence", "Phase B small evidence"),
)


def _init_folder(sessions_root: Path, session_id: str, topic: str) -> Path:
    folder = sessions_root / session_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "topic.txt").write_text(topic + "\n", encoding="utf-8")
    (folder / "chat.jsonl").write_text("", encoding="utf-8")
    (folder / "plan.md").write_text(PLAN_MD, encoding="utf-8")
    return folder


def _base_run(topic: str, session_id: str) -> dict[str, Any]:
    return {
        "_session_id": session_id,
        "topic": topic,
        "status": "idle",
        "workflow_id": "room.parallel",
        "agents": ["cursor", "codex", "claude"],
        "actions": [
            {
                "action_id": "plan-action-now-1",
                "index": 1,
                "kind": "now",
                "what": "Phase B Small Mission dogfood",
                "where": "web/e2e/phase-b-small-mission-dogfood.spec.ts",
                "verify": "npx playwright test e2e/phase-b-small-mission-dogfood.spec.ts",
            }
        ],
        "executions": [],
        "human_inbox": [],
        "cost_ledger": {
            "cumulative": {"usd": 1.25, "tokens": 12000},
            "by_provider": {"mock": {"usd": 1.25}},
        },
    }


def _seed_gate(folder: Path, topic: str) -> None:
    from agent_lab.plan.workflow_state import set_plan_workflow_phase
    from agent_lab.run.meta import write_run_meta

    write_run_meta(folder, _base_run(topic, folder.name))
    # Opens decision_latency + HUMAN_PENDING → Waiting chip + Needs input age.
    set_plan_workflow_phase(folder, "HUMAN_PENDING")


def _seed_evidence(folder: Path, topic: str) -> None:
    from agent_lab.plan.workflow_state import set_plan_workflow_phase
    from agent_lab.run.meta import write_run_meta

    run = _base_run(topic, folder.name)
    run["executions"] = [
        {
            "id": "exec-phase-b-evidence",
            "action_id": "plan-action-now-1",
            "action_index": 1,
            "action_kind": "now",
            "action_what": "Phase B evidence strip",
            "action_where": "phase-b-evidence.txt",
            "action_verify": "UI strip",
            "status": "pending_approval",
            "isolation_effective": "snapshot_override",
            "workspace_root": str(folder),
            "workspace_label": "phase-b-small",
            "expected_paths": ["phase-b-evidence.txt"],
            "touched_paths": ["phase-b-evidence.txt", "phase-b-extra.txt"],
            "source_touched_paths": ["phase-b-evidence.txt"],
            "empty_source_diff": False,
            "needs_artifact_review": False,
            "diff_stat": " phase-b-evidence.txt | 2 +\n 1 file changed, 2 insertions(+)",
            "diff": (
                "diff --git a/phase-b-evidence.txt b/phase-b-evidence.txt\n"
                "--- /dev/null\n+++ b/phase-b-evidence.txt\n"
                "@@ -0,0 +1,2 @@\n+PHASE_B\n+EVIDENCE\n"
            ),
            "oracle": {"verdict": "pass", "detail": "mock ok"},
            "oracle_verdict": "pass",
            "draft_summary": "Phase B evidence pending",
            "executor_label": "Cursor",
        }
    ]
    write_run_meta(folder, run)
    set_plan_workflow_phase(folder, "APPROVED")


def seed_all(sessions_root: Path) -> dict[str, Any]:
    sessions_root.mkdir(parents=True, exist_ok=True)
    seeded: list[dict[str, str]] = []
    for session_id, topic in SESSIONS:
        folder = _init_folder(sessions_root, session_id, topic)
        if session_id.endswith("gate"):
            _seed_gate(folder, topic)
        else:
            _seed_evidence(folder, topic)
        seeded.append({"id": session_id, "topic": topic})
    return {
        "ok": True,
        "sessions_dir": str(sessions_root.resolve()),
        "sessions": seeded,
        "profile": "small",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(seed_all(args.sessions_dir), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
