#!/usr/bin/env python3
"""Analyze room_* module import graph for package refactor planning.

Usage:
    python scripts/room_import_graph.py
    python scripts/room_import_graph.py --json
    python scripts/room_import_graph.py --strict
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "agent_lab"

ROOM_PREFIX = "room_"
FACADE = "room"


@dataclass(frozen=True, slots=True)
class ImportEdge:
    source: str
    target: str
    symbols: tuple[str, ...]
    lazy: bool


def _module_name(path: Path) -> str:
    rel = path.relative_to(SRC)
    if rel.name == "__init__.py":
        return ".".join(rel.parts[:-1])
    return rel.with_suffix("").as_posix().replace("/", ".")


def _room_modules() -> dict[str, Path]:
    modules: dict[str, Path] = {}
    pkg_init = SRC / FACADE / "__init__.py"
    legacy_facade = SRC / f"{FACADE}.py"
    if pkg_init.is_file():
        modules[FACADE] = pkg_init
    elif legacy_facade.is_file():
        modules[FACADE] = legacy_facade
    for path in sorted(SRC.glob(f"{ROOM_PREFIX}*.py")):
        modules[path.stem] = path
    pkg_dir = SRC / FACADE
    if pkg_dir.is_dir():
        for path in sorted(pkg_dir.glob("*.py")):
            if path.name == "__init__.py":
                continue
            modules[f"{FACADE}.{path.stem}"] = path
    return modules


def _parse_imports(path: Path) -> tuple[list[tuple[str, tuple[str, ...]]], list[tuple[str, tuple[str, ...]]]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    eager: list[tuple[str, tuple[str, ...]]] = []
    lazy: list[tuple[str, tuple[str, ...]]] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self._lazy = False

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            prev = self._lazy
            self._lazy = True
            self.generic_visit(node)
            self._lazy = prev

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            prev = self._lazy
            self._lazy = True
            self.generic_visit(node)
            self._lazy = prev

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if not node.module or not node.module.startswith("agent_lab.room"):
                return
            target = node.module.removeprefix("agent_lab.")
            symbols = tuple(alias.name for alias in node.names)
            bucket = lazy if self._lazy else eager
            bucket.append((target, symbols))

    Visitor().visit(tree)
    return eager, lazy


def collect_graph() -> dict:
    modules = _room_modules()
    edges: list[ImportEdge] = []
    external_importers: dict[str, list[str]] = defaultdict(list)

    for source, path in modules.items():
        eager, lazy = _parse_imports(path)
        for target, symbols in eager:
            if target == source:
                continue
            edges.append(ImportEdge(source, target, symbols, lazy=False))
        for target, symbols in lazy:
            if target == source:
                continue
            edges.append(ImportEdge(source, target, symbols, lazy=True))

    room_module_names = set(modules)
    for path in SRC.rglob("*.py"):
        if path in modules.values():
            continue
        mod = _module_name(path)
        if mod.startswith("room"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if not node.module or not node.module.startswith("agent_lab.room"):
                continue
            target = node.module.removeprefix("agent_lab.")
            external_importers[target].append(mod)

    in_degree = Counter({name: 0 for name in room_module_names})
    out_degree = Counter({name: 0 for name in room_module_names})
    for edge in edges:
        if edge.source in room_module_names and edge.target in room_module_names:
            out_degree[edge.source] += 1
            in_degree[edge.target] += 1

    leaf_modules = sorted(name for name, degree in in_degree.items() if degree == 0 and name != FACADE)
    hub_modules = sorted(
        (name for name, degree in out_degree.items() if degree >= 5 and name != FACADE),
        key=lambda name: (-out_degree[name], name),
    )

    return {
        "room_module_count": len(modules) - (1 if FACADE in modules else 0),
        "facade_module": FACADE,
        "modules": sorted(modules),
        "internal_edges": [
            {
                "source": edge.source,
                "target": edge.target,
                "symbols": list(edge.symbols),
                "lazy": edge.lazy,
            }
            for edge in sorted(edges, key=lambda e: (e.source, e.target))
        ],
        "external_importers": {
            target: sorted(set(importers))
            for target, importers in sorted(external_importers.items())
        },
        "leaf_modules": leaf_modules,
        "hub_modules": [{"module": name, "out_degree": out_degree[name]} for name in hub_modules],
    }


def _print_human(payload: dict) -> None:
    print(f"room package import graph ({payload['room_module_count']} room_* modules + facade)")
    print("\nLeaf modules (no in-package imports):")
    for name in payload["leaf_modules"]:
        print(f"  - {name}")
    print("\nHub modules (>=5 outgoing in-package imports):")
    for row in payload["hub_modules"]:
        print(f"  - {row['module']} ({row['out_degree']} edges)")
    print("\nExternal importers (non-room modules importing room_*):")
    for target, importers in payload["external_importers"].items():
        print(f"  {target}: {len(importers)} modules")
        for importer in importers[:5]:
            print(f"    - {importer}")
        if len(importers) > 5:
            print(f"    ... +{len(importers) - 5} more")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any room_* module imports agent_lab.room (facade cycle risk).",
    )
    args = parser.parse_args()

    payload = collect_graph()

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        _print_human(payload)

    if args.strict:
        facade_cycles = [
            edge
            for edge in payload["internal_edges"]
            if edge["source"] != FACADE and edge["target"] == FACADE
        ]
        if facade_cycles:
            print("\nFacade import cycles detected:", file=sys.stderr)
            for edge in facade_cycles:
                print(f"  {edge['source']} → {edge['target']}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
