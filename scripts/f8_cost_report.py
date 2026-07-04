#!/usr/bin/env python3
"""F8 quarterly cost report — see docs/F8-COST-VISIBILITY.md."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_lab.cost_ledger_quarter import (  # noqa: E402
    public_quarter_cost_payload,
    quarter_budget_status,
    read_quarter_ledger,
)


def render(status: dict) -> str:
    lines = [
        f"F8 quarterly cost — {status.get('quarter')}",
        f"spent_usd: {status.get('spent_usd')}",
        f"limit_usd: {status.get('limit_usd')}",
        f"sessions: {status.get('session_count')}",
        f"warn: {status.get('warn')}  over: {status.get('over')}",
        f"demote_enabled: {status.get('demote_enabled')}",
        f"updated_at: {status.get('updated_at')}",
    ]
    if status.get("over"):
        lines.append("")
        lines.append("OVER quarterly cap — autonomy demotion to L0 when demote_enabled.")
    elif status.get("limit_usd") is None:
        lines.append("")
        lines.append("No AGENT_LAB_QUARTER_BUDGET_USD set — tracking only.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="F8 quarterly cost report")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="project root holding .agent-lab/cost_ledger_quarter.json",
    )
    args = parser.parse_args()
    root = Path(args.root) if args.root else None
    status = quarter_budget_status(root)
    if args.json:
        payload = public_quarter_cost_payload(root)
        payload["demote_enabled"] = status.get("demote_enabled")
        payload["by_session"] = read_quarter_ledger(root).get("by_session")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render(status))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
