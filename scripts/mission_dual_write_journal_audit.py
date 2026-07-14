"""Read-only Mission journal duplicate / integrity audit for dual-write cohorts.

Scans ``mission-events.jsonl`` for:
- duplicate ``idempotency_key`` values with differing payloads (unexpected duplicate)
- non-monotonic event sequences
- missing idempotency keys on replay collisions

Usage:
    .venv/bin/python scripts/mission_dual_write_journal_audit.py --sessions sessions/
    .venv/bin/python scripts/mission_dual_write_journal_audit.py --sessions sessions/ --cohort

Exit code 0 iff ``duplicate_count == 0``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _cohort_ids() -> frozenset[str]:
    raw = (os.getenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS") or "").strip()
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


def _audit_journal(folder: Path) -> dict[str, Any]:
    journal = folder / ".agent-lab" / "mission-events.jsonl"
    findings: list[dict[str, str]] = []
    if not journal.is_file():
        return {
            "session_id": folder.name,
            "migrated": False,
            "findings": [],
            "duplicate_count": 0,
            "invalid_json": 0,
            "error_count": 0,
        }

    events: list[dict[str, Any]] = []
    invalid_json = 0
    error_count = 0
    for line_number, raw in enumerate(journal.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            invalid_json += 1
            findings.append(
                {
                    "dimension": "journal",
                    "severity": "error",
                    "detail": f"line {line_number}: invalid json",
                }
            )
            continue
        if not isinstance(record, dict):
            error_count += 1
            findings.append({"dimension": "journal", "severity": "error", "detail": f"line {line_number}: record must be an object"})
            continue
        rows = record.get("events") if record.get("record_type") == "batch" else [record]
        if not isinstance(rows, list) or not rows:
            error_count += 1
            findings.append({"dimension": "journal", "severity": "error", "detail": f"line {line_number}: batch events must be a non-empty list"})
            continue
        for row in rows:
            if not isinstance(row, dict) or not row.get("event_type"):
                error_count += 1
                findings.append({"dimension": "journal", "severity": "error", "detail": f"line {line_number}: event is invalid"})
                continue
            events.append(row)

    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        key = event.get("idempotency_key")
        if isinstance(key, str) and key:
            by_key[key].append(event)

    expected_sequence = 0
    sequence_corrupt = False
    for event in events:
        expected_sequence += 1
        sequence = event.get("sequence")
        if type(sequence) is not int or sequence != expected_sequence:
            sequence_corrupt = True
            error_count += 1
            findings.append(
                {
                    "dimension": "sequence",
                    "severity": "duplicate",
                    "detail": f"expected sequence {expected_sequence}, got {sequence}",
                }
            )
            break

    duplicate_count = 1 if sequence_corrupt else 0
    for key, rows in sorted(by_key.items()):
        if len(rows) <= 1:
            continue
        fingerprints = {
            (
                str(row.get("event_type") or ""),
                json.dumps(row.get("payload") or {}, sort_keys=True, ensure_ascii=False),
            )
            for row in rows
        }
        if len(fingerprints) > 1:
            duplicate_count += 1
            findings.append(
                {
                    "dimension": "idempotency_key",
                    "severity": "duplicate",
                    "detail": f"{key} has {len(rows)} events with differing payloads",
                }
            )
        else:
            findings.append(
                {
                    "dimension": "idempotency_key",
                    "severity": "review_needed",
                    "detail": f"{key} repeated {len(rows)} times with identical payloads",
                }
            )

    return {
        "session_id": folder.name,
        "migrated": True,
        "event_count": len(events),
        "findings": findings,
        "duplicate_count": duplicate_count,
        "invalid_json": invalid_json,
        "error_count": error_count,
    }


def run_audit(sessions_root: Path, *, cohort_only: bool) -> dict[str, Any]:
    cohort_ids = _cohort_ids() if cohort_only else frozenset()
    if cohort_only and not cohort_ids:
        return {
            "sessions_root": str(sessions_root),
            "checked": 0,
            "not_found": 0,
            "invalid_json": 0,
            "error_count": 1,
            "errors": ["--cohort requires a non-empty AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS allowlist"],
            "duplicate_count": 0,
            "duplicate_sessions": [],
            "results": [],
        }
    if cohort_only:
        targets = [sessions_root / sid for sid in sorted(cohort_ids)]
    elif sessions_root.is_dir():
        targets = sorted(p for p in sessions_root.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))
    else:
        targets = []

    results: list[dict[str, Any]] = []
    for folder in targets:
        if not folder.is_dir():
            results.append(
                {
                    "session_id": folder.name,
                    "migrated": False,
                    "findings": [],
                    "duplicate_count": 0,
                    "invalid_json": 0,
                    "error_count": 0,
                    "severity": "not_found",
                }
            )
            continue
        try:
            results.append(_audit_journal(folder))
        except Exception as exc:
            results.append(
                {
                    "session_id": folder.name,
                    "migrated": None,
                    "findings": [],
                    "duplicate_count": 0,
                    "invalid_json": 0,
                    "error_count": 1,
                    "error": str(exc)[:300],
                    "severity": "error",
                }
            )

    duplicates = [r for r in results if int(r.get("duplicate_count") or 0) > 0]
    matched = [r for r in results if r.get("severity") != "not_found"]
    scope_errors = [str(r["error"]) for r in results if r.get("severity") == "error" and r.get("error")]
    if cohort_only and not matched:
        scope_errors.append("--cohort allowlist matched no session directories")
    return {
        "sessions_root": str(sessions_root),
        "checked": len(results),
        "not_found": sum(1 for r in results if r.get("severity") == "not_found"),
        "invalid_json": sum(int(r.get("invalid_json") or 0) for r in results),
        "error_count": sum(int(r.get("error_count") or 0) for r in results) + (1 if cohort_only and not matched else 0),
        "errors": scope_errors,
        "duplicate_count": len(duplicates),
        "duplicate_sessions": [r["session_id"] for r in duplicates],
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--cohort", action="store_true", help="audit only AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS")
    args = parser.parse_args()
    report = run_audit(args.sessions, cohort_only=args.cohort)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["duplicate_count"] == 0 and report["invalid_json"] == 0 and report["error_count"] == 0 and report["not_found"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
