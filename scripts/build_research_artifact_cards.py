#!/usr/bin/env python3
"""Sync research/kr/results *_full.json → data/agentic_trading/cards/*.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ResearchArtifactCard cache")
    parser.add_argument(
        "--pipeline",
        type=Path,
        default=None,
        help="QUANT_PIPELINE_ROOT override",
    )
    parser.add_argument(
        "--cards-dir",
        type=Path,
        default=None,
        help="Output cards directory override",
    )
    parser.add_argument(
        "--pass-only",
        action="store_true",
        help="Skip FAIL/INFO cards",
    )
    args = parser.parse_args()

    from agent_lab.pipeline_research_read import sync_research_cards

    report = sync_research_cards(
        args.pipeline,
        cards_dir=args.cards_dir,
        include_ineligible=not args.pass_only,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
