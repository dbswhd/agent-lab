#!/usr/bin/env python3
"""Weekly real-usage KPI rollup from score_session (H4 / M4)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from agent_lab.session_score_weekly import (  # noqa: E402
    build_weekly_report,
    default_sessions_root,
    format_weekly_report_markdown,
    weekly_report_artifact_paths,
)


def main() -> int:
    argv = sys.argv[1:]
    as_json = "--json" in argv
    strict = "--strict" in argv
    include_fixtures = "--include-fixtures" in argv
    write_path: Path | None = None
    write_md_path: Path | None = None
    write_artifacts_dir: Path | None = None
    report_dir: Path | None = None
    days = 7
    root = default_sessions_root()

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--json", "--strict", "--include-fixtures"):
            i += 1
            continue
        if arg == "--days" and i + 1 < len(argv):
            days = max(1, int(argv[i + 1]))
            i += 2
            continue
        if arg == "--sessions-dir" and i + 1 < len(argv):
            root = Path(argv[i + 1]).expanduser()
            i += 2
            continue
        if arg == "--write" and i + 1 < len(argv):
            write_path = Path(argv[i + 1]).expanduser()
            i += 2
            continue
        if arg == "--write-md" and i + 1 < len(argv):
            write_md_path = Path(argv[i + 1]).expanduser()
            i += 2
            continue
        if arg == "--write-artifacts" and i + 1 < len(argv):
            write_artifacts_dir = Path(argv[i + 1]).expanduser()
            i += 2
            continue
        if arg == "--report-dir" and i + 1 < len(argv):
            report_dir = Path(argv[i + 1]).expanduser()
            i += 2
            continue
        if arg in ("-h", "--help"):
            print(_USAGE, file=sys.stderr)
            return 0
        print(f"Unknown argument: {arg}", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 1

    if not root.is_dir():
        print(f"Sessions directory not found: {root}", file=sys.stderr)
        return 1

    report = build_weekly_report(
        root,
        days=days,
        include_fixtures=include_fixtures,
        report_dir=report_dir or write_artifacts_dir or (root / "_reports"),
    )
    artifact_paths: dict[str, Path] = {}
    if write_artifacts_dir is not None:
        end = str((report.get("period") or {}).get("end") or "latest")
        artifact_paths = weekly_report_artifact_paths(end, write_artifacts_dir)
        write_path = artifact_paths["json"]
        write_md_path = artifact_paths["md"]

    if write_path:
        write_path.parent.mkdir(parents=True, exist_ok=True)
        write_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if write_md_path:
        write_md_path.parent.mkdir(parents=True, exist_ok=True)
        write_md_path.write_text(
            format_weekly_report_markdown(report),
            encoding="utf-8",
        )

    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for line in report.get("summary_lines") or []:
            print(line)
        if report.get("sessions"):
            print("")
            print("Per session:")
            for row in report["sessions"]:
                scores = row.get("scores") or {}
                print(
                    f"  - {row['session_id']}: "
                    f"objection {_fmt(scores.get('objection_resolution_rate'))}, "
                    f"retry {_fmt(scores.get('execute_retry_rate'))}"
                )
        if report.get("errors"):
            print("")
            print("Errors:", file=sys.stderr)
            for err in report["errors"]:
                print(f"  {err}", file=sys.stderr)
        if write_md_path:
            print("")
            print(_ops_line(report, write_md_path))

    if strict:
        m4 = report.get("m4_milestones") or {}
        if m4.get("overall_pass") is False:
            return 2
    return 0


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.0f}%"


def _ops_line(report: dict, md_path: Path) -> str:
    m4 = report.get("m4_milestones") or {}
    scores = ((report.get("aggregate") or {}).get("scores") or {})
    counts = (((report.get("aggregate") or {}).get("counts") or {}).get("capability_cwd") or {})
    live = report.get("live_ops_summary") or {}
    worktree = live.get("worktree") or {}
    merge = live.get("merge") or {}
    status = "PASS" if m4.get("overall_pass") is True else "FAIL" if m4.get("overall_pass") is False else "n/a"
    return (
        "Ops: "
        f"M4={status} | "
        f"cwd asymmetry={_fmt(scores.get('asymmetric_capability_cwd_rate'))} "
        f"({counts.get('asymmetric', 0)}/{counts.get('specialist_contexts', 0)}) | "
        f"live worktree={_live_status(worktree)} | "
        f"live merge={_live_status(merge)} | "
        f"report: {md_path}"
    )


def _live_status(row: dict) -> str:
    status = str(row.get("status") or "").strip()
    return status.upper() if status else "n/a"


_USAGE = """Usage: score_sessions_weekly.py [options]

Options:
  --sessions-dir PATH   Sessions root (default: resolve_sessions_dir())
  --days N              Rolling window, default 7 (inclusive)
  --include-fixtures    Include sessions/_regression and _benchmark
  --json                Machine-readable report on stdout
  --write PATH          Also write JSON report to PATH
  --write-md PATH       Also write Markdown ops report to PATH
  --write-artifacts DIR Write weekly-YYYY-MM-DD.json and .md to DIR
  --report-dir DIR      Scan live-worktree/live-merge JSON from DIR
  --strict              Exit 2 when applicable M4 milestones fail
  -h, --help

M4 targets: objection resolution >= 80%, execute retry rate < 30%.
"""


if __name__ == "__main__":
    raise SystemExit(main())
