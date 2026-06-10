#!/usr/bin/env python3
"""Weekly mission dogfood routine: mock run + KPI report + score-weekly rollup."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_lab.session_score_weekly import (  # noqa: E402
    build_weekly_report,
    default_sessions_root,
    format_weekly_report_markdown,
)


def _utc_today() -> str:
    return date.today().isoformat()


def run_weekly(
    *,
    sessions_root: Path,
    report_dir: Path,
    days: int,
    skip_mock: bool,
    include_fixtures: bool,
) -> dict:
    dogfood: dict | None = None
    session_folder: Path | None = None

    if not skip_mock:
        import importlib.util

        run_spec = importlib.util.spec_from_file_location(
            "mission_dogfood_run",
            ROOT / "scripts" / "mission_dogfood_run.py",
        )
        assert run_spec and run_spec.loader
        run_mod = importlib.util.module_from_spec(run_spec)
        run_spec.loader.exec_module(run_mod)
        session_folder = run_mod.run_dogfood(sessions_root=sessions_root)

        report_path = ROOT / "scripts" / "mission_dogfood_report.py"
        spec = importlib.util.spec_from_file_location("mission_dogfood_report", report_path)
        assert spec and spec.loader
        report_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(report_mod)
        dogfood = report_mod.evaluate(session_folder)

    weekly = build_weekly_report(
        sessions_root,
        days=days,
        include_fixtures=include_fixtures,
        report_dir=report_dir,
    )

    payload = {
        "generated_at": date.today().isoformat(),
        "mock_dogfood": dogfood,
        "mock_session_id": session_folder.name if session_folder else None,
        "weekly": weekly,
    }

    report_dir.mkdir(parents=True, exist_ok=True)
    end = str((weekly.get("period") or {}).get("end") or _utc_today())
    json_path = report_dir / f"dogfood-weekly-{end}.json"
    md_path = report_dir / f"dogfood-weekly-{end}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(_format_markdown(payload, weekly), encoding="utf-8")
    payload["artifact_paths"] = {"json": str(json_path), "markdown": str(md_path)}
    return payload


def _format_markdown(payload: dict, weekly: dict) -> str:
    lines = [
        f"# Mission dogfood weekly — {payload.get('generated_at')}",
        "",
        "## Mock dogfood",
    ]
    dogfood = payload.get("mock_dogfood")
    if isinstance(dogfood, dict):
        status = "OK" if dogfood.get("ok") else "FAIL"
        lines.append(f"- Session: `{payload.get('mock_session_id')}` — **{status}**")
        for row in dogfood.get("checks") or []:
            if isinstance(row, dict):
                mark = "x" if row.get("ok") else " "
                lines.append(f"  - [{mark}] {row.get('name')}: {row.get('detail')}")
    else:
        lines.append("- Skipped (`--skip-mock`)")

    lines.extend(["", "## Weekly KPI", ""])
    lines.append(format_weekly_report_markdown(weekly).strip())
    lines.extend(
        [
            "",
            "## Live dogfood (manual)",
            "",
            "Run one real mission with `AGENT_LAB_MISSION_LOOP=1` (optional `AGENT_LAB_ORACLE_LIVE=1`),",
            "then score the session:",
            "",
            "```bash",
            "make score-session SESSION=sessions/<id>",
            "python scripts/mission_dogfood_report.py sessions/<id>",
            "```",
            "",
            "SSOT for goal completion: `run.json` → `goal_loop.status` / `mission_loop.phase`.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sessions",
        type=Path,
        default=default_sessions_root(),
        help="Sessions root",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=None,
        help="Artifact directory (default: <sessions>/_reports)",
    )
    parser.add_argument("--days", type=int, default=7, help="Weekly rollup window")
    parser.add_argument("--skip-mock", action="store_true", help="Only run weekly rollup")
    parser.add_argument("--include-fixtures", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    sessions_root = args.sessions.expanduser().resolve()
    report_dir = (args.report_dir or (sessions_root / "_reports")).expanduser().resolve()

    payload = run_weekly(
        sessions_root=sessions_root,
        report_dir=report_dir,
        days=max(1, args.days),
        skip_mock=args.skip_mock,
        include_fixtures=args.include_fixtures,
    )

    if args.as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        dogfood = payload.get("mock_dogfood") or {}
        if dogfood:
            status = "OK" if dogfood.get("ok") else "FAIL"
            print(f"Mock dogfood: {status} ({payload.get('mock_session_id')})")
        else:
            print("Mock dogfood: skipped")
        for line in (payload.get("weekly") or {}).get("summary_lines") or []:
            print(line)
        paths = payload.get("artifact_paths") or {}
        if paths:
            print(f"Artifacts: {paths.get('markdown')}")

    dogfood_ok = not payload.get("mock_dogfood") or bool(payload.get("mock_dogfood", {}).get("ok"))
    return 0 if dogfood_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
