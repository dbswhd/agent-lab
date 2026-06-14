#!/usr/bin/env python3
"""Audit cross-lane orchestration imports against H0 contract.

Usage:
    python scripts/audit_runtime_imports.py
    python scripts/audit_runtime_imports.py --strict
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _source_path(source_module: str) -> Path:
    rel = source_module.replace(".", "/") + ".py"
    return SRC / rel


def _module_imports(path: Path) -> set[tuple[str, str]]:
    """Return (target_module, symbol) for ``from agent_lab.X import Y`` in *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if not node.module or not node.module.startswith("agent_lab."):
            continue
        for alias in node.names:
            out.add((node.module, alias.name))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if contract edges are missing from source (import moved/renamed).",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(SRC))
    from agent_lab.runtime.import_graph import CROSS_LANE_IMPORTS, FORBIDDEN_CROSS_IMPORTS

    contract: set[tuple[str, str, str]] = set()
    scan_modules: set[str] = set()
    orchestration_targets = {
        "agent_lab.room",
        "agent_lab.mission_loop",
        "agent_lab.plan_execute",
    }
    for row in CROSS_LANE_IMPORTS:
        contract.add((row.source_module, row.target_module, row.symbol))
        scan_modules.add(row.source_module)

    found: set[tuple[str, str, str]] = set()
    for source_module in sorted(scan_modules):
        path = _source_path(source_module)
        if not path.is_file():
            print(f"WARN: missing source module file {path}")
            continue
        for target_module, symbol in _module_imports(path):
            found.add((source_module, target_module, symbol))

    missing = contract - found
    extra = {
        edge for edge in found if edge[0] in scan_modules and edge[1] in orchestration_targets and edge not in contract
    }

    print(f"Contract edges: {len(contract)}")
    print(f"Found in scan modules: {len(found & contract)} matched")

    if missing:
        print("\nMissing contract edges (update import_graph.py or restore import):")
        for src, tgt, sym in sorted(missing):
            print(f"  {src} → {tgt}.{sym}")

    if extra:
        print("\nUndocumented cross-lane imports (add to CROSS_LANE_IMPORTS):")
        for src, tgt, sym in sorted(extra):
            print(f"  {src} → {tgt}.{sym}")

    forbidden_modules = {
        "agent_lab.plan_execute",
        "agent_lab.room",
        "agent_lab.mission_loop",
        "agent_lab.context_bundle",
        "agent_lab.room_tasks",
    }
    forbidden_hits: list[tuple[str, str, str]] = []
    for source_module in sorted(forbidden_modules):
        path = _source_path(source_module)
        if not path.is_file():
            continue
        for tgt, sym in _module_imports(path):
            if (source_module, tgt) in FORBIDDEN_CROSS_IMPORTS:
                forbidden_hits.append((source_module, tgt, sym))

    if forbidden_hits:
        print("\nForbidden cross-lane imports:")
        for src, tgt, sym in sorted(forbidden_hits):
            print(f"  {src} → {tgt}.{sym}")

    if args.strict and missing:
        return 1
    if extra:
        return 1
    if forbidden_hits:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
