#!/usr/bin/env python3
"""Run one mock mission dogfood session and print KPI report (docs/MISSION-DOGFOOD.md)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("AGENT_LAB_MOCK_AGENTS", "1")
os.environ.setdefault("AGENT_LAB_MISSION_LOOP", "1")

_GOOD_PLAN = """# Plan

## 지금 실행

1. Fix auth module
   - 무엇을: JWT validation in `src/auth.py`
   - 어디서: `src/auth.py`
   - 검증: `make test tests/test_auth.py` and `AUTH_OK` in `src/auth.py`
"""


def _utc_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def run_dogfood(*, sessions_root: Path, session_id: str | None = None) -> Path:
    from agent_lab.mission_loop import pause_mission_loop, resume_mission_loop, run_plan_gate
    from agent_lab.mission_advance import on_verify_result
    from agent_lab.oracle_core import PROMPT_VERSION
    from agent_lab.run_meta import patch_run_meta, read_run_meta
    from agent_lab.verified_loop import (
        approve_verified_loop,
        init_verified_loop,
        record_proposed_goal,
    )

    sid = session_id or f"dogfood-{_utc_slug()}"
    folder = sessions_root / sid
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "topic.txt").write_text("mission dogfood mock run\n", encoding="utf-8")
    (folder / "plan.md").write_text(_GOOD_PLAN, encoding="utf-8")
    (folder / "chat.jsonl").write_text(
        json.dumps(
            {
                "role": "agent",
                "agent": "codex",
                "content": "Discuss: scope auth JWT fix for dogfood.",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (folder / "run.json").write_text(
        json.dumps(
            {
                "workflow_id": "room.parallel",
                "run_schema_version": 1,
                "topic": "mission dogfood",
                "agents": ["cursor", "codex"],
                "status": "active",
                "turns": [{"mode": "discuss", "status": "completed"}],
                "actions": [],
                "approvals": [],
                "executions": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    init_verified_loop(folder)
    record_proposed_goal(
        folder,
        {
            "goal": "Ship JWT auth fix with AUTH_OK marker",
            "completion_promise": "MISSION_DONE",
            "criteria": "tests pass",
        },
        source="dogfood",
    )

    def _pending(run: dict) -> dict:
        run["verified_loop"]["status"] = "pending_approval"
        return run

    patch_run_meta(folder, _pending)
    approve_verified_loop(folder)

    gate = run_plan_gate(folder, _GOOD_PLAN)
    if gate.get("status") != "ok":
        raise RuntimeError(f"plan gate failed: {gate}")

    def _exec_queue(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "enabled": True,
                "phase": "EXECUTE_QUEUE",
                "pending_action_indices": [1],
                "current_action_index": 1,
            }
        )
        return run

    patch_run_meta(folder, _exec_queue)
    pause_mission_loop(folder, reason="dogfood_pause_drill")
    from agent_lab.runtime.snapshot import build_runtime_snapshot

    paused_snap = build_runtime_snapshot(folder)
    if paused_snap.get("boulder", {}).get("resume_phase") != "EXECUTE_QUEUE":
        raise RuntimeError(f"dogfood boulder missing after pause: {paused_snap.get('boulder')}")
    if paused_snap.get("last_failure", {}).get("event") != "mission.pause":
        raise RuntimeError(f"dogfood last_failure missing after pause: {paused_snap.get('last_failure')}")
    resume_mission_loop(folder)
    resumed_snap = build_runtime_snapshot(folder)
    if resumed_snap.get("last_failure") is not None:
        raise RuntimeError("dogfood last_failure should clear after resume")

    def _verify_ready(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "phase": "VERIFY",
                "last_execution_id": "exec-dogfood-live",
            }
        )
        run["executions"] = [
            {
                "id": "exec-dogfood-live",
                "action_index": 1,
                "status": "merged",
                "isolation_effective": "worktree",
                "oracle": {
                    "verdict": "pass",
                    "detail": "found literal(s): AUTH_OK",
                    "source": "mock",
                    "evidence": [
                        "read 1 merged snippet(s)",
                        "found literal(s): AUTH_OK",
                    ],
                    "prompt_version": PROMPT_VERSION,
                    "checked_paths": ["src/auth.py"],
                },
            }
        ]
        return run

    patch_run_meta(folder, _verify_ready)

    oracle = read_run_meta(folder)["executions"][0]["oracle"]
    on_verify_result(
        folder,
        action_index=1,
        verdict="pass",
        reason=str(oracle.get("detail") or ""),
        oracle=oracle,
    )

    phase = read_run_meta(folder)["mission_loop"]["phase"]
    if phase != "MISSION_DONE":
        raise RuntimeError(f"expected MISSION_DONE, got {phase!r}")

    done_snap = build_runtime_snapshot(folder)
    if done_snap.get("boulder") is not None:
        raise RuntimeError("dogfood boulder should clear on MISSION_DONE")
    if done_snap.get("last_failure") is not None:
        raise RuntimeError("dogfood last_failure should clear on MISSION_DONE")

    return folder


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sessions",
        type=Path,
        default=ROOT / "sessions",
        help="Sessions root (default: repo sessions/)",
    )
    parser.add_argument("--session-id", default=None, help="Optional fixed session id")
    parser.add_argument("--json", action="store_true", help="JSON report only")
    args = parser.parse_args()

    folder = run_dogfood(sessions_root=args.sessions.expanduser(), session_id=args.session_id)
    print(f"Session: {folder}", file=sys.stderr)

    import importlib.util

    report_path = ROOT / "scripts" / "mission_dogfood_report.py"
    spec = importlib.util.spec_from_file_location("mission_dogfood_report", report_path)
    assert spec and spec.loader
    report_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report_mod)
    payload = report_mod.evaluate(folder)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        status = "OK" if payload["ok"] else "FAIL"
        print(f"\n{status}: mission dogfood — {payload['session_id']}")
        for row in payload["checks"]:
            mark = "✓" if row["ok"] else "✗"
            print(f"  {mark} {row['name']}: {row['detail']}")
        for line in payload["notepad_lines"]:
            print(f"  notepad · {line}")
        for row in payload.get("oracle_evidence") or []:
            print(f"  oracle · {row}")
        for line in payload["score_summary"]:
            if "mission" in line.lower():
                print(f"  {line.strip()}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
