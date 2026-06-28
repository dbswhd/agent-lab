#!/usr/bin/env python3
"""Mypy error-count ratchet — fail CI when typing debt grows."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "tests" / "fixtures" / "mypy-ratchet.json"
ERROR_RE = re.compile(r"^([^:]+):\d+: error:")


def resolve_mypy() -> str:
    venv = ROOT / ".venv" / "bin" / "mypy"
    if venv.is_file():
        return str(venv)
    on_path = shutil.which("mypy")
    if on_path:
        return on_path
    raise FileNotFoundError("mypy not found (.venv/bin/mypy or PATH)")


def run_mypy() -> tuple[int, dict[str, int]]:
    proc = subprocess.run(
        [resolve_mypy()],
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


def ratchet_count(counts: dict[str, int], exclude_files: list[str], exclude_prefixes: list[str] | None = None) -> int:
    excluded = set(exclude_files)
    prefixes = tuple(exclude_prefixes or ())
    total = 0
    for path, n in counts.items():
        if path in excluded:
            continue
        if any(path.startswith(prefix) for prefix in prefixes):
            continue
        total += n
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Exit 1 if ratchet count exceeds baseline")
    parser.add_argument("--update", action="store_true", help="Rewrite baseline from current mypy output")
    parser.add_argument("--print", action="store_true", help="Print current counts vs baseline")
    args = parser.parse_args()
    if not (args.check or args.update or args.print):
        parser.error("one of --check, --update, or --print is required")

    _code, counts = run_mypy()
    total = sum(counts.values())
    baseline = load_baseline() if BASELINE_PATH.is_file() else {}
    exclude = list(baseline.get("exclude_files", []))
    exclude_prefixes = list(baseline.get("exclude_prefixes", []))
    if args.update and not exclude_prefixes:
        exclude_prefixes = [
            "src/agent_lab/room/",
            "src/agent_lab/plan/",
            "src/agent_lab/session/",
            "src/agent_lab/kimi/",
            "src/agent_lab/mission/",
            "src/agent_lab/agent/",
        ]
    ratchet = ratchet_count(counts, exclude, exclude_prefixes)

    if args.print:
        excluded_counts = {path: counts.get(path, 0) for path in exclude}
        print(f"total={total} ratchet={ratchet} excluded={exclude} exclude_prefixes={exclude_prefixes}")
        for path, n in excluded_counts.items():
            print(f"  {path}: {n} errors (notes ignored — grep 'room.py:' over-counts)")
        print(f"baseline max_ratchet_errors={baseline.get('max_ratchet_errors', '?')}")
        return 0

    if args.update:
        payload = {
            "version": 1,
            "exclude_files": exclude or ["src/agent_lab/room/__init__.py"],
            "exclude_prefixes": exclude_prefixes
            or [
                "src/agent_lab/room/",
                "src/agent_lab/plan/",
                "src/agent_lab/session/",
                "src/agent_lab/kimi/",
                "src/agent_lab/mission/",
                "src/agent_lab/agent/",
            ],
            "max_ratchet_errors": ratchet,
            "total_errors_snapshot": total,
            "note": "Ratchet applies outside exclude_files and exclude_prefixes. Package strict debt: mypy_*_ratchet.py scripts.",
        }
        write_baseline(payload)
        print(f"Updated {BASELINE_PATH.relative_to(ROOT)}: max_ratchet_errors={ratchet} total={total}")
        return 0

    max_allowed = int(baseline.get("max_ratchet_errors", ratchet))
    if ratchet > max_allowed:
        print(
            f"mypy ratchet FAILED: {ratchet} errors (excluding {exclude}) > baseline {max_allowed}",
            file=sys.stderr,
        )
        print(f"  total={total} — fix types or run: python scripts/mypy_ratchet.py --update", file=sys.stderr)
        return 1

    print(f"mypy ratchet OK: {ratchet}/{max_allowed} (total={total}, excluded={exclude})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
