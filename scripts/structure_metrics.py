#!/usr/bin/env python3
"""Repository structure metrics — baseline for package flattening work.

Usage:
    python scripts/structure_metrics.py
    python scripts/structure_metrics.py --json
    python scripts/structure_metrics.py --check
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_LAB = ROOT / "src" / "agent_lab"
BASELINE_PATH = ROOT / "tests" / "fixtures" / "structure-metrics-baseline.json"
MAKEFILE = ROOT / "Makefile"
WEB_SRC = ROOT / "web" / "src"

# F9 hot-path LOC ratchet — caps match NORTH-STAR §3.1 (2026-07-04 measured).
HOT_PATH_PY_FILES: tuple[str, ...] = (
    "src/agent_lab/plan/execute.py",
    "src/agent_lab/plan/workflow.py",
    "src/agent_lab/room/turn_flow.py",
)

TRACK_PREFIXES = (
    "room_",
    "plan_",
    "session_",
    "kimi_",
    "agent_",
    "mission_",
    "wisdom_",
    "inbox_",
    "context_",
    "run_",
    "workspace_",
    "research_",
    "hook_",
    "quant_",
    "cursor_",
    "codex_",
    "claude_",
)


@dataclass(frozen=True, slots=True)
class StructureMetrics:
    version: int
    agent_lab_root_py_files: int
    agent_lab_subpackages: list[str]
    prefix_counts: dict[str, int]
    tracked_pycache_files: int
    makefile_lines: int
    makefile_targets: int
    large_tsx_files: list[dict[str, int | str]]
    hot_path_py_files: list[dict[str, int | str]]
    notes: dict[str, str]


def _git_tracked_pycache_count() -> int:
    proc = subprocess.run(
        ["git", "ls-files", "*__pycache__*", "*.pyc"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return -1
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    return len(lines)


def _makefile_targets() -> tuple[int, int]:
    text = MAKEFILE.read_text(encoding="utf-8")
    targets = re.findall(r"^[a-zA-Z0-9_.-]+:", text, flags=re.MULTILINE)
    return len(text.splitlines()), len(targets)


def _count_lines(path: Path) -> int:
    return sum(1 for _ in path.open(encoding="utf-8"))


def _hot_path_py_files() -> list[dict[str, int | str]]:
    rows: list[dict[str, int | str]] = []
    for rel in HOT_PATH_PY_FILES:
        path = ROOT / rel
        rows.append(
            {
                "path": rel,
                "lines": _count_lines(path) if path.is_file() else -1,
            }
        )
    return rows


def _large_tsx_files(*, min_lines: int = 500, limit: int = 10) -> list[dict[str, int | str]]:
    rows: list[tuple[int, Path]] = []
    if not WEB_SRC.is_dir():
        return []
    for path in WEB_SRC.rglob("*.tsx"):
        line_count = _count_lines(path)
        if line_count >= min_lines:
            rows.append((line_count, path))
    rows.sort(key=lambda item: item[0], reverse=True)
    return [{"path": str(path.relative_to(ROOT)), "lines": line_count} for line_count, path in rows[:limit]]


def collect_metrics() -> StructureMetrics:
    root_py = sorted(AGENT_LAB.glob("*.py"))
    prefix_counts = {prefix: 0 for prefix in TRACK_PREFIXES}
    for path in root_py:
        for prefix in TRACK_PREFIXES:
            if path.name.startswith(prefix):
                prefix_counts[prefix] += 1

    subpackages = sorted(
        child.name for child in AGENT_LAB.iterdir() if child.is_dir() and (child / "__init__.py").is_file()
    )
    makefile_lines, makefile_targets = _makefile_targets()

    return StructureMetrics(
        version=2,
        agent_lab_root_py_files=len(root_py),
        agent_lab_subpackages=subpackages,
        prefix_counts=prefix_counts,
        tracked_pycache_files=_git_tracked_pycache_count(),
        makefile_lines=makefile_lines,
        makefile_targets=makefile_targets,
        large_tsx_files=_large_tsx_files(),
        hot_path_py_files=_hot_path_py_files(),
        notes={
            "pycache": (
                "tracked_pycache_files counts git-tracked __pycache__/*.pyc only; "
                "local __pycache__ dirs are ignored by .gitignore and are not repo debt."
            ),
            "makefile_targets": "Counted as Makefile lines matching ^target:",
            "hot_path_py_files": (
                "F9 ratchet: execute.py / workflow.py / turn_flow.py LOC caps; "
                "--check fails on any drift from baseline (growth or shrink without update)."
            ),
            "f11_run_meta_dict_signatures": (
                "F11 ratchet: grep count of run_meta: dict[str, Any] in src/agent_lab; "
                "must not grow without baseline update (Stage 1 migration lowers over time)."
            ),
        },
    )


def _print_human(metrics: StructureMetrics) -> None:
    print("agent_lab structure metrics")
    print(f"  root .py modules: {metrics.agent_lab_root_py_files}")
    print(f"  subpackages: {', '.join(metrics.agent_lab_subpackages) or '(none)'}")
    print("  prefix counts (root only):")
    for prefix, count in metrics.prefix_counts.items():
        if count:
            print(f"    {prefix:<12} {count}")
    print(f"  tracked __pycache__/*.pyc: {metrics.tracked_pycache_files}")
    print(f"  Makefile: {metrics.makefile_lines} lines, {metrics.makefile_targets} targets")
    print("  large TSX (>=500 lines):")
    for row in metrics.large_tsx_files:
        print(f"    {row['lines']:>5}  {row['path']}")
    print("  F9 hot-path Python:")
    for row in metrics.hot_path_py_files:
        print(f"    {row['lines']:>5}  {row['path']}")


def _load_baseline() -> dict:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _check_against_baseline(metrics: StructureMetrics) -> list[str]:
    baseline = _load_baseline()
    failures: list[str] = []

    for key in (
        "agent_lab_root_py_files",
        "tracked_pycache_files",
        "makefile_lines",
        "makefile_targets",
    ):
        expected = baseline[key]
        actual = getattr(metrics, key)
        if actual != expected:
            failures.append(f"{key}: expected {expected}, got {actual}")

    for prefix, expected in baseline["prefix_counts"].items():
        actual = metrics.prefix_counts.get(prefix, 0)
        if actual != expected:
            failures.append(f"prefix_counts[{prefix!r}]: expected {expected}, got {actual}")

    baseline_tsx = {row["path"]: row["lines"] for row in baseline["large_tsx_files"]}
    actual_tsx = {row["path"]: row["lines"] for row in metrics.large_tsx_files}
    for path, expected_lines in baseline_tsx.items():
        if path not in actual_tsx:
            failures.append(f"large_tsx_files missing baseline path {path!r}")
        elif actual_tsx[path] != expected_lines:
            failures.append(f"large_tsx_files[{path!r}]: expected {expected_lines}, got {actual_tsx[path]}")

    baseline_hot = {row["path"]: row["lines"] for row in baseline.get("hot_path_py_files", [])}
    actual_hot = {row["path"]: row["lines"] for row in metrics.hot_path_py_files}
    for path, expected_lines in baseline_hot.items():
        if path not in actual_hot:
            failures.append(f"hot_path_py_files missing baseline path {path!r}")
        elif actual_hot[path] != expected_lines:
            failures.append(f"hot_path_py_files[{path!r}]: expected {expected_lines}, got {actual_hot[path]}")
    for path in HOT_PATH_PY_FILES:
        if path not in baseline_hot:
            failures.append(f"hot_path_py_files missing F9 path {path!r}")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON on stdout.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if metrics drift from tests/fixtures/structure-metrics-baseline.json.",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Rewrite tests/fixtures/structure-metrics-baseline.json (maintainer only).",
    )
    args = parser.parse_args()

    metrics = collect_metrics()

    if args.write_baseline:
        payload = asdict(metrics)
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {BASELINE_PATH.relative_to(ROOT)}", file=sys.stderr)
        return 0

    if args.json:
        print(json.dumps(asdict(metrics), indent=2, ensure_ascii=False))
    else:
        _print_human(metrics)

    if args.check:
        if not BASELINE_PATH.is_file():
            print(f"Missing baseline: {BASELINE_PATH}", file=sys.stderr)
            return 1
        failures = _check_against_baseline(metrics)
        if failures:
            print("\nBaseline drift:", file=sys.stderr)
            for failure in failures:
                print(f"  - {failure}", file=sys.stderr)
            return 1
        if not args.json:
            print("\nBaseline check: OK", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
