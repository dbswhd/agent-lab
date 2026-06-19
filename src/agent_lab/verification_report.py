from __future__ import annotations

import json
import shlex
from pathlib import Path
from re import search
from typing import Literal, NotRequired, TypedDict

VerificationLaneId = Literal["fast", "integration", "bridge", "ci_full", "live"]
VerificationStatus = Literal["passed", "failed", "not_run", "running", "unknown"]

LANE_IDS: tuple[VerificationLaneId, ...] = ("fast", "integration", "bridge", "ci_full", "live")
LANE_LABELS: dict[VerificationLaneId, str] = {
    "fast": "Fast",
    "integration": "Integration",
    "bridge": "Bridge",
    "ci_full": "CI full",
    "live": "Live",
}
LANE_COMMANDS: dict[VerificationLaneId, str] = {
    "fast": "make test-fast",
    "integration": "make test-integration",
    "bridge": "make test-bridge",
    "ci_full": "make ci-full",
    "live": "AGENT_LAB_RUN_LIVE=1 make test-live",
}
LANE_MARKER_EXPRESSIONS: dict[VerificationLaneId, str | None] = {
    "fast": "not live and not integration and not bridge",
    "integration": "integration and not live and not bridge",
    "bridge": "bridge and not live",
    "ci_full": None,
    "live": "live",
}


class VerificationLaneReport(TypedDict):
    lane: VerificationLaneId
    label: str
    command: str
    marker_expression: str | None
    status: VerificationStatus
    exit_code: int | None
    started_at: str | None
    finished_at: str | None
    duration_seconds: float | None
    selected_count: int | None
    total_count: int | None
    failure_summary: str | None
    report_path: NotRequired[str]


class VerificationReport(TypedDict):
    generated_at: str | None
    report_dir: str
    lanes: dict[VerificationLaneId, VerificationLaneReport]


def verification_reports_dir(sessions_dir: Path) -> Path:
    return sessions_dir / "_reports"


def parse_collect_counts(output: str) -> tuple[int | None, int | None]:
    selected_total = search(r"(\d+)/(\d+) tests collected", output)
    if selected_total:
        return int(selected_total.group(1)), int(selected_total.group(2))
    selected_only = search(r"(\d+) tests collected", output)
    if selected_only:
        count = int(selected_only.group(1))
        return count, count
    return None, None


def default_lane_report(lane: VerificationLaneId, *, report_path: str | None = None) -> VerificationLaneReport:
    row: VerificationLaneReport = {
        "lane": lane,
        "label": LANE_LABELS[lane],
        "command": LANE_COMMANDS[lane],
        "marker_expression": LANE_MARKER_EXPRESSIONS[lane],
        "status": "not_run",
        "exit_code": None,
        "started_at": None,
        "finished_at": None,
        "duration_seconds": None,
        "selected_count": None,
        "total_count": None,
        "failure_summary": None,
    }
    if report_path:
        row["report_path"] = report_path
    return row


def _normalize_lane_report(raw: object, lane: VerificationLaneId, report_path: Path) -> VerificationLaneReport:
    if not isinstance(raw, dict):
        return default_lane_report(lane, report_path=str(report_path))
    base = default_lane_report(lane, report_path=str(report_path))
    status = raw.get("status")
    if status in ("passed", "failed", "not_run", "running", "unknown"):
        base["status"] = status
    exit_code = raw.get("exit_code")
    if isinstance(exit_code, int):
        base["exit_code"] = exit_code
    started_at = raw.get("started_at")
    if isinstance(started_at, str):
        base["started_at"] = started_at
    finished_at = raw.get("finished_at")
    if isinstance(finished_at, str):
        base["finished_at"] = finished_at
    failure_summary = raw.get("failure_summary")
    if isinstance(failure_summary, str):
        base["failure_summary"] = failure_summary
    duration = raw.get("duration_seconds")
    if isinstance(duration, int | float):
        base["duration_seconds"] = round(float(duration), 3)
    selected_count = raw.get("selected_count")
    if isinstance(selected_count, int):
        base["selected_count"] = selected_count
    total_count = raw.get("total_count")
    if isinstance(total_count, int):
        base["total_count"] = total_count
    command = raw.get("command")
    if isinstance(command, str) and command:
        base["command"] = command
    marker = raw.get("marker_expression")
    if isinstance(marker, str) or marker is None:
        base["marker_expression"] = marker
    return base


def _read_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    except json.JSONDecodeError:
        return None


def build_verification_report(sessions_dir: Path) -> VerificationReport:
    report_dir = verification_reports_dir(sessions_dir)
    latest_path = report_dir / "verification-latest.json"
    latest = _read_json(latest_path)
    generated_at = None
    lanes: dict[VerificationLaneId, VerificationLaneReport] = {}
    latest_lanes = latest.get("lanes") if isinstance(latest, dict) else None
    if isinstance(latest, dict) and isinstance(latest.get("generated_at"), str):
        generated_at = latest["generated_at"]
    for lane in LANE_IDS:
        lane_path = report_dir / f"verification-{lane}-latest.json"
        raw = latest_lanes.get(lane) if isinstance(latest_lanes, dict) else _read_json(lane_path)
        lanes[lane] = _normalize_lane_report(raw, lane, lane_path)
    return {"generated_at": generated_at, "report_dir": str(report_dir), "lanes": lanes}


def update_verification_report(
    *,
    sessions_dir: Path,
    lane: VerificationLaneId,
    command: list[str],
    marker_expression: str | None,
    status: VerificationStatus,
    exit_code: int,
    started_at: str,
    finished_at: str,
    duration_seconds: float,
    selected_count: int | None,
    total_count: int | None,
    failure_summary: str | None,
) -> VerificationReport:
    report_dir = verification_reports_dir(sessions_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    lane_path = report_dir / f"verification-{lane}-latest.json"
    lane_report: VerificationLaneReport = {
        "lane": lane,
        "label": LANE_LABELS[lane],
        "command": shlex.join(command),
        "marker_expression": marker_expression,
        "status": status,
        "exit_code": exit_code,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": round(duration_seconds, 3),
        "selected_count": selected_count,
        "total_count": total_count,
        "failure_summary": failure_summary,
        "report_path": str(lane_path),
    }
    lane_path.write_text(json.dumps(lane_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = build_verification_report(sessions_dir)
    report["generated_at"] = finished_at
    report["lanes"][lane] = lane_report
    latest_path = report_dir / "verification-latest.json"
    latest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
