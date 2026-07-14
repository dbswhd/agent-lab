#!/usr/bin/env python3
"""Coordination-topology shadow report — mission.topology.choose_topology()
decisions recorded by topic_router.py's _coordination_shadow_decision(), read
back from real session run.json files.

The shadow field does not drive routing yet (see topic_router.py docstring).
This report exists to make the accumulating real-usage signal inspectable
before anyone decides whether to promote it from shadow to authoritative —
same "observe, then decide" shape as scripts/f7_dogfood_report.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _session_mtime(folder: Path) -> datetime:
    run_path = folder / "run.json"
    if run_path.is_file():
        return datetime.fromtimestamp(run_path.stat().st_mtime, tz=timezone.utc)
    return datetime.fromtimestamp(folder.stat().st_mtime, tz=timezone.utc)


def _load_run(folder: Path) -> dict[str, Any] | None:
    path = folder / "run.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def collect_turns(sessions_dir: Path, *, days: int) -> list[dict[str, Any]]:
    """One row per turn that carries a coordination_topology shadow decision."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    rows: list[dict[str, Any]] = []
    if not sessions_dir.is_dir():
        return rows
    for folder in sorted(sessions_dir.iterdir()):
        if not folder.is_dir() or folder.name.startswith("_"):
            continue
        if _session_mtime(folder) < cutoff:
            continue
        run = _load_run(folder)
        if not run:
            continue
        turns = run.get("turns")
        if not isinstance(turns, list):
            continue
        for i, turn in enumerate(turns):
            if not isinstance(turn, dict):
                continue
            category = turn.get("category")
            if not isinstance(category, dict):
                continue
            topology = category.get("coordination_topology")
            if not isinstance(topology, str) or not topology:
                continue
            rows.append(
                {
                    "session_id": folder.name,
                    "turn_index": i,
                    "category": category.get("value"),
                    "task_type": category.get("task_type"),
                    "agent_subset": category.get("agent_subset"),
                    "topology": category.get("topology"),
                    "coordination_topology": topology,
                    "coordination_topology_reason": category.get("coordination_topology_reason"),
                }
            )
    return rows


def build_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    kind_counts = Counter(r["coordination_topology"] for r in rows)
    category_counts = Counter(r["category"] for r in rows if r.get("category"))
    by_kind_and_category = Counter((r["coordination_topology"], r.get("category")) for r in rows)
    gates = {
        "min_turns_20": n >= 20,
        "at_least_2_topology_kinds": len(kind_counts) >= 2,
        "at_least_3_categories": len(category_counts) >= 3,
        "not_degenerate_single_only": n == 0 or kind_counts.get("single", 0) < n,
    }
    return {
        "turns": n,
        "kind_counts": dict(kind_counts),
        "category_counts": dict(category_counts),
        "kind_by_category": {f"{kind}/{cat}": count for (kind, cat), count in by_kind_and_category.items()},
        "gates": gates,
        "ready_for_manual_review": all(gates.values()),
        "rows": rows,
    }


def render_report(report: dict[str, Any]) -> str:
    lines = [
        "Coordination-topology shadow report",
        f"turns with a shadow decision: {report['turns']}",
        "",
        "topology kind distribution:",
    ]
    for kind, count in sorted(report["kind_counts"].items(), key=lambda kv: -kv[1]):
        lines.append(f"  {kind}: {count}")
    lines.append("")
    lines.append("category distribution:")
    for cat, count in sorted(report["category_counts"].items(), key=lambda kv: -kv[1]):
        lines.append(f"  {cat}: {count}")
    lines.append("")
    lines.append("gates:")
    for key, ok in (report.get("gates") or {}).items():
        lines.append(f"  {'PASS' if ok else 'FAIL'}  {key}")
    lines.append("")
    if report.get("ready_for_manual_review"):
        lines.append("Sample gates met — spot-check the rows below against human judgment:")
        lines.append("does each (category, task_type, agent_subset) -> coordination_topology")
        lines.append("assignment look sane? If yes across a real sample, that's the evidence")
        lines.append("needed before considering whether the shadow decision should drive")
        lines.append("routing. This report does not make that call on its own.")
    else:
        lines.append("Not enough real-usage signal yet — keep the topic router running as-is.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Coordination-topology shadow dogfood report")
    parser.add_argument("--sessions", type=str, default=str(ROOT / "sessions"), help="sessions directory")
    parser.add_argument("--days", type=int, default=14, help="lookback days (default 14)")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    sessions_dir = Path(args.sessions)
    rows = collect_turns(sessions_dir, days=args.days)
    report = build_report(rows)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_report(report))
        if rows:
            print("")
            print("sample rows (most recent 10):")
            for row in rows[-10:]:
                print(
                    f"  {row['session_id']}#{row['turn_index']}: "
                    f"{row['category']}/{row['task_type']} subset={row['agent_subset']} "
                    f"-> {row['coordination_topology']} ({row['coordination_topology_reason']})"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
