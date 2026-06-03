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
)


def main() -> int:
    argv = sys.argv[1:]
    as_json = "--json" in argv
    strict = "--strict" in argv
    include_fixtures = "--include-fixtures" in argv
    write_path: Path | None = None
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
    )
    if write_path:
        write_path.parent.mkdir(parents=True, exist_ok=True)
        write_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
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

    if strict:
        m4 = report.get("m4_milestones") or {}
        if m4.get("overall_pass") is False:
            return 2
    return 0


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.0f}%"


_USAGE = """Usage: score_sessions_weekly.py [options]

Options:
  --sessions-dir PATH   Sessions root (default: resolve_sessions_dir())
  --days N              Rolling window, default 7 (inclusive)
  --include-fixtures    Include sessions/_regression and _benchmark
  --json                Machine-readable report on stdout
  --write PATH          Also write JSON report to PATH
  --strict              Exit 2 when applicable M4 milestones fail
  -h, --help

M4 targets: objection resolution >= 80%, execute retry rate < 30%.
"""


if __name__ == "__main__":
    raise SystemExit(main())
