"""Aggregate offline session KPIs into a weekly real-usage report (H4 / M4)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent_lab.app_config import resolve_sessions_dir
from agent_lab.session_score import score_session

_FOLDER_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")

# ROOM-REINFORCEMENT.md M4 (H track)
M4_OBJECTION_RESOLUTION_MIN = 0.80
M4_EXECUTE_RETRY_RATE_MAX = 0.30


@dataclass(frozen=True)
class WeeklyDiscovery:
    folder: Path
    anchor_date: date


def _parse_iso_date(value: str) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw).date()
    except ValueError:
        return None


def session_anchor_date(folder: Path) -> date | None:
    """Best-effort session date from folder name or run.json created_at."""
    match = _FOLDER_DATE_RE.match(folder.name)
    if match:
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            pass
    run_path = folder / "run.json"
    if run_path.is_file():
        try:
            data = json.loads(run_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                parsed = _parse_iso_date(str(data.get("created_at") or ""))
                if parsed:
                    return parsed
        except (OSError, json.JSONDecodeError):
            pass
    meta_path = folder / "meta.json"
    if meta_path.is_file():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                parsed = _parse_iso_date(str(data.get("created_at") or ""))
                if parsed:
                    return parsed
        except (OSError, json.JSONDecodeError):
            pass
    return None


def is_scorable_session_folder(folder: Path, *, include_fixtures: bool) -> bool:
    if not folder.is_dir():
        return False
    name = folder.name
    if name.startswith("."):
        return False
    if name.startswith("_") and not include_fixtures:
        return False
    return (folder / "run.json").is_file()


def _iter_session_candidates(
    root: Path,
    *,
    include_fixtures: bool,
) -> list[Path]:
    if not root.is_dir():
        return []
    candidates: list[Path] = []
    for child in sorted(root.iterdir()):
        if child.name in ("_regression", "_benchmark") and include_fixtures and child.is_dir():
            candidates.extend(
                sorted(
                    p
                    for p in child.iterdir()
                    if is_scorable_session_folder(p, include_fixtures=True)
                )
            )
            continue
        if is_scorable_session_folder(child, include_fixtures=include_fixtures):
            candidates.append(child)
    return candidates


def discover_sessions(
    root: Path,
    *,
    days: int = 7,
    include_fixtures: bool = False,
    as_of: date | None = None,
) -> list[WeeklyDiscovery]:
    """List session folders with run.json in the last `days` (inclusive window)."""
    root = root.expanduser().resolve()
    end = as_of or datetime.now(timezone.utc).date()
    start = end - timedelta(days=max(days - 1, 0))
    out: list[WeeklyDiscovery] = []
    for child in _iter_session_candidates(root, include_fixtures=include_fixtures):
        anchor = session_anchor_date(child)
        if anchor is None or anchor < start or anchor > end:
            continue
        out.append(WeeklyDiscovery(folder=child, anchor_date=anchor))
    return out


def _pool_objection_counts(reports: list[dict[str, Any]]) -> dict[str, int]:
    total = resolved = open_n = 0
    for report in reports:
        counts = (report.get("counts") or {}).get("objections") or {}
        total += int(counts.get("total") or 0)
        resolved += int(counts.get("resolved") or 0)
        open_n += int(counts.get("open") or 0)
    return {"total": total, "resolved": resolved, "open": open_n}


def _pool_execute_counts(reports: list[dict[str, Any]]) -> dict[str, int]:
    terminal = first_try = retried = 0
    for report in reports:
        counts = (report.get("counts") or {}).get("executions") or {}
        terminal += int(counts.get("terminal") or 0)
        first_try += int(counts.get("first_try") or 0)
        retried += int(counts.get("retried") or 0)
    return {
        "terminal": terminal,
        "first_try": first_try,
        "retried": retried,
    }


def _pool_merge_counts(reports: list[dict[str, Any]]) -> dict[str, int]:
    keys = (
        "total",
        "gitish",
        "worktree",
        "snapshot_override",
        "worktree_terminal",
        "merge_first_success",
        "merge_conflict",
    )
    pooled = {k: 0 for k in keys}
    for report in reports:
        counts = (report.get("counts") or {}).get("execute_merge") or {}
        for key in keys:
            pooled[key] += int(counts.get(key) or 0)
    return pooled


def _pool_turn_counts(reports: list[dict[str, Any]]) -> dict[str, int]:
    total = partial = failed = completed = 0
    for report in reports:
        counts = (report.get("counts") or {}).get("turns") or {}
        total += int(counts.get("total") or 0)
        partial += int(counts.get("partial") or 0)
        failed += int(counts.get("failed") or 0)
        completed += int(counts.get("completed") or 0)
    return {
        "total": total,
        "partial": partial,
        "failed": failed,
        "completed": completed,
    }


def aggregate_rates(
    reports: list[dict[str, Any]],
) -> tuple[dict[str, float | None], dict[str, dict[str, int]]]:
    """Pooled weekly rates across session reports."""
    obj = _pool_objection_counts(reports)
    exe = _pool_execute_counts(reports)
    merge = _pool_merge_counts(reports)
    turns = _pool_turn_counts(reports)

    objection_rate = (
        obj["resolved"] / obj["total"] if obj["total"] else None
    )
    first_try_rate = exe["first_try"] / exe["terminal"] if exe["terminal"] else None
    retry_rate = exe["retried"] / exe["terminal"] if exe["terminal"] else None
    partial_rate = turns["partial"] / turns["total"] if turns["total"] else None

    scores: dict[str, float | None] = {
        "objection_resolution_rate": objection_rate,
        "execute_first_try_rate": first_try_rate,
        "execute_retry_rate": retry_rate,
        "partial_turn_rate": partial_rate,
        "worktree_usage_rate": (
            merge["worktree"] / merge["gitish"] if merge["gitish"] else None
        ),
        "snapshot_override_rate": (
            merge["snapshot_override"] / merge["total"] if merge["total"] else None
        ),
        "merge_first_success_rate": (
            merge["merge_first_success"] / merge["worktree_terminal"]
            if merge["worktree_terminal"]
            else None
        ),
        "merge_conflict_rate": (
            merge["merge_conflict"] / merge["worktree"] if merge["worktree"] else None
        ),
    }
    counts = {
        "objections": obj,
        "executions": exe,
        "execute_merge": merge,
        "turns": turns,
    }
    return scores, counts


def evaluate_m4_milestones(
    scores: dict[str, float | None],
    counts: dict[str, dict[str, int]],
) -> dict[str, Any]:
    """M4 gates: objection resolution ≥80%, execute retry <30% (when data exists)."""
    obj_total = int((counts.get("objections") or {}).get("total") or 0)
    exe_terminal = int((counts.get("executions") or {}).get("terminal") or 0)
    obj_rate = scores.get("objection_resolution_rate")
    retry_rate = scores.get("execute_retry_rate")

    objection = {
        "metric": "objection_resolution_rate",
        "target": f">={M4_OBJECTION_RESOLUTION_MIN:.0%}",
        "applicable": obj_total > 0,
        "value": obj_rate,
        "pass": (
            obj_rate is not None and obj_rate >= M4_OBJECTION_RESOLUTION_MIN
            if obj_total > 0
            else None
        ),
    }
    execute_retry = {
        "metric": "execute_retry_rate",
        "target": f"<{M4_EXECUTE_RETRY_RATE_MAX:.0%}",
        "applicable": exe_terminal > 0,
        "value": retry_rate,
        "pass": (
            retry_rate is not None and retry_rate < M4_EXECUTE_RETRY_RATE_MAX
            if exe_terminal > 0
            else None
        ),
    }
    applicable = [m for m in (objection, execute_retry) if m["applicable"]]
    passes = [m for m in applicable if m["pass"] is True]
    fails = [m for m in applicable if m["pass"] is False]
    overall = None
    if applicable:
        overall = len(fails) == 0
    return {
        "objection_resolution": objection,
        "execute_retry": execute_retry,
        "applicable_count": len(applicable),
        "pass_count": len(passes),
        "fail_count": len(fails),
        "overall_pass": overall,
    }


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.0f}%"


def _milestone_line(name: str, row: dict[str, Any]) -> str:
    if not row.get("applicable"):
        return f"  {name}: n/a (no data this window)"
    status = "PASS" if row.get("pass") else "FAIL"
    return f"  {name}: {_pct(row.get('value'))} — M4 {status} ({row.get('target')})"


def build_weekly_report(
    root: Path,
    *,
    days: int = 7,
    include_fixtures: bool = False,
    as_of: date | None = None,
) -> dict[str, Any]:
    end = as_of or datetime.now(timezone.utc).date()
    start = end - timedelta(days=max(days - 1, 0))
    discovered = discover_sessions(
        root,
        days=days,
        include_fixtures=include_fixtures,
        as_of=end,
    )
    session_reports: list[dict[str, Any]] = []
    errors: list[str] = []
    for item in discovered:
        try:
            session_reports.append(score_session(item.folder))
        except Exception as exc:  # noqa: BLE001 — batch report should continue
            errors.append(f"{item.folder.name}: {exc}")

    aggregate_scores, aggregate_counts = aggregate_rates(session_reports)
    m4 = evaluate_m4_milestones(aggregate_scores, aggregate_counts)

    summary_lines = [
        f"Weekly KPI ({start.isoformat()} .. {end.isoformat()})",
        f"  sessions_dir: {root}",
        f"  sessions scored: {len(session_reports)} (discovered {len(discovered)})",
        f"  aggregate objection resolution: {_pct(aggregate_scores['objection_resolution_rate'])} "
        f"({aggregate_counts['objections']['resolved']}/"
        f"{aggregate_counts['objections']['total']} resolved)",
        f"  aggregate execute retry: {_pct(aggregate_scores['execute_retry_rate'])} "
        f"({aggregate_counts['executions']['retried']}/"
        f"{aggregate_counts['executions']['terminal']} terminal)",
        f"  aggregate partial turns: {_pct(aggregate_scores['partial_turn_rate'])} "
        f"({aggregate_counts['turns']['partial']}/{aggregate_counts['turns']['total']} turns)",
        f"  aggregate merge first-success: {_pct(aggregate_scores['merge_first_success_rate'])} "
        f"({aggregate_counts['execute_merge']['merge_first_success']}/"
        f"{aggregate_counts['execute_merge']['worktree_terminal']} worktree terminal)",
        "M4 milestones:",
        _milestone_line("objection resolution", m4["objection_resolution"]),
        _milestone_line("execute retry", m4["execute_retry"]),
    ]
    if m4["overall_pass"] is True:
        summary_lines.append("  overall M4: PASS")
    elif m4["overall_pass"] is False:
        summary_lines.append("  overall M4: FAIL")
    else:
        summary_lines.append("  overall M4: n/a (insufficient data)")

    if errors:
        summary_lines.append(f"  errors: {len(errors)}")

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "sessions_dir": str(root),
        "include_fixtures": include_fixtures,
        "sessions": [
            {
                "session_id": r["session_id"],
                "folder": r["folder"],
                "scores": r["scores"],
            }
            for r in session_reports
        ],
        "aggregate": {"scores": aggregate_scores, "counts": aggregate_counts},
        "m4_milestones": m4,
        "errors": errors,
        "summary_lines": summary_lines,
    }


def default_sessions_root() -> Path:
    return resolve_sessions_dir()
