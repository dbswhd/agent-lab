#!/usr/bin/env python3
"""Mission dogfood KPI report — score-session + notepad checks (docs/MISSION-DOGFOOD.md)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_lab.session_score import score_session  # noqa: E402

_NOTEPAD_FILES = ("verification.md", "learnings.md", "decisions.md")
_MIN_NOTEPAD_CHARS = 200


def _notepad_report(folder: Path) -> tuple[int, list[str]]:
    lines: list[str] = []
    total = 0
    for name in _NOTEPAD_FILES:
        path = folder / name
        if not path.is_file():
            lines.append(f"missing: {name}")
            continue
        try:
            chars = len(path.read_text(encoding="utf-8").strip())
        except OSError as exc:
            lines.append(f"read error {name}: {exc}")
            continue
        total += chars
        lines.append(f"{name}: {chars} chars")
    return total, lines


def evaluate(folder: Path) -> dict:
    folder = folder.expanduser().resolve()
    if not (folder / "run.json").is_file():
        raise FileNotFoundError(f"run.json missing: {folder}")
    report = score_session(folder)
    ml = report.get("counts", {}).get("mission_loop") or {}
    scores = report.get("scores") or {}
    notepad_chars, notepad_lines = _notepad_report(folder)
    checks: list[dict[str, object]] = []

    if ml.get("enabled"):
        checks.append(
            {
                "name": "mission_enabled",
                "ok": True,
                "detail": f"phase iteration={ml.get('iteration', 0)}",
            }
        )
        checks.append(
            {
                "name": "circuit_breaker_off",
                "ok": not ml.get("circuit_breaker"),
                "detail": f"circuit_breaker={ml.get('circuit_breaker', 0)}",
            }
        )
        checks.append(
            {
                "name": "notepad_chars",
                "ok": notepad_chars >= _MIN_NOTEPAD_CHARS
                or int(ml.get("notepad_chars") or 0) >= _MIN_NOTEPAD_CHARS,
                "detail": f"chars={max(notepad_chars, int(ml.get('notepad_chars') or 0))} "
                f"(min {_MIN_NOTEPAD_CHARS})",
            }
        )
        completed = scores.get("mission_completed")
        if completed is not None:
            checks.append(
                {
                    "name": "mission_completed",
                    "ok": completed == 1.0,
                    "detail": f"mission_completed={completed}",
                }
            )
    else:
        checks.append(
            {
                "name": "mission_enabled",
                "ok": False,
                "detail": "mission_loop not enabled in run.json",
            }
        )

    ok = all(bool(c["ok"]) for c in checks)
    return {
        "session_id": folder.name,
        "folder": str(folder),
        "ok": ok,
        "checks": checks,
        "notepad_lines": notepad_lines,
        "score_summary": report.get("summary_lines") or [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "session",
        type=Path,
        help="Session folder (e.g. sessions/<id>)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    args = parser.parse_args()
    try:
        payload = evaluate(args.session)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        status = "OK" if payload["ok"] else "FAIL"
        print(f"{status}: mission dogfood — {payload['session_id']}")
        for row in payload["checks"]:
            mark = "✓" if row["ok"] else "✗"
            print(f"  {mark} {row['name']}: {row['detail']}")
        for line in payload["notepad_lines"]:
            print(f"  notepad · {line}")
        for line in payload["score_summary"]:
            if "mission" in line.lower():
                print(f"  {line.strip()}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
