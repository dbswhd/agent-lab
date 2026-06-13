#!/usr/bin/env python3
"""Trading Mission scheduler tick — run premarket when due (cron/launchd)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Trading Mission scheduler (P2)")
    parser.add_argument("--force", action="store_true", help="Ignore date/time guards")
    parser.add_argument("--ingest", action="store_true", help="Pass --ingest to premarket script")
    parser.add_argument("--mock-room", action="store_true", help="Pass --mock-room to premarket script")
    parser.add_argument("--pipeline-root", type=Path, default=None)
    args = parser.parse_args()

    from agent_lab.trading_mission.scheduler import scheduler_tick

    report = scheduler_tick(
        force=args.force,
        pipeline_root=args.pipeline_root,
        ingest=args.ingest,
        mock_room=args.mock_room,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
