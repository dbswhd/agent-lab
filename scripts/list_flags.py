#!/usr/bin/env python3
"""List AGENT_LAB_* env flags (registry + active values). See GET /api/health/flags."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_lab.runtime_flags import build_flags_payload  # noqa: E402


def _print_table(payload: dict) -> None:
    cat = payload.get("category_filter")
    header = f"AGENT_LAB flags ({payload['count']} shown"
    if cat:
        header += f", filter={cat}"
    header += f", registry={payload['registry_count']})"
    print(header)
    print("-" * len(header))
    for row in payload.get("flags") or []:
        name = row["name"]
        category = row["category"]
        effective = row.get("effective") or "—"
        value = row.get("value")
        if value is None:
            value_col = "—"
        else:
            value_col = str(value)
        mark = "*" if row.get("set") else " "
        doc = "" if row.get("documented", True) else " (undocumented)"
        print(f"{mark} {name:<38} {category:<12} {effective:<16} {value_col}{doc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="List AGENT_LAB_* environment flags.")
    parser.add_argument(
        "--category",
        choices=["feature", "infra", "test", "internal", "undocumented"],
        help="Filter by flag category",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON (default: table)")
    args = parser.parse_args()

    payload = build_flags_payload(category=args.category)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_table(payload)
        if payload.get("undocumented_count"):
            print(f"\n* = set in environment · {payload['undocumented_count']} undocumented AGENT_LAB_* var(s) in env")
        else:
            print("\n* = set in environment")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
