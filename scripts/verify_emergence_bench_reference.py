#!/usr/bin/env python3
"""Compare emergence bench output to committed mock reference (N8 reproducibility).

Usage:
    python scripts/verify_emergence_bench_reference.py --check
    python scripts/verify_emergence_bench_reference.py --check --reference PATH
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = ROOT / "sessions" / "_benchmark" / "reports" / "emergence-bench-reference-mock-20260706.json"


def _float_close(a: Any, b: Any, *, tol: float = 1e-9) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return math.isclose(float(a), float(b), rel_tol=0, abs_tol=tol)


def compare_by_category(got: dict[str, Any], ref: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    g = got.get("by_category") or {}
    r = ref.get("by_category") or {}
    if set(g.keys()) != set(r.keys()):
        errors.append(f"category keys differ: got={sorted(g)} ref={sorted(r)}")
        return errors
    for cat in sorted(r.keys()):
        gb = g[cat]
        rb = r[cat]
        if gb.get("topics") != rb.get("topics"):
            errors.append(f"{cat}: topics got={gb.get('topics')} ref={rb.get('topics')}")
        if gb.get("delta_positive") != rb.get("delta_positive"):
            errors.append(f"{cat}: delta_positive got={gb.get('delta_positive')} ref={rb.get('delta_positive')}")
        if not _float_close(gb.get("delta_mean"), rb.get("delta_mean")):
            errors.append(f"{cat}: delta_mean got={gb.get('delta_mean')} ref={rb.get('delta_mean')}")
    return errors


def run_bench(out_path: Path) -> int:
    from agent_lab.subprocess_env import subprocess_env

    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "emergence_bench.py"), "--out", str(out_path)],
        cwd=str(ROOT),
        env=subprocess_env(AGENT_LAB_MOCK_AGENTS="1"),
    )
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Run mock bench and compare to reference")
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--report", type=Path, help="Compare existing report JSON instead of running bench")
    args = parser.parse_args()

    if not args.check and not args.report:
        parser.error("pass --check or --report")

    ref_path = args.reference
    if not ref_path.is_file():
        print(f"reference missing: {ref_path}", file=sys.stderr)
        return 2
    reference = json.loads(ref_path.read_text(encoding="utf-8"))

    if args.report:
        got = json.loads(args.report.read_text(encoding="utf-8"))
    else:
        with tempfile.TemporaryDirectory(prefix="emergence-check-") as tmp:
            out = Path(tmp) / "report.json"
            code = run_bench(out)
            if code != 0:
                print("emergence bench failed", file=sys.stderr)
                return code
            got = json.loads(out.read_text(encoding="utf-8"))

    errors = compare_by_category(got, reference)
    if got.get("judge") != reference.get("judge"):
        errors.append(f"judge got={got.get('judge')!r} ref={reference.get('judge')!r}")
    if got.get("mock") is not reference.get("mock"):
        errors.append("mock flag mismatch")

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1

    print(f"OK: emergence bench matches reference ({ref_path.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
