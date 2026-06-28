#!/usr/bin/env python3
"""Mypy error-count ratchet for ``agent_lab.session`` (strict overrides in pyproject.toml)."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "tests" / "fixtures" / "mypy-session-ratchet.json"
PKG_SRC = ROOT / "src" / "agent_lab" / "session"
ERROR_RE = re.compile(r"^([^:]+):\d+: error:")


def resolve_mypy() -> str:
    venv = ROOT / ".venv" / "bin" / "mypy"
    if venv.is_file():
        return str(venv)
    on_path = shutil.which("mypy")
    if on_path:
        return on_path
    raise FileNotFoundError("mypy not found (.venv/bin/mypy or PATH)")


def run_pkg_mypy() -> tuple[int, dict[str, int]]:
    proc = subprocess.run(
        [resolve_mypy(), str(PKG_SRC.relative_to(ROOT))],
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args()
    if not (args.check or args.update or args.print):
        parser.error("one of --check, --update, or --print is required")

    _code, counts = run_pkg_mypy()
    total = sum(counts.values())
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8")) if BASELINE_PATH.is_file() else {}
    exclude = set(baseline.get("exclude_files", []))
    ratchet = sum(n for path, n in counts.items() if path not in exclude)
    max_allowed = int(baseline.get("max_ratchet_errors", ratchet))

    if args.print:
        print(f"session total={total} ratchet={ratchet} max_allowed={max_allowed}")
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
            "note": "Strict overrides: pyproject.toml [[tool.mypy.overrides]] agent_lab.session.*",
        }
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Updated {BASELINE_PATH.relative_to(ROOT)}: max_ratchet_errors={ratchet} total={total}")
        return 0

    if ratchet > max_allowed:
        print(f"session mypy ratchet FAILED: {ratchet} errors > baseline {max_allowed}", file=sys.stderr)
        return 1

    print(f"session mypy ratchet OK: {ratchet}/{max_allowed} (total={total})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
