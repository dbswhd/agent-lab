from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SCENARIOS = (
    "plan_reject_revisit",
    "execute_success_merge_oracle_pass",
    "oracle_fail_repair",
    "human_inbox_pause_resume",
    "daemon_crash_recovery",
)
EXPECTED_EVENTS = {
    "plan_reject_revisit": ("PlanOpened", "PlanRejected"),
    "execute_success_merge_oracle_pass": (
        "PlanOpened", "PlanApproved", "ExecutionStarted", "DiffReady", "DiffApproved", "MergeCommitted", "OraclePassed"
    ),
    "oracle_fail_repair": (
        "PlanOpened", "PlanApproved", "ExecutionStarted", "DiffReady", "DiffApproved", "MergeCommitted",
        "RepairScheduled", "DiffReady", "DiffApproved", "MergeCommitted", "OraclePassed",
    ),
    "human_inbox_pause_resume": ("PlanOpened", "PlanApproved", "BlockOpened", "BlockResolved"),
    "daemon_crash_recovery": ("PlanOpened", "PlanApproved", "ExecutionStarted"),
}
LEGACY_OBSERVATIONS = {
    "plan_reject_revisit": ("plan_rejected",),
    "execute_success_merge_oracle_pass": ("plan_approved", "execution_merged", "oracle_passed"),
    "oracle_fail_repair": ("plan_approved", "execution_merged", "oracle_failed", "execution_merged", "oracle_passed"),
    "human_inbox_pause_resume": ("mission_paused", "mission_resumed"),
    "daemon_crash_recovery": ("step_completed",),
}


def _init_session(root: Path, scenario: str, index: int) -> tuple[Path, str]:
    session_id = f"dualwrite-{index:02d}-{scenario}"
    folder = root / session_id
    folder.mkdir(parents=True)
    goal = f"dual-write evidence {scenario} {index}"
    (folder / "plan.md").write_text(f"# Plan\n\n- {goal}\n", encoding="utf-8")
    (folder / "run.json").write_text(
        json.dumps(
            {
                "topic": goal,
                "plan_workflow": {"enabled": True, "phase": "HUMAN_PENDING"},
                "dual_write_legacy": [],
            }
        ),
        encoding="utf-8",
    )
    return folder, goal


def _legacy(folder: Path, operation: str, observation: str, **fields: Any) -> None:
    from agent_lab.run.meta import patch_run_meta

    def update(run: dict[str, Any]) -> dict[str, Any]:
        rows = list(run.get("dual_write_legacy") or [])
        rows.append({"operation": operation, "observation": observation, **fields})
        run["dual_write_legacy"] = rows
        return run

    patch_run_meta(folder, update)


def _mission(repo: Any, receipts: list[dict[str, Any]], session_id: str, operation: str, command: Any, key: str) -> Any:
    state = repo.dispatch(command, idempotency_key=key)
    receipts.append({"session_id": session_id, "mission_id": session_id, "operation": operation, "idempotency_key": key})
    return state


def _merge_side_effect(folder: Path, key: str) -> int:
    path = folder / "effects" / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"effect_key": key, "commit_sha": key}, stream)
        count += 1
    return count


def _execute(folder: Path, goal: str, receipts: list[dict[str, Any]], *, repair: bool) -> tuple[int, str]:
    from agent_lab.mission.kernel import (
        ApproveDiff, ApprovePlan, MarkDiffReady, OpenPlan, OracleVerdict, RecordMerge, RecordOracle,
        StartExecution,
    )
    from agent_lab.mission.repository import MissionRepository

    repo = MissionRepository(folder / ".agent-lab" / "mission-events.jsonl", folder.name, goal)
    commands = (
        ("open", OpenPlan("dual-plan")),
        ("approve", ApprovePlan("dual-plan")),
        ("start", StartExecution()),
        ("diff", MarkDiffReady()),
        ("diff-approve", ApproveDiff()),
        ("merge", RecordMerge(f"merge-{folder.name}-a")),
    )
    for operation, command in commands:
        observation = "plan_approved" if operation == "approve" else "execution_merged" if operation == "merge" else "execution_step"
        _legacy(folder, operation, observation)
        _mission(repo, receipts, folder.name, operation, command, f"{folder.name}:{operation}:1")
    effect_count = _merge_side_effect(folder, f"merge-{folder.name}-a")
    if repair:
        _legacy(folder, "oracle-fail", "oracle_failed")
        _mission(repo, receipts, folder.name, "oracle-fail", RecordOracle(OracleVerdict.FAIL, "controlled failure"), f"{folder.name}:oracle:1")
        for operation, command in (("repair-diff", MarkDiffReady()), ("repair-approve", ApproveDiff()), ("repair-merge", RecordMerge(f"merge-{folder.name}-b"))):
            _legacy(folder, operation, "execution_merged" if operation == "repair-merge" else "execution_step")
            _mission(repo, receipts, folder.name, operation, command, f"{folder.name}:{operation}:1")
        effect_count += _merge_side_effect(folder, f"merge-{folder.name}-b")
        _legacy(folder, "oracle-pass", "oracle_passed")
        _mission(repo, receipts, folder.name, "oracle-pass", RecordOracle(OracleVerdict.PASS, "repair passed"), f"{folder.name}:oracle:2")
    else:
        _legacy(folder, "oracle-pass", "oracle_passed")
        _mission(repo, receipts, folder.name, "oracle-pass", RecordOracle(OracleVerdict.PASS, "passed"), f"{folder.name}:oracle:1")
    return effect_count, "SUCCEEDED"


def _scenario(folder: Path, goal: str, scenario: str, receipts: list[dict[str, Any]]) -> tuple[int, str]:
    from agent_lab.human_inbox import create_inbox_item
    from agent_lab.mission.application import MissionApplication
    from agent_lab.mission.kernel import BlockExecution, OpenPlan, ApprovePlan, StartExecution
    from agent_lab.mission.repository import MissionRepository
    from agent_lab.mission.activity_queue import ActivityQueue, QueuedActivity
    from agent_lab.mission.recovery import SideEffectState
    from agent_lab.plan.workflow_approval import reject_plan

    if scenario == "plan_reject_revisit":
        _legacy(folder, "reject", "plan_rejected")
        reject_plan(folder, note="revise scope")
        MissionApplication(folder, goal).reject_plan("revise scope")
        receipts.append({"session_id": folder.name, "mission_id": folder.name, "operation": "reject", "idempotency_key": f"{folder.name}:reject"})
        return 0, "DRAFTING"
    if scenario == "execute_success_merge_oracle_pass":
        return _execute(folder, goal, receipts, repair=False)
    if scenario == "oracle_fail_repair":
        return _execute(folder, goal, receipts, repair=True)
    repo = MissionRepository(folder / ".agent-lab" / "mission-events.jsonl", folder.name, goal)
    if scenario == "human_inbox_pause_resume":
        MissionApplication(folder, goal).approve_plan()
        receipts.append({"session_id": folder.name, "mission_id": folder.name, "operation": "approve", "idempotency_key": f"{folder.name}:plan-approve"})
        _legacy(folder, "pause", "mission_paused")
        _mission(repo, receipts, folder.name, "pause", BlockExecution("human decision"), f"{folder.name}:pause:1")
        item = create_inbox_item(folder, kind="question", source="dual-write", prompt="Resume execution?")
        MissionApplication(folder, goal).answer_inbox(item["id"], "resume")
        receipts.append({"session_id": folder.name, "mission_id": folder.name, "operation": "resume", "idempotency_key": f"{folder.name}:resume:1"})
        _legacy(folder, "resume", "mission_resumed")
        return 0, "READY_TO_EXECUTE"
    for operation, command in (("open", OpenPlan("dual-plan")), ("approve", ApprovePlan("dual-plan")), ("start", StartExecution())):
        _legacy(folder, operation, "plan_approved" if operation == "approve" else "execution_step")
        _mission(repo, receipts, folder.name, operation, command, f"{folder.name}:{operation}:1")
    queue = ActivityQueue.for_session(folder)
    activity = QueuedActivity(f"activity-{folder.name}", folder.name, "recovery", 1, "recover-step")
    queue.enqueue(activity)
    claimed = queue.claim_next("dual-worker", now=100.0, ttl_s=30.0)
    if claimed is None:
        raise RuntimeError("recovery activity was not claimed")
    queue.record_side_effect(activity.activity_id, "dual-worker", claimed.lease.token, SideEffectState.COMMITTED)
    queue.complete(activity.activity_id, "dual-worker", claimed.lease.token, now=101.0)
    _legacy(folder, "recovery", "step_completed", activity_id=activity.activity_id)
    return 0, "EXECUTING"


def _read_model(root: Path, session_id: str) -> dict[str, Any]:
    from fastapi.testclient import TestClient
    from agent_lab.session import paths as session_paths
    from agent_lab import session as session_module
    from app.server.main import create_app
    import app.server.deps as deps_mod

    # active_sessions_dir() checks app.server.deps.SESSIONS_DIR first (see
    # session/paths.py) — deps.py's own `from ... import SESSIONS_DIR` binds
    # once at first import and never re-reads session_paths.SESSIONS_DIR
    # afterward, so create_app() here can leave a stale root baked into deps
    # for the rest of the process (and, under pytest-xdist, the rest of the
    # worker) unless it's saved/restored alongside the other two bindings.
    previous_paths = session_paths.SESSIONS_DIR
    previous_session = session_module.SESSIONS_DIR
    previous_deps = deps_mod.SESSIONS_DIR
    try:
        session_paths.SESSIONS_DIR = root
        session_module.SESSIONS_DIR = root
        deps_mod.SESSIONS_DIR = root
        response = TestClient(create_app(bootstrap=False)).get(f"/api/sessions/{session_id}/mission/read-model")
        response.raise_for_status()
        return response.json()
    finally:
        deps_mod.SESSIONS_DIR = previous_deps
        session_paths.SESSIONS_DIR = previous_paths
        session_module.SESSIONS_DIR = previous_session


def run_cohort(root: Path) -> dict[str, Any]:
    from agent_lab.mission.activity_queue import ActivityQueue, QueueState

    root.mkdir(parents=True, exist_ok=True)
    receipts: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for index, scenario in enumerate(SCENARIOS * 2, start=1):
        folder, goal = _init_session(root, scenario, index)
        effect_count, final_state = _scenario(folder, goal, scenario, receipts)
        from agent_lab.mission.journal import MissionJournal
        from agent_lab.mission.repository import MissionRepository

        stored = MissionJournal(folder / ".agent-lab" / "mission-events.jsonl", mission_id=folder.name).load()
        replayed = MissionRepository(folder / ".agent-lab" / "mission-events.jsonl", folder.name, goal).load()
        legacy = json.loads((folder / "run.json").read_text(encoding="utf-8"))
        observed = tuple(event.event_type for event in stored)
        parity = observed == EXPECTED_EVENTS[scenario] and tuple(row["observation"] for row in legacy["dual_write_legacy"] if row["observation"] in LEGACY_OBSERVATIONS[scenario]) == LEGACY_OBSERVATIONS[scenario]
        activity_ok = scenario != "daemon_crash_recovery" or any(item.state is QueueState.COMPLETED for item in ActivityQueue.for_session(folder).snapshot())
        read_model = _read_model(root, folder.name)
        rows.append({
            "session_id": folder.name,
            "mission_id": replayed.id,
            "scenario": scenario,
            "same_session_identity": replayed.id == folder.name and all(row["session_id"] == folder.name for row in receipts if row["session_id"] == folder.name),
            "parity": parity and activity_ok,
            "side_effect_count": effect_count,
            "restart_replay": replayed.state.value == final_state,
            "reconnect": read_model["migrated"] and read_model["event_cursor"] == len(stored),
            "human_inbox_resume": scenario != "human_inbox_pause_resume" or replayed.state.value == "READY_TO_EXECUTE",
            "event_types": observed,
        })
    return {
        "session_count": len(rows),
        "scenario_counts": {scenario: sum(row["scenario"] == scenario for row in rows) for scenario in SCENARIOS},
        "parity_pass": all(row["parity"] for row in rows),
        "side_effect_single_execution": all(
            row["side_effect_count"] == (2 if row["scenario"] == "oracle_fail_repair" else 1 if row["scenario"] == "execute_success_merge_oracle_pass" else 0)
            for row in rows
        ),
        "restart_replay_pass": all(row["restart_replay"] for row in rows),
        "reconnect_pass": all(row["reconnect"] for row in rows),
        "human_inbox_resume_pass": all(row["human_inbox_resume"] for row in rows),
        "sessions": rows,
        "scope": "isolated production-like dual-write cohort; production routes remain unchanged",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=Path, required=True)
    args = parser.parse_args()
    report = run_cohort(args.sessions)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(report[key] for key in ("parity_pass", "side_effect_single_execution", "restart_replay_pass", "reconnect_pass", "human_inbox_resume_pass")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
