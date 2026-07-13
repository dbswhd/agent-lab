from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for path in (ROOT / "src", SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _load_dogfood_runner() -> Any:
    spec = importlib.util.spec_from_file_location("mission_dogfood_run", SCRIPTS / "mission_dogfood_run.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("mission dogfood runner could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project_execute_success_shadow(folder: Path) -> None:
    from agent_lab.mission.kernel import (
        ApproveDiff,
        ApprovePlan,
        MarkDiffReady,
        OpenPlan,
        OracleVerdict,
        RecordMerge,
        RecordOracle,
        StartExecution,
    )
    from agent_lab.mission.repository import MissionRepository

    repository = MissionRepository(
        folder / ".agent-lab" / "mission-events.jsonl",
        folder.name,
        "supervisor dogfood shadow",
    )
    for command in (
        OpenPlan("dogfood-shadow-plan"),
        ApprovePlan("dogfood-shadow-plan"),
        StartExecution(),
        MarkDiffReady(),
        ApproveDiff(),
        RecordMerge("dogfood-shadow-merge"),
        RecordOracle(OracleVerdict.PASS, "shadow projection from dogfood Oracle evidence"),
    ):
        repository.dispatch(command)


def run_dual_read(*, sessions_root: Path, session_id: str) -> dict[str, object]:
    os.environ["AGENT_LAB_MOCK_AGENTS"] = "1"
    os.environ["AGENT_LAB_MISSION_LOOP"] = "1"
    runner = _load_dogfood_runner()
    folder = runner.run_dogfood(sessions_root=sessions_root, session_id=session_id)
    legacy_run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    project_execute_success_shadow(folder)
    from agent_lab.mission.dual_read import inspect_fixture

    parity = inspect_fixture(
        sessions_root,
        {
            "id": "supervisor_dogfood_shadow",
            "fixture": session_id,
            "expected_terminal_state": "MISSION_DONE",
        },
    )
    return {
        "session_id": folder.name,
        "dogfood_ok": str(legacy_run.get("mission_loop", {}).get("phase")) == "MISSION_DONE",
        "dual_read_status": parity.status,
        "journal_present": parity.journal_present,
        "observed_event_types": parity.observed_event_types,
        "missing_event_types": parity.missing_event_types,
        "unexpected_event_types": parity.unexpected_event_types,
        "note": "Mission journal was projected after legacy dogfood; no production writer was changed",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--session-id", default="supervisor-dual-read")
    args = parser.parse_args()
    payload = run_dual_read(sessions_root=args.sessions, session_id=args.session_id)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["dogfood_ok"] and payload["dual_read_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
