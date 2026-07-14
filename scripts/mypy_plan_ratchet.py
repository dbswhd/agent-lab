#!/usr/bin/env python3
"""Mypy error-count ratchet for ``agent_lab.plan`` (strict overrides in pyproject.toml).

Usage:
    python scripts/mypy_plan_ratchet.py --check
    python scripts/mypy_plan_ratchet.py --update
    python scripts/mypy_plan_ratchet.py --print
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "tests" / "fixtures" / "mypy-plan-ratchet.json"
PLAN_SRC = ROOT / "src" / "agent_lab" / "plan"
ERROR_RE = re.compile(r"^([^:]+):\d+: error:")


def resolve_mypy() -> str:
    # Prefer the running interpreter's own venv (sys.executable) over a
    # ROOT-relative guess — see scripts/mypy_vendor_ratchet.py for why.
    sibling = Path(sys.executable).with_name("mypy")
    if sibling.is_file():
        return str(sibling)
    venv = ROOT / ".venv" / "bin" / "mypy"
    if venv.is_file():
        return str(venv)
    on_path = shutil.which("mypy")
    if on_path:
        return on_path
    raise FileNotFoundError("mypy not found (next to sys.executable, .venv/bin/mypy, or PATH)")


def run_plan_mypy() -> tuple[int, dict[str, int]]:
    proc = subprocess.run(
        [resolve_mypy(), str(PLAN_SRC.relative_to(ROOT))],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = proc.stdout + proc.stderr
    counts: dict[str, int] = {}
    for line in combined.splitlines():
        match = ERROR_RE.match(line)
        if match:
            path = match.group(1)
            counts[path] = counts.get(path, 0) + 1
    return proc.returncode, counts


def load_baseline() -> dict:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def write_baseline(payload: dict) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Exit 1 if plan error count exceeds baseline")
    parser.add_argument("--update", action="store_true", help="Rewrite plan ratchet baseline")
    parser.add_argument("--print", action="store_true", help="Print current plan counts vs baseline")
    args = parser.parse_args()
    if not (args.check or args.update or args.print):
        parser.error("one of --check, --update, or --print is required")

    _code, counts = run_plan_mypy()
    total = sum(counts.values())
    baseline = load_baseline() if BASELINE_PATH.is_file() else {}
    exclude = set(baseline.get("exclude_files", []))
    ratchet = sum(n for path, n in counts.items() if path not in exclude)
    max_allowed = int(baseline.get("max_ratchet_errors", ratchet))

    if args.print:
        print(f"plan total={total} ratchet={ratchet} max_allowed={max_allowed}")
        for path, n in sorted(counts.items()):
            tag = " (excluded)" if path in exclude else ""
            print(f"  {path}: {n}{tag}")
        return 0

    if args.update:
        payload = {
            "version": 1,
            "exclude_files": sorted(exclude),
            "max_ratchet_errors": ratchet,
            "total_errors_snapshot": total,
            "note": "Strict overrides: pyproject.toml [[tool.mypy.overrides]] agent_lab.plan.*",
        }
        write_baseline(payload)
        print(f"Updated {BASELINE_PATH.relative_to(ROOT)}: max_ratchet_errors={ratchet} total={total}")
        return 0

    if ratchet > max_allowed:
        print(
            f"plan mypy ratchet FAILED: {ratchet} errors > baseline {max_allowed}",
            file=sys.stderr,
        )
        print(
            f"  total={total} — fix types or run: python scripts/mypy_plan_ratchet.py --update",
            file=sys.stderr,
        )
        return 1

    print(f"plan mypy ratchet OK: {ratchet}/{max_allowed} (total={total})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
