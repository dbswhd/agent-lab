#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agent_lab.room.turn_contract_promotion import build_promotion_report


def _rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                rows.append({})
                continue
            rows.append(row if isinstance(row, dict) else {})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate staged TurnContract routing promotion evidence.")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--stage", choices=("roles", "adaptive"), required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = build_promotion_report(_rows(args.ledger), stage=args.stage)
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(f"{report['stage']}: {report['decision']}")
        print(f"eligible sessions: {report['eligible_sessions']}")
        print(f"blocking reasons: {', '.join(report['blocking_reasons']) or 'none'}")
        print(f"Human checkpoint: {report['human_checkpoint']}")
    return 0 if report["metrics_green"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
