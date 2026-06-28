#!/usr/bin/env python3
"""Compare two room session folders (run metadata + plan.md)."""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from agent_lab.plan.refs import validate_plan_refs  # noqa: E402


def _load_run(folder: Path) -> dict[str, Any]:
    path = folder / "run.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _load_plan(folder: Path) -> str:
    path = folder / "plan.md"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _turn_summary(turns: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for i, t in enumerate(turns, start=1):
        mode = t.get("mode", "?")
        synth = t.get("synthesize")
        review = " review" if t.get("review_mode") else ""
        advocate = f" advocate={t['review_advocate']}" if t.get("review_advocate") else ""
        latency = t.get("latency_ms")
        lat = f" {latency}ms" if latency is not None else ""
        lines.append(f"  {i}. {mode}{review}{advocate} synthesize={synth}{lat}")
    return lines


def _meta_line(label: str, a: Any, b: Any) -> str | None:
    if a == b:
        return None
    return f"  {label}: {a!r} → {b!r}"


def compare_sessions(left: Path, right: Path) -> int:
    left = left.expanduser().resolve()
    right = right.expanduser().resolve()
    if not left.is_dir():
        print(f"Not a directory: {left}", file=sys.stderr)
        return 2
    if not right.is_dir():
        print(f"Not a directory: {right}", file=sys.stderr)
        return 2

    run_a = _load_run(left)
    run_b = _load_run(right)
    plan_a = _load_plan(left)
    plan_b = _load_plan(right)

    print(f"A: {left.name}")
    print(f"B: {right.name}")
    print()

    print("## run.json")
    for key in ("run_schema_version", "plan_format_version"):
        va = run_a.get(key)
        vb = run_b.get(key)
        if va != vb:
            print(f"  WARNING: {key} mismatch ({va!r} vs {vb!r}) — compare run metadata with caution")
    for key in (
        "workflow_id",
        "message_count",
        "agent_parallel_rounds",
        "status",
    ):
        line = _meta_line(key, run_a.get(key), run_b.get(key))
        if line:
            print(line)
    lpu_a = run_a.get("last_plan_update") or {}
    lpu_b = run_b.get("last_plan_update") or {}
    for key in ("trigger", "ts", "agents", "request_id"):
        line = _meta_line(f"last_plan_update.{key}", lpu_a.get(key), lpu_b.get(key))
        if line:
            print(line)

    turns_a = run_a.get("turns") or []
    turns_b = run_b.get("turns") or []
    if len(turns_a) != len(turns_b):
        print(f"  turns count: {len(turns_a)} → {len(turns_b)}")
    print("  turns A:")
    for ln in _turn_summary(turns_a) or ["  (none)"]:
        print(ln)
    print("  turns B:")
    for ln in _turn_summary(turns_b) or ["  (none)"]:
        print(ln)
    print()

    print("## plan.md refs")
    ref_a = validate_plan_refs(left)
    ref_b = validate_plan_refs(right)
    print(f"  A: {ref_a.summary()}")
    print(f"  B: {ref_b.summary()}")
    print()

    print("## plan.md diff")
    if plan_a == plan_b:
        print("  (identical)")
    elif not plan_a or not plan_b:
        print(f"  A chars: {len(plan_a)}, B chars: {len(plan_b)}")
    else:
        diff = difflib.unified_diff(
            plan_a.splitlines(keepends=True),
            plan_b.splitlines(keepends=True),
            fromfile=f"{left.name}/plan.md",
            tofile=f"{right.name}/plan.md",
            lineterm="",
        )
        for line in diff:
            print(line, end="" if line.endswith("\n") else f"{line}\n")

    return 0


def main() -> int:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <session-a> <session-b>", file=sys.stderr)
        return 2
    return compare_sessions(Path(sys.argv[1]), Path(sys.argv[2]))


if __name__ == "__main__":
    raise SystemExit(main())
