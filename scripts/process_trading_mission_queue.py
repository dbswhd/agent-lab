#!/usr/bin/env python3
"""Process pending Trading Mission delta events from watcher queue."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Process trading mission queue (P2)")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--skip-discuss", action="store_true")
    parser.add_argument("--ingest", action="store_true")
    args = parser.parse_args()

    from agent_lab.trading_mission.watcher import read_pending_queue

    pending = read_pending_queue(limit=args.limit)
    if not pending:
        print(json.dumps({"ok": True, "processed": 0, "reason": "queue empty"}, indent=2))
        return 0

    script = ROOT / "scripts" / "run_trading_mission_delta.py"
    results: list[dict] = []
    for event in pending[: args.limit]:
        trigger = str(event.get("trigger") or "queued")
        reason = str(event.get("reason") or "")
        cmd = [
            sys.executable,
            str(script),
            "--trigger",
            trigger,
            "--reason",
            reason,
        ]
        if args.skip_discuss:
            cmd.append("--skip-discuss")
        if args.ingest:
            cmd.append("--ingest")
        proc = subprocess.run(cmd, cwd=str(ROOT), check=False)
        results.append({"trigger": trigger, "returncode": proc.returncode})

    ok = all(r["returncode"] == 0 for r in results)
    print(json.dumps({"ok": ok, "processed": len(results), "results": results}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
