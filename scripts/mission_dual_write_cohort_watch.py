"""Dual-write cohort 관찰 — verify + health daemon 주기 스냅샷."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _fetch_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--minutes", type=int, default=60)
    parser.add_argument("--interval-sec", type=int, default=300)
    parser.add_argument("--cohort", action="store_true", help="pass --cohort to verify script")
    parser.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args()

    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.minutes * 60
    tick = 0
    hard_failures = 0

    while time.monotonic() < deadline:
        tick += 1
        ts = datetime.now(UTC).isoformat()
        verify_cmd = [
            sys.executable,
            str(ROOT / "scripts" / "mission_dual_write_verify.py"),
            "--sessions",
            str(args.sessions),
        ]
        if args.cohort:
            verify_cmd.append("--cohort")
        proc = subprocess.run(verify_cmd, capture_output=True, text=True, check=False)
        verify = json.loads(proc.stdout) if proc.stdout.strip() else {"stderr": proc.stderr[:500]}
        try:
            health = _fetch_json(f"{args.base_url.rstrip('/')}/api/health/daemon")
        except OSError as exc:
            health = {"error": str(exc)[:300]}
        entry = {
            "tick": tick,
            "at": ts,
            "verify_exit_code": proc.returncode,
            "hard_mismatch_count": verify.get("hard_mismatch_count"),
            "migrated_count": verify.get("migrated_count"),
            "dual_write": health.get("dual_write"),
            "last_activity_recovery": health.get("last_activity_recovery_result"),
        }
        with args.ledger.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if proc.returncode != 0:
            hard_failures += 1
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(args.interval_sec, remaining))

    summary = {
        "kind": "cohort_watch",
        "minutes": args.minutes,
        "ticks": tick,
        "hard_failure_ticks": hard_failures,
        "ledger": str(args.ledger),
        "cohort_env": os.getenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", ""),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if hard_failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
