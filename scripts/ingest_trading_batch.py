#!/usr/bin/env python3
"""Ingest one Trading Mission session's proposal_batch into control plane SQLite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest trading mission proposal batch")
    parser.add_argument("session_folder", type=Path, help="Agent-lab session folder")
    parser.add_argument("--db", type=Path, default=None, help="Control plane SQLite path")
    parser.add_argument("--dry-run", action="store_true", help="Validate only")
    parser.add_argument("--force", action="store_true", help="Re-ingest same mission_id")
    args = parser.parse_args()

    from agent_lab.trading_mission.ingest_bridge import ingest_proposal_batch

    report = ingest_proposal_batch(
        args.session_folder,
        db_path=args.db,
        dry_run=args.dry_run,
        force=args.force,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
