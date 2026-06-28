#!/usr/bin/env python3
"""Mission dogfood KPI report — score-session + notepad checks (docs/MISSION-DOGFOOD.md)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_lab.session.score import score_session  # noqa: E402

_NOTEPAD_FILES = ("verification.md", "learnings.md", "decisions.md")
_MIN_NOTEPAD_CHARS = 200


def _notepad_report(folder: Path) -> tuple[int, list[str]]:
    from agent_lab.mission.notepad import mission_notepad_dir

    lines: list[str] = []
    total = 0
    mission_base = mission_notepad_dir(folder)
    session_has = any((folder / n).is_file() for n in _NOTEPAD_FILES)
    bases = [folder] if session_has else [mission_base, folder]
    for name in _NOTEPAD_FILES:
        path = None
        for base in bases:
            candidate = base / name
            if candidate.is_file():
                path = candidate
                break
        if path is None:
            lines.append(f"missing: {name}")
            continue
        try:
            chars = len(path.read_text(encoding="utf-8").strip())
        except OSError as exc:
            lines.append(f"read error {name}: {exc}")
            continue
        total += chars
        rel = path.name if path.parent == folder else f"~/.agent-lab/missions/{folder.name}/{name}"
        lines.append(f"{rel}: {chars} chars")
    return total, lines


def _latest_oracle_evidence(folder: Path) -> list[str]:
    import json

    run_path = folder / "run.json"
    try:
        run = json.loads(run_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    for row in reversed(run.get("executions") or []):
        if not isinstance(row, dict):
            continue
        oracle = row.get("oracle") if isinstance(row.get("oracle"), dict) else {}
        evidence = oracle.get("evidence") or []
        if isinstance(evidence, list) and evidence:
            return [str(x) for x in evidence[:5] if str(x).strip()]
    return []


def evaluate(folder: Path) -> dict:
    folder = folder.expanduser().resolve()
    if not (folder / "run.json").is_file():
        raise FileNotFoundError(f"run.json missing: {folder}")
    report = score_session(folder)
    oracle_evidence = _latest_oracle_evidence(folder)
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
                "ok": notepad_chars >= _MIN_NOTEPAD_CHARS or int(ml.get("notepad_chars") or 0) >= _MIN_NOTEPAD_CHARS,
                "detail": f"chars={max(notepad_chars, int(ml.get('notepad_chars') or 0))} (min {_MIN_NOTEPAD_CHARS})",
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

    if oracle_evidence:
        checks.append(
            {
                "name": "oracle_evidence",
                "ok": True,
                "detail": f"{len(oracle_evidence)} bullet(s) on latest execution",
            }
        )
    ok = all(bool(c["ok"]) for c in checks)
    return {
        "session_id": folder.name,
        "folder": str(folder),
        "ok": ok,
        "checks": checks,
        "notepad_lines": notepad_lines,
        "oracle_evidence": oracle_evidence,
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
        for row in payload.get("oracle_evidence") or []:
            print(f"  oracle · {row}")
        for line in payload["score_summary"]:
            if "mission" in line.lower():
                print(f"  {line.strip()}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
