#!/usr/bin/env python3
"""Orchestration layer import-cycle guard (F12 Stage 2).

Counts module-level cross-layer edges and 2-cycles among orchestration packages.
Ratchets against tests/fixtures/layer-cycles-baseline.json.

Usage:
    python scripts/layer_cycle_check.py
    python scripts/layer_cycle_check.py --check
    python scripts/layer_cycle_check.py --json
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "agent_lab"
BASELINE_PATH = ROOT / "tests" / "fixtures" / "layer-cycles-baseline.json"

ORCHESTRATION_PACKAGES = frozenset(
    {
        "core",
        "runtime",
        "room",
        "plan",
        "mission",
        "run",
        "session",
        "inbox",
        "context",
    }
)


@dataclass(frozen=True, slots=True)
class LayerCycleMetrics:
    version: int
    module_level_edges: int
    two_cycles: list[list[str]]
    edges: list[list[str]]


def _package_for_path(path: Path) -> str:
    rel = path.relative_to(SRC)
    return rel.parts[0] if rel.parts else "root"


def _target_package(module: str) -> str | None:
    if not module.startswith("agent_lab."):
        return None
    parts = module.split(".")
    if len(parts) < 2:
        return None
    pkg = parts[1]
    return pkg if pkg in ORCHESTRATION_PACKAGES else None


def _module_level_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    targets: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("agent_lab."):
                targets.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("agent_lab."):
                    targets.append(alias.name)
    return targets


def collect_metrics() -> LayerCycleMetrics:
    edges: set[tuple[str, str]] = set()
    for path in sorted(SRC.rglob("*.py")):
        src_pkg = _package_for_path(path)
        if src_pkg not in ORCHESTRATION_PACKAGES:
            continue
        for module in _module_level_imports(path):
            tgt_pkg = _target_package(module)
            if tgt_pkg is None or tgt_pkg == src_pkg:
                continue
            edges.add((src_pkg, tgt_pkg))

    graph: dict[str, set[str]] = defaultdict(set)
    for src, tgt in edges:
        graph[src].add(tgt)

    two_cycles: list[list[str]] = []
    for a, tgts in graph.items():
        for b in tgts:
            if a in graph.get(b, set()):
                cycle = sorted([a, b])
                if [cycle[0], cycle[1]] not in two_cycles and [cycle[1], cycle[0]] not in two_cycles:
                    two_cycles.append([cycle[0], cycle[1]])

    two_cycles.sort()
    edge_rows = [[a, b] for a, b in sorted(edges)]
    return LayerCycleMetrics(
        version=1,
        module_level_edges=len(edges),
        two_cycles=two_cycles,
        edges=edge_rows,
    )


def _load_baseline() -> dict:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _check_against_baseline(metrics: LayerCycleMetrics) -> list[str]:
    baseline = _load_baseline()
    failures: list[str] = []
    if metrics.module_level_edges > int(baseline["module_level_edges"]):
        failures.append(f"module_level_edges: {metrics.module_level_edges} > baseline {baseline['module_level_edges']}")
    baseline_cycles = {tuple(row) for row in baseline.get("two_cycles", [])}
    actual_cycles = {tuple(row) for row in metrics.two_cycles}
    new_cycles = actual_cycles - baseline_cycles
    if new_cycles:
        failures.append(f"new 2-cycles: {sorted(new_cycles)}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    metrics = collect_metrics()
    if args.json:
        print(json.dumps(asdict(metrics), indent=2))
        return 0

    if not args.check:
        print(f"module-level orchestration edges: {metrics.module_level_edges}")
        print(f"2-cycles: {len(metrics.two_cycles)}")
        for row in metrics.two_cycles:
            print(f"  {' <-> '.join(row)}")
        return 0

    failures = _check_against_baseline(metrics)
    if failures:
        for line in failures:
            print(f"layer cycle check FAILED: {line}")
        return 1
    print(f"layer cycle check OK — edges={metrics.module_level_edges}, 2-cycles={len(metrics.two_cycles)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
