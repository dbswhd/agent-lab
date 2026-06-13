#!/usr/bin/env python3
"""Trading Mission watcher — enqueue delta missions on overlay/freshness events."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Trading Mission watcher (P2)")
    parser.add_argument("--no-enqueue", action="store_true", help="Detect only, do not write queue")
    parser.add_argument("--pipeline-root", type=Path, default=None)
    args = parser.parse_args()

    from agent_lab.trading_mission.watcher import watcher_tick

    report = watcher_tick(args.pipeline_root, enqueue=not args.no_enqueue)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
