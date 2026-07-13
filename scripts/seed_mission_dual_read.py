from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from agent_lab.mission.activity_queue import ActivityQueue, QueuedActivity
from agent_lab.mission.kernel import (
    ApproveDiff,
    ApprovePlan,
    BlockExecution,
    MarkDiffReady,
    MissionCommand,
    OpenPlan,
    OracleVerdict,
    RecordMerge,
    RecordOracle,
    RejectPlan,
    StartExecution,
)
from agent_lab.mission.repository import MissionRepository
from agent_lab.mission.recovery import SideEffectState

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "tests" / "fixtures" / "mission-baseline.json"


def _execute_commands() -> tuple[MissionCommand, ...]:
    return (
        OpenPlan("fixture-plan"),
        ApprovePlan("fixture-plan"),
        StartExecution(),
        MarkDiffReady(),
        ApproveDiff(),
        RecordMerge("fixture-merge-a"),
        RecordOracle(OracleVerdict.PASS, "fixture oracle pass"),
    )


def _repair_commands() -> tuple[MissionCommand, ...]:
    return (
        OpenPlan("fixture-plan"),
        ApprovePlan("fixture-plan"),
        StartExecution(),
        MarkDiffReady(),
        ApproveDiff(),
        RecordMerge("fixture-merge-a"),
        RecordOracle(OracleVerdict.FAIL, "fixture oracle failure"),
        MarkDiffReady(),
        ApproveDiff(),
        RecordMerge("fixture-merge-b"),
        RecordOracle(OracleVerdict.PASS, "fixture repair pass"),
    )


def _pause_commands() -> tuple[MissionCommand, ...]:
    return (
        OpenPlan("fixture-plan"),
        ApprovePlan("fixture-plan"),
        BlockExecution("fixture human pause"),
    )


def _seed_mission(folder: Path, scenario_id: str) -> None:
    if scenario_id == "plan_reject_revisit":
        commands: tuple[MissionCommand, ...] = (OpenPlan("fixture-plan"), RejectPlan("fixture rejection"))
    elif scenario_id == "execute_success_merge_oracle_pass":
        commands = _execute_commands()
    elif scenario_id == "oracle_fail_repair":
        commands = _repair_commands()
    elif scenario_id == "human_inbox_pause_resume":
        commands = _pause_commands()
    else:
        return
    repository = MissionRepository(folder / ".agent-lab" / "mission-events.jsonl", folder.name, scenario_id)
    for command in commands:
        repository.dispatch(command)


def _seed_crash_activity(folder: Path) -> None:
    queue = ActivityQueue.for_session(folder)
    queue.enqueue(QueuedActivity("recovery-step-1", folder.name, "recovery", 1, "recovery-step-1"))
    claimed = queue.claim_next("seed-worker", now=100.0, ttl_s=30.0)
    if claimed is None:
        raise RuntimeError("crash recovery activity was not claimed")
    queue.record_side_effect(
        claimed.activity.activity_id,
        "seed-worker",
        claimed.lease.token,
        SideEffectState.COMMITTED,
    )
    queue.complete(claimed.activity.activity_id, "seed-worker", claimed.lease.token, now=101.0)


def seed_manifest(source_root: Path, target_root: Path, manifest_path: Path) -> tuple[str, ...]:
    if target_root.exists():
        raise FileExistsError(f"target already exists: {target_root}")
    raw: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    scenarios = raw.get("scenarios") if isinstance(raw, dict) else None
    if not isinstance(scenarios, list):
        raise ValueError("mission baseline manifest must contain scenarios")
    seeded: list[str] = []
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        fixture = scenario.get("fixture")
        scenario_id = scenario.get("id")
        if not isinstance(fixture, str) or not isinstance(scenario_id, str):
            continue
        source = source_root / fixture
        target = target_root / fixture
        shutil.copytree(source, target)
        if scenario_id == "daemon_crash_recovery":
            _seed_crash_activity(target)
        else:
            _seed_mission(target, scenario_id)
        seeded.append(scenario_id)
    return tuple(seeded)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    seeded = seed_manifest(args.source_root, args.target, args.manifest)
    print(json.dumps({"target": str(args.target), "seeded": seeded}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
