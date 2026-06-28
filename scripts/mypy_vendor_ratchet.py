#!/usr/bin/env python3
"""Mypy error-count ratchet for vendor packages (cursor, codex, claude)."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ERROR_RE = re.compile(r"^([^:]+):\d+: error:")

PACKAGES = {
    "cursor": {
        "src": ROOT / "src" / "agent_lab" / "cursor",
        "baseline": ROOT / "tests" / "fixtures" / "mypy-cursor-ratchet.json",
        "mypy_module": "agent_lab.cursor.*",
    },
    "codex": {
        "src": ROOT / "src" / "agent_lab" / "codex",
        "baseline": ROOT / "tests" / "fixtures" / "mypy-codex-ratchet.json",
        "mypy_module": "agent_lab.codex.*",
    },
    "claude": {
        "src": ROOT / "src" / "agent_lab" / "claude",
        "baseline": ROOT / "tests" / "fixtures" / "mypy-claude-ratchet.json",
        "mypy_module": "agent_lab.claude.*",
    },
    "local": {
        "src": ROOT / "src" / "agent_lab" / "local",
        "baseline": ROOT / "tests" / "fixtures" / "mypy-local-ratchet.json",
        "mypy_module": "agent_lab.local.*",
    },
}


def resolve_mypy() -> str:
    venv = ROOT / ".venv" / "bin" / "mypy"
    if venv.is_file():
        return str(venv)
    on_path = shutil.which("mypy")
    if on_path:
        return on_path
    raise FileNotFoundError("mypy not found (.venv/bin/mypy or PATH)")


def run_pkg_mypy(pkg_src: Path) -> tuple[int, dict[str, int]]:
    proc = subprocess.run(
        [resolve_mypy(), str(pkg_src.relative_to(ROOT))],
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
    parser.add_argument("--package", choices=sorted(PACKAGES), required=True)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args()
    if not (args.check or args.update or args.print):
        parser.error("one of --check, --update, or --print is required")

    meta = PACKAGES[args.package]
    pkg_src: Path = meta["src"]
    baseline_path: Path = meta["baseline"]
    mypy_module: str = meta["mypy_module"]

    _code, counts = run_pkg_mypy(pkg_src)
    total = sum(counts.values())
    baseline = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.is_file() else {}
    exclude = set(baseline.get("exclude_files", []))
    ratchet = sum(n for path, n in counts.items() if path not in exclude)
    max_allowed = int(baseline.get("max_ratchet_errors", ratchet))

    if args.print:
        print(f"{args.package} total={total} ratchet={ratchet} max_allowed={max_allowed}")
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
            "note": f"Strict overrides: pyproject.toml [[tool.mypy.overrides]] {mypy_module}",
        }
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Updated {baseline_path.relative_to(ROOT)}: max_ratchet_errors={ratchet} total={total}")
        return 0

    if ratchet > max_allowed:
        print(
            f"{args.package} mypy ratchet FAILED: {ratchet} errors > baseline {max_allowed}",
            file=sys.stderr,
        )
        return 1

    print(f"{args.package} mypy ratchet OK: {ratchet}/{max_allowed} (total={total})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
