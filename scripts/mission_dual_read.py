from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_lab.mission.dual_read import FixtureDualReadReport, evaluate_manifest

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "tests" / "fixtures" / "mission-baseline.json"


def _payload(report: FixtureDualReadReport) -> dict[str, object]:
    return {
        "cutover_ready": report.cutover_ready,
        "results": [
            {
                "scenario_id": result.scenario_id,
                "fixture": result.fixture,
                "expected_terminal_state": result.expected_terminal_state,
                "status": result.status,
                "journal_present": result.journal_present,
                "legacy_observation_kinds": result.legacy_observation_kinds,
                "observed_event_types": result.observed_event_types,
                "missing_event_types": result.missing_event_types,
                "unexpected_event_types": result.unexpected_event_types,
                "unsupported_observations": result.unsupported_observations,
                "detail": result.detail,
                "activity_queue_present": result.activity_queue_present,
                "completed_activity_ids": result.completed_activity_ids,
            }
            for result in report.results
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    report = evaluate_manifest(args.root, args.manifest)
    print(json.dumps(_payload(report), ensure_ascii=False, indent=2))
    return 0 if report.cutover_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
