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
        last_turn = run.get("last_turn")
        turn_context = last_turn.get("context") if isinstance(last_turn, dict) else None
        turn_agents = turn_context.get("agents") if isinstance(turn_context, dict) else None
        if not isinstance(bundle, dict) and not isinstance(log, list) and not isinstance(turn_agents, list):
            continue
        if not isinstance(bundle, dict):
            bundle = {}
        if not isinstance(log, list):
            log = []
        if not isinstance(turn_agents, list):
            turn_agents = []
        budget_vals = [
            float(row.get("budget_pct"))
            for row in log
            if isinstance(row, dict) and isinstance(row.get("budget_pct"), (int, float))
        ]
        if isinstance(bundle.get("budget_pct"), (int, float)):
            budget_vals.append(float(bundle["budget_pct"]))
        budget_vals.extend(
            float(row.get("budget_pct"))
            for row in turn_agents
            if isinstance(row, dict) and isinstance(row.get("budget_pct"), (int, float))
        )
        f7_rows = [r for r in [bundle, *log, *turn_agents] if isinstance(r, dict)]
        repo_layer = next(
            (str(r["repo_layer"]) for r in reversed(f7_rows) if isinstance(r.get("repo_layer"), str)),
            None,
        )
        repo_map_enabled = any(r.get("repo_map_enabled") is True or r.get("repo_layer") == "repo_map" for r in f7_rows)
        compact_tool_output = any(r.get("compact_tool_output") is True for r in f7_rows)
        f7_instrumented = any(
            "repo_layer" in r or "repo_map_enabled" in r or "compact_tool_output" in r for r in f7_rows
        )
        rows.append(
            {
                "session_id": folder.name,
                "repo_layer": repo_layer,
                "repo_map_enabled": repo_map_enabled,
                "compact_tool_output": compact_tool_output,
                "f7_instrumented": f7_instrumented,
                "budget_pct_median": median(budget_vals) if budget_vals else None,
                "trim_level": bundle.get("trim_level"),
                "log_n": len(log),
                "turn_context_agents": len(turn_agents),
            }
        )
    return rows


def build_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    repo_map_n = sum(1 for r in rows if r.get("repo_layer") == "repo_map" or r.get("repo_map_enabled"))
    compact_n = sum(1 for r in rows if r.get("compact_tool_output"))
    instrumented_n = sum(1 for r in rows if r.get("f7_instrumented"))
    missing_n = n - instrumented_n
    budgets = [float(r["budget_pct_median"]) for r in rows if isinstance(r.get("budget_pct_median"), (int, float))]
    coverage = round(100.0 * repo_map_n / n, 1) if n else 0.0
    instrumented_coverage = round(100.0 * repo_map_n / instrumented_n, 1) if instrumented_n else 0.0
    gates = {
        "min_sessions": n >= 10,
        "f7_instrumented_sessions": instrumented_n >= 10,
        "repo_map_coverage_70": instrumented_coverage >= 70.0,
        "budget_median_under_90": (median(budgets) < 90.0) if budgets else False,
    }
    return {
        "sessions": n,
        "f7_instrumented_sessions": instrumented_n,
        "missing_f7_instrumentation_sessions": missing_n,
        "repo_map_sessions": repo_map_n,
        "repo_map_coverage_pct": instrumented_coverage,
        "repo_map_coverage_all_context_pct": coverage,
        "compact_sessions": compact_n,
        "median_budget_pct": round(median(budgets), 1) if budgets else None,
        "gates": gates,
        "ready_for_decision": all(gates.values()),
        "flags_now": {
            "AGENT_LAB_REPO_MAP": os.getenv("AGENT_LAB_REPO_MAP") or "(unset)",
            "AGENT_LAB_COMPACT_TOOL_OUTPUT": os.getenv("AGENT_LAB_COMPACT_TOOL_OUTPUT") or "(unset)",
        },
        "rows": rows,
    }


def render_report(report: dict[str, Any]) -> str:
    lines = [
        "F7 repo_map / compaction dogfood report",
        f"sessions with context metrics: {report['sessions']}",
        f"F7-instrumented sessions: {report['f7_instrumented_sessions']} "
        f"(missing {report['missing_f7_instrumentation_sessions']})",
        f"repo_map coverage: {report['repo_map_coverage_pct']}% "
        f"({report['repo_map_sessions']}/{report['f7_instrumented_sessions']})",
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


def render_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {render_report(report).splitlines()[0]}", ""]
    lines.extend(render_report(report).splitlines()[1:])
    lines.append("")
    lines.append("## Sessions")
    for row in report.get("rows") or []:
        if not isinstance(row, dict):
            continue
        session_id = row.get("session_id")
        f7_state = "instrumented" if row.get("f7_instrumented") else "missing F7 fields"
        lines.append(
            f"- `{session_id}`: {f7_state}, "
            f"repo_layer={row.get('repo_layer') or 'unknown'}, "
            f"budget_pct_median={row.get('budget_pct_median')}"
        )
    return "\n".join(lines) + "\n"


def write_report_artifacts(report: dict[str, Any], report_dir: Path) -> dict[str, str]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    json_path = report_dir / f"f7-dogfood-{stamp}.json"
    md_path = report_dir / f"f7-dogfood-{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_report_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


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
    parser.add_argument("--write", action="store_true", help="write JSON and Markdown artifacts")
    parser.add_argument("--out-dir", type=str, default="", help="report artifact directory")
    args = parser.parse_args()

    sessions_dir = Path(args.sessions)
    rows = collect_sessions(sessions_dir, days=args.days)
    report = build_report(rows)
    artifact_paths: dict[str, str] = {}
    if args.write:
        report_dir = Path(args.out_dir) if args.out_dir else sessions_dir / "_reports"
        artifact_paths = write_report_artifacts(report, report_dir)
    if args.json:
        # omit full rows unless small
        payload = {k: v for k, v in report.items() if k != "rows"}
        payload["session_ids"] = [r["session_id"] for r in rows]
        if artifact_paths:
            payload["artifact_paths"] = artifact_paths
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_report(report))
        if artifact_paths:
            print("")
            print(f"report_json: {artifact_paths['json']}")
            print(f"report_markdown: {artifact_paths['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
