#!/usr/bin/env python3
"""Seed four Wave B live browser-acceptance sessions into a sessions dir.

Writes disposable session folders (English topics → Dogfood tab) for:
  - wave-b-live-plan-reject   (HUMAN_PENDING plan)
  - wave-b-live-diff-approve  (pending_approval execution, non-worktree)
  - wave-b-live-oracle-repair (merged + Oracle fail → RecoveryStrip)
  - wave-b-live-human-resume  (pending inbox question + decision_version)

Usage:
  .venv/bin/python scripts/seed_wave_b_live_sessions.py --sessions-dir /tmp/wave-b-live
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
Wave B live browser acceptance.

## Now
1.
   - What: exercise Decision Queue CTAs
   - Where: `web/e2e/wave-b-live-journey.spec.ts`
   - Verify: live Playwright green
"""

SESSIONS: tuple[tuple[str, str], ...] = (
    ("wave-b-live-plan-reject", "Wave B live plan reject"),
    ("wave-b-live-diff-approve", "Wave B live diff approve"),
    ("wave-b-live-oracle-repair", "Wave B live Oracle repair"),
    ("wave-b-live-human-resume", "Wave B live human resume"),
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
                "what": "Wave B live journey",
                "where": "web/e2e/wave-b-live-journey.spec.ts",
                "verify": "npx playwright test e2e/wave-b-live-journey.spec.ts",
            }
        ],
        "executions": [],
        "human_inbox": [],
    }


def _seed_plan_reject(folder: Path, topic: str) -> None:
    from agent_lab.plan.workflow_state import set_plan_workflow_phase
    from agent_lab.run.meta import write_run_meta

    write_run_meta(folder, _base_run(topic, folder.name))
    set_plan_workflow_phase(folder, "HUMAN_PENDING")


def _seed_diff_approve(folder: Path, topic: str) -> None:
    from agent_lab.plan.workflow_state import set_plan_workflow_phase
    from agent_lab.run.meta import write_run_meta

    run = _base_run(topic, folder.name)
    run["executions"] = [
        {
            "id": "exec-wave-b-diff",
            "action_id": "plan-action-now-1",
            "action_index": 1,
            "action_kind": "now",
            "action_what": "Wave B live diff approve",
            "action_where": "wave-b-live.txt",
            "action_verify": "UI approve",
            "status": "pending_approval",
            "isolation_effective": "snapshot_override",
            "workspace_root": str(folder),
            "workspace_label": "wave-b-live",
            "expected_paths": ["wave-b-live.txt"],
            "touched_paths": ["wave-b-live.txt"],
            "source_touched_paths": ["wave-b-live.txt"],
            "empty_source_diff": False,
            "needs_artifact_review": False,
            "diff_stat": " wave-b-live.txt | 1 +\n 1 file changed, 1 insertion(+)",
            "diff": (
                "diff --git a/wave-b-live.txt b/wave-b-live.txt\n"
                "--- /dev/null\n+++ b/wave-b-live.txt\n"
                "@@ -0,0 +1 @@\n+WAVE_B_LIVE\n"
            ),
            "draft_summary": "Wave B live pending diff",
            "executor_label": "Cursor",
        }
    ]
    write_run_meta(folder, run)
    set_plan_workflow_phase(folder, "APPROVED")


def _seed_oracle_repair(folder: Path, topic: str) -> None:
    """Seed pending_approval + Oracle fail so ExecuteQueueBar shows 재검증.

    Full worktree repair E2E is out of scope for Wave B browser acceptance
    (MOCK_AGENTS does not short-circuit Cursor SDK repair). Live Playwright
    asserts the CTA posts ``/execute/reverify``; the API may return 409
    (execution not merged) which still proves UI→API wiring.
    """
    from agent_lab.plan.workflow_state import set_plan_workflow_phase
    from agent_lab.run.meta import write_run_meta

    run = _base_run(topic, folder.name)
    run["executions"] = [
        {
            "id": "exec-wave-b-oracle",
            "action_id": "plan-action-now-1",
            "action_index": 1,
            "action_kind": "now",
            "action_what": "Wave B live Oracle repair",
            "action_where": "wave-b-oracle.txt",
            "action_verify": "pytest",
            "status": "pending_approval",
            "isolation_effective": "snapshot_override",
            "workspace_root": str(folder),
            "oracle": {"verdict": "fail", "detail": "tests failed (live seed)"},
            "oracle_verdict": "fail",
            "verify_retries": 0,
            "needs_artifact_review": False,
            "diff_stat": "1 file changed",
            "touched_paths": ["wave-b-oracle.txt"],
            "diff": "diff --git a/wave-b-oracle.txt b/wave-b-oracle.txt\n+fail\n",
            "executor_label": "Cursor",
            "draft_summary": "Wave B live Oracle fail pending",
        }
    ]
    write_run_meta(folder, run)
    set_plan_workflow_phase(folder, "APPROVED")


def _seed_human_resume(folder: Path, topic: str) -> None:
    import os

    from agent_lab.human_inbox import create_inbox_item
    from agent_lab.plan.workflow_state import set_plan_workflow_phase
    from agent_lab.run.meta import write_run_meta

    # Enable mission authority for this session so read-model exposes mission_id
    # and inbox answers carry version-guard fields (Wave B §7.3).
    os.environ["AGENT_LAB_MISSION_AUTHORITY"] = "1"
    os.environ["AGENT_LAB_MISSION_AUTHORITY_SESSIONS"] = folder.name

    write_run_meta(folder, {**_base_run(topic, folder.name)})
    set_plan_workflow_phase(folder, "APPROVED")
    create_inbox_item(
        folder,
        kind="question",
        source="wave-b-live-seed",
        prompt="실행 중 어떤 범위로 진행할까요?",
        options=[
            {
                "id": "safe",
                "label": "안전한 범위",
                "description": "변경 영향이 적은 범위만 진행합니다.",
                "recommended": True,
            },
            {
                "id": "full",
                "label": "전체 범위",
                "description": "모든 변경을 한 번에 적용합니다.",
            },
        ],
        summary="Wave B live human resume",
        session_id=folder.name,
    )


def seed_all(sessions_root: Path) -> dict[str, Any]:
    sessions_root.mkdir(parents=True, exist_ok=True)
    seeded: list[dict[str, str]] = []
    for session_id, topic in SESSIONS:
        folder = _init_folder(sessions_root, session_id, topic)
        if session_id.endswith("plan-reject"):
            _seed_plan_reject(folder, topic)
        elif session_id.endswith("diff-approve"):
            _seed_diff_approve(folder, topic)
        elif session_id.endswith("oracle-repair"):
            _seed_oracle_repair(folder, topic)
        else:
            _seed_human_resume(folder, topic)
        seeded.append({"id": session_id, "topic": topic})
    return {
        "ok": True,
        "sessions_dir": str(sessions_root.resolve()),
        "sessions": seeded,
        "authority_allowlist": "wave-b-live-human-resume",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sessions-dir",
        type=Path,
        required=True,
        help="Disposable AGENT_LAB_SESSIONS_DIR root",
    )
    args = parser.parse_args()
    payload = seed_all(args.sessions_dir)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
