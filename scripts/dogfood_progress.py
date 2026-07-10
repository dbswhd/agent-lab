#!/usr/bin/env python3
"""Dogfood progress automation — track + auto-run catalog topics through execute/Oracle.

Persists progress in ``sessions/_benchmark/topics/suite-log.json`` (same schema as
EVAL-PROGRAM §8). Does **not** bypass Human gates: mock paths call
``approve_plan`` / ``resolve_execution`` explicitly; live paths still need API +
optional ``--auto-approve``.

Modes:
  status   — catalog vs suite-log coverage (done / remaining / blocked)
  record   — append one suite-log row after a manual/live session
  auto     — run automatable mock topics (Room + plan approve + execute + Oracle
             where wired), append suite-log, print progress

Automatable mock arms (Human gate called in-process, not skipped):
  - plain ``mock: run`` / ``scenario:*`` via ``run_dogfood_suite.run_mock``
  - X1 → ``mission_dogfood_run.run_dogfood`` (mission → VERIFY → MISSION_DONE)
  - X2 → ``x2_lift_dogfood_run.run_x2_lift_mock`` (plan → dry-run → merge → Oracle)

Still live/manual (listed as blocked until Human records them):
  L4, X3, X4, A1, and other ``live_only`` / ``skip:`` topics without a mock arm.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for _p in (ROOT / "src", SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

DEFAULT_TOPICS = ROOT / "sessions" / "_benchmark" / "topics" / "dogfood-v1.json"
DEFAULT_LOG = ROOT / "sessions" / "_benchmark" / "topics" / "suite-log.json"
REPORTS = ROOT / "sessions" / "_reports"

# Topics with dedicated execute/Oracle (or mission) mock drivers beyond suite scenarios.
_EXECUTE_DRIVERS: dict[str, str] = {
    "X1": "mission",
    "X2": "x2_lift",
}


def _load_suite():
    spec = importlib.util.spec_from_file_location("run_dogfood_suite", SCRIPTS / "run_dogfood_suite.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"expected JSON list: {path}")
    return [row for row in data if isinstance(row, dict)]


def _write_json_list(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _topic_automatable(entry: dict[str, Any]) -> tuple[bool, str]:
    """Return (can_auto_mock, reason)."""
    topic_id = str(entry.get("id") or "")
    if topic_id in _EXECUTE_DRIVERS:
        return True, f"driver:{_EXECUTE_DRIVERS[topic_id]}"
    mock = str(entry.get("mock") or "run")
    if mock.startswith("skip:"):
        return False, mock[5:]
    if entry.get("live_only") and mock == "run":
        # live_only + plain run still has no mock driver
        return False, "live_only"
    if mock == "run" or mock.startswith("scenario:"):
        return True, mock
    return False, f"unknown mock={mock}"


def build_progress(
    topics: list[dict[str, Any]],
    log_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    by_id: dict[str, list[dict[str, Any]]] = {}
    for row in log_rows:
        tid = str(row.get("id") or "")
        if tid:
            by_id.setdefault(tid, []).append(row)

    done: list[dict[str, Any]] = []
    remaining_auto: list[dict[str, Any]] = []
    remaining_manual: list[dict[str, Any]] = []

    for entry in topics:
        tid = str(entry.get("id"))
        runs = by_id.get(tid) or []
        passes = [r for r in runs if r.get("pass") is True]
        auto_ok, reason = _topic_automatable(entry)
        target_repeats = max(1, int(entry.get("repeat") or 1))
        pass_count = len(passes)
        item = {
            "id": tid,
            "tier": entry.get("tier"),
            "runs": len(runs),
            "pass_count": pass_count,
            "target_repeats": target_repeats,
            "automatable": auto_ok,
            "reason": reason,
        }
        if pass_count >= target_repeats:
            done.append(item)
        elif auto_ok:
            remaining_auto.append(item)
        else:
            remaining_manual.append(item)

    total = len(topics)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "done": len(done),
        "remaining_auto": len(remaining_auto),
        "remaining_manual": len(remaining_manual),
        "pct_done": round(100.0 * len(done) / total, 1) if total else 0.0,
        "done_ids": [r["id"] for r in done],
        "remaining_auto_ids": [r["id"] for r in remaining_auto],
        "remaining_manual_ids": [r["id"] for r in remaining_manual],
        "topics": {
            "done": done,
            "remaining_auto": remaining_auto,
            "remaining_manual": remaining_manual,
        },
    }


def append_suite_log(
    log_path: Path,
    *,
    topic_id: str,
    session: str,
    passed: bool,
    human_minutes: float | None = None,
    tags: list[str] | None = None,
    notes: str = "",
    repeat: int = 1,
) -> dict[str, Any]:
    rows = _load_json_list(log_path)
    row = {
        "id": topic_id,
        "session": session,
        "repeat": repeat,
        "pass": passed,
        "human_minutes": human_minutes if human_minutes is not None else 0,
        "tags": tags or ["auto"],
        "notes": notes,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    rows.append(row)
    _write_json_list(log_path, rows)
    return row


def _run_x1_mission(sessions_base: Path) -> dict[str, Any]:
    from mission_dogfood_run import run_dogfood

    folder = run_dogfood(sessions_root=sessions_base)
    report_path = SCRIPTS / "mission_dogfood_report.py"
    spec = importlib.util.spec_from_file_location("mission_dogfood_report", report_path)
    assert spec and spec.loader
    report_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report_mod)
    payload = report_mod.evaluate(folder)
    return {
        "ok": bool(payload.get("ok")),
        "session": str(folder),
        "session_id": folder.name,
        "detail": "mission dogfood → MISSION_DONE" if payload.get("ok") else "mission dogfood failed",
        "checks": payload.get("checks") or [],
    }


def _run_x2_lift(sessions_base: Path) -> dict[str, Any]:
    from x2_lift_dogfood_run import run_x2_lift_mock

    report = run_x2_lift_mock(sessions_base=sessions_base, restore_fixture=True)
    failed = report.get("failed") or []
    detail = (
        f"oracle={report.get('oracle_verdict')} exec={report.get('execution_status')}"
        if report.get("ok")
        else f"failed={[f.get('name') for f in failed]}"
    )
    return {
        "ok": bool(report.get("ok")),
        "session": str(report.get("session") or ""),
        "session_id": str(report.get("session_id") or ""),
        "detail": detail,
        "checks": report.get("checks") or [],
    }


def run_auto(
    topics: list[dict[str, Any]],
    *,
    log_path: Path,
    sessions_base: Path | None,
    only: set[str] | None,
    skip_done: bool,
    dry_run: bool,
) -> int:
    os.environ["AGENT_LAB_MOCK_AGENTS"] = "1"
    os.environ.setdefault("AGENT_LAB_CLARIFIER", "0")
    os.environ.setdefault("AGENT_LAB_INBOX_MODE", "soft")

    suite = _load_suite()
    progress = build_progress(topics, _load_json_list(log_path))
    done_ids = set(progress["done_ids"])

    base = sessions_base or Path(tempfile.mkdtemp(prefix="dogfood-progress-"))
    base.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for entry in topics:
        tid = str(entry.get("id"))
        if only and tid not in only:
            continue
        if skip_done and tid in done_ids:
            results.append({"id": tid, "status": "skip", "reason": "already_done"})
            print(f"  SKIP {tid}: already_done")
            continue
        auto_ok, reason = _topic_automatable(entry)
        if not auto_ok:
            results.append({"id": tid, "status": "blocked", "reason": reason})
            print(f"  BLOCKED {tid}: {reason}")
            continue
        if dry_run:
            results.append({"id": tid, "status": "would_run", "reason": reason})
            print(f"  WOULD_RUN {tid}: {reason}")
            continue

        try:
            driver = _EXECUTE_DRIVERS.get(tid)
            mock_mode = str(entry.get("mock") or "run")
            if driver == "mission" or mock_mode == "scenario:mission_dogfood":
                out = _run_x1_mission(base / f"x1-{tid}")
            elif driver == "x2_lift" or mock_mode == "scenario:x2_execute_oracle":
                out = _run_x2_lift(base)
            elif mock_mode.startswith("scenario:"):
                fn = suite.SCENARIOS.get(mock_mode.split(":", 1)[1])
                if fn is None:
                    raise RuntimeError(f"unknown scenario {mock_mode}")
                raw = fn(entry, base)
                out = {
                    "ok": bool(raw.get("ok")),
                    "session": f"sessions/{raw.get('session_id') or tid}",
                    "session_id": raw.get("session_id") or tid,
                    "detail": raw.get("detail") or "",
                }
            elif mock_mode == "run":
                folder, report = suite._run_topic_session(entry, base)
                out = {
                    "ok": bool(report.get("scores")),
                    "session": str(folder),
                    "session_id": folder.name,
                    "detail": "room run + score_session",
                }
            else:
                raise RuntimeError(f"unhandled automatable reason={reason}")

            status = "pass" if out.get("ok") else "fail"
            session_ref = out.get("session") or f"sessions/{out.get('session_id')}"
            if not str(session_ref).startswith("sessions/") and Path(str(session_ref)).is_dir():
                # Prefer repo-relative path when under ROOT/sessions
                try:
                    session_ref = str(Path(str(session_ref)).resolve().relative_to(ROOT))
                except ValueError:
                    session_ref = str(session_ref)

            append_suite_log(
                log_path,
                topic_id=tid,
                session=str(session_ref),
                passed=bool(out.get("ok")),
                tags=["auto", reason.split(":")[0] if ":" in reason else reason],
                notes=str(out.get("detail") or ""),
            )
            results.append({"id": tid, "status": status, **{k: out.get(k) for k in ("session_id", "detail")}})
            print(f"  {status.upper()} {tid}: {out.get('detail')}")
        except Exception as exc:  # noqa: BLE001 — progress runner continues
            results.append({"id": tid, "status": "error", "reason": str(exc)[:300]})
            print(f"  ERROR {tid}: {exc}")

    failed = [r for r in results if r["status"] in {"fail", "error"}]
    after = build_progress(topics, _load_json_list(log_path))
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = REPORTS / f"dogfood-progress-{stamp}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "auto",
        "dry_run": dry_run,
        "log": str(log_path),
        "results": results,
        "failed": len(failed),
        "progress": after,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(f"\nprogress: {after['done']}/{after['total']} ({after['pct_done']}%)")
    print(f"  remaining auto: {after['remaining_auto_ids']}")
    print(f"  remaining manual: {after['remaining_manual_ids']}")
    print(f"report: {out_path}")
    return 1 if failed else 0


def cmd_status(topics: list[dict[str, Any]], log_path: Path, *, as_json: bool) -> int:
    progress = build_progress(topics, _load_json_list(log_path))
    if as_json:
        print(json.dumps(progress, indent=2, ensure_ascii=False))
        return 0
    print(f"Dogfood progress — {progress['done']}/{progress['total']} ({progress['pct_done']}%)")
    print(f"  log: {log_path}")
    print(f"  done: {', '.join(progress['done_ids']) or '—'}")
    print(f"  remaining (auto): {', '.join(progress['remaining_auto_ids']) or '—'}")
    print(f"  remaining (manual/live): {', '.join(progress['remaining_manual_ids']) or '—'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["status", "record", "auto"],
        default="status",
        help="status | record | auto (default: status)",
    )
    parser.add_argument("--topics", type=Path, default=DEFAULT_TOPICS)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG, help="suite-log.json path")
    parser.add_argument("--tier", help="comma tiers (e.g. S,X)")
    parser.add_argument("--only", help="comma topic ids (e.g. X1,X2,S1)")
    parser.add_argument("--sessions-base", type=Path, help="session root for auto runs")
    parser.add_argument("--json", action="store_true", help="JSON output for status")
    parser.add_argument("--no-skip-done", action="store_true", help="re-run topics already passed")
    parser.add_argument("--dry-run", action="store_true", help="list what auto would run")
    # record
    parser.add_argument("--id", help="record: topic id")
    parser.add_argument("--session", help="record: sessions/<id> path")
    parser.add_argument("--pass", dest="passed", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--minutes", type=float, default=0.0)
    parser.add_argument("--notes", default="")
    parser.add_argument("--tags", default="manual", help="comma tags for record")
    args = parser.parse_args()

    suite = _load_suite()
    tiers = {t.strip().upper() for t in args.tier.split(",")} if args.tier else None
    only = {t.strip().upper() for t in args.only.split(",")} if args.only else None
    topics = suite.filter_topics(suite.load_topics(args.topics), tiers, only)

    if args.mode == "status":
        # status ignores --only filter for full picture unless --tier/--only set
        all_topics = suite.filter_topics(
            suite.load_topics(args.topics),
            tiers,
            only,
        )
        return cmd_status(all_topics, args.log, as_json=args.json)

    if args.mode == "record":
        if not args.id or not args.session:
            print("--mode record requires --id and --session", file=sys.stderr)
            return 2
        row = append_suite_log(
            args.log,
            topic_id=args.id.upper(),
            session=args.session,
            passed=bool(args.passed),
            human_minutes=args.minutes,
            tags=[t.strip() for t in args.tags.split(",") if t.strip()],
            notes=args.notes,
        )
        print(json.dumps(row, indent=2, ensure_ascii=False))
        return cmd_status(suite.load_topics(args.topics), args.log, as_json=False)

    return run_auto(
        topics,
        log_path=args.log,
        sessions_base=args.sessions_base,
        only=only,
        skip_done=not args.no_skip_done,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
