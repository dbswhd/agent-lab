#!/usr/bin/env python3
"""Audit Cursor bridge registry vs live processes; optional stale cleanup."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from agent_lab.bridge_registry import audit_bridge_processes, cleanup_stale_bridges

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="drop stale rows from ~/.agent-lab/bridge_registry.json",
    )
    parser.add_argument(
        "--kill-orphans",
        action="store_true",
        help="SIGTERM bridge PIDs not present in registry (use with care)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 when stale registry rows or orphan processes exist",
    )
    args = parser.parse_args()

    if args.prune or args.kill_orphans:
        result = cleanup_stale_bridges(
            kill_orphans=args.kill_orphans,
            prune_registry=args.prune,
        )
        audit = result["audit"]
        payload = {"action": "cleanup", **result}
    else:
        audit = audit_bridge_processes()
        payload = {"action": "audit", "audit": audit}

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        audit = payload.get("audit", audit)
        print(
            f"bridge registry: {audit.get('record_count', 0)} rows · "
            f"active={audit.get('active_count', 0)} · "
            f"stale={audit.get('stale_count', 0)} · "
            f"orphan_proc={audit.get('orphan_process_count', 0)}"
        )
        if payload.get("action") == "cleanup":
            print(
                f"cleanup: removed_registry={payload.get('removed_registry', 0)} "
                f"killed={payload.get('killed_pids', [])}"
            )
        for row in audit.get("stale_records") or []:
            print(f"  stale workspace={row.get('workspace')} pid={row.get('pid')} age_h={row.get('age_hours')}")
        for row in audit.get("orphan_processes") or []:
            print(f"  orphan pid={row.get('pid')} cmd={row.get('command', '')[:80]}")

    audit = payload.get("audit", {})
    if args.strict and (int(audit.get("stale_count") or 0) > 0 or int(audit.get("orphan_process_count") or 0) > 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
