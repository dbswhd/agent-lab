#!/usr/bin/env python3
"""F7 dogfood report — repo_map / compaction coverage from session run.json.

See docs/F7-REPO-MAP-COMPACTION-DOGFOOD.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _parse_ts(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


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


def collect_sessions(
    sessions_dir: Path,
    *,
    days: int,
) -> list[dict[str, Any]]:
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
        bundle = run.get("last_context_bundle")
        log = run.get("context_quality_log")
        if not isinstance(bundle, dict) and not isinstance(log, list):
            continue
        if not isinstance(bundle, dict):
            bundle = {}
        if not isinstance(log, list):
            log = []
        budget_vals = [
            float(row.get("budget_pct"))
            for row in log
            if isinstance(row, dict) and isinstance(row.get("budget_pct"), (int, float))
        ]
        if isinstance(bundle.get("budget_pct"), (int, float)):
            budget_vals.append(float(bundle["budget_pct"]))
        rows.append(
            {
                "session_id": folder.name,
                "repo_layer": bundle.get("repo_layer")
                or (log[-1].get("repo_layer") if log and isinstance(log[-1], dict) else None),
                "repo_map_enabled": bool(
                    bundle.get("repo_map_enabled")
                    or any(
                        isinstance(r, dict) and r.get("repo_layer") == "repo_map" for r in log
                    )
                ),
                "compact_tool_output": bool(
                    bundle.get("compact_tool_output")
                    or any(
                        isinstance(r, dict) and r.get("compact_tool_output") for r in log
                    )
                ),
                "budget_pct_median": median(budget_vals) if budget_vals else None,
                "trim_level": bundle.get("trim_level"),
                "log_n": len(log),
            }
        )
    return rows


def build_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    repo_map_n = sum(1 for r in rows if r.get("repo_layer") == "repo_map" or r.get("repo_map_enabled"))
    compact_n = sum(1 for r in rows if r.get("compact_tool_output"))
    budgets = [
        float(r["budget_pct_median"])
        for r in rows
        if isinstance(r.get("budget_pct_median"), (int, float))
    ]
    coverage = round(100.0 * repo_map_n / n, 1) if n else 0.0
    gates = {
        "min_sessions": n >= 10,
        "repo_map_coverage_70": coverage >= 70.0,
        "budget_median_under_90": (median(budgets) < 90.0) if budgets else False,
    }
    return {
        "sessions": n,
        "repo_map_sessions": repo_map_n,
        "repo_map_coverage_pct": coverage,
        "compact_sessions": compact_n,
        "median_budget_pct": round(median(budgets), 1) if budgets else None,
        "gates": gates,
        "ready_for_decision": all(gates.values()),
        "flags_now": {
            "AGENT_LAB_REPO_MAP": os.getenv("AGENT_LAB_REPO_MAP") or "(unset)",
            "AGENT_LAB_COMPACT_TOOL_OUTPUT": os.getenv("AGENT_LAB_COMPACT_TOOL_OUTPUT")
            or "(unset)",
        },
        "rows": rows,
    }


def render_report(report: dict[str, Any]) -> str:
    lines = [
        "F7 repo_map / compaction dogfood report",
        f"sessions with context metrics: {report['sessions']}",
        f"repo_map coverage: {report['repo_map_coverage_pct']}% "
        f"({report['repo_map_sessions']}/{report['sessions']})",
        f"compact_tool_output seen: {report['compact_sessions']}",
        f"median budget_pct: {report['median_budget_pct']}",
        "",
        "gates:",
    ]
    for key, ok in (report.get("gates") or {}).items():
        lines.append(f"  {'PASS' if ok else 'FAIL'}  {key}")
    lines.append("")
    if report.get("ready_for_decision"):
        lines.append("Sample gates met — complete Human compaction checklist (≥5 sessions),")
        lines.append("then record ON/OFF in docs/F7-REPO-MAP-COMPACTION-DOGFOOD.md")
    else:
        lines.append("Sample gates not met yet — keep dogfood week running (supervisor + flags ON).")
    lines.append("")
    lines.append("current process flags:")
    for name, val in (report.get("flags_now") or {}).items():
        lines.append(f"  {name}={val}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="F7 dogfood coverage report")
    parser.add_argument(
        "--sessions",
        type=str,
        default=str(ROOT / "sessions"),
        help="sessions directory",
    )
    parser.add_argument("--days", type=int, default=7, help="lookback days (default 7)")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    rows = collect_sessions(Path(args.sessions), days=args.days)
    report = build_report(rows)
    if args.json:
        # omit full rows unless small
        payload = {k: v for k, v in report.items() if k != "rows"}
        payload["session_ids"] = [r["session_id"] for r in rows]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
