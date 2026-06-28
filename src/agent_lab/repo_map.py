"""Symbol-graph repo-map for agent context (AGENT_LAB_REPO_MAP).

Optional, additive, default-off. When ``AGENT_LAB_REPO_MAP`` is enabled,
:func:`build_repo_map_block` replaces ``repo_tree_context.build_repo_tree_block`` in the agent
context bundle with an Aider-style symbol map: stdlib ``ast`` extracts Python symbol
definitions/references, a def/ref graph is ranked by a zero-dependency 1-2 hop neighborhood
weighting seeded from plan/turn path hints, and the top-ranked symbols render as a file-keyed
elided signature tree within a token budget.

Design invariants:
- Pure stdlib (ast/os/pathlib); no tree-sitter, no networkx, no full PageRank power-iteration.
- Python-only extraction; unparseable files are skipped, never raised.
- Parse set is bounded: dotdirs / vendored dirs excluded, and at most ``MAX_FILES`` files.
- No cross-lane imports beyond reusing ``repo_tree_context`` seed/root helpers + the context
  layer toggle; no on-disk map (computed per turn).
- Returns "" when the workspace is unbound or the repo_tree context layer is off, so flag-off
  (and layer-off) behavior matches the plain repo tree.
"""

from __future__ import annotations

import ast
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from agent_lab.context.layers import repo_tree_layer_enabled
from agent_lab.repo_tree_context import (
    _plan_action_path_hints,
    _plan_path_hints,
    _workspace_root,
)

_TRUE = frozenset({"1", "true", "yes", "on"})

# Directories never parsed for symbols (dotdirs handled separately by name.startswith(".")).
EXCLUDE_DIRS = frozenset(
    {
        ".git",
        ".venv",
        ".gjc",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "node_modules",
        "dist",
        "build",
        "__pycache__",
        "sessions",
        ".tox",
        ".eggs",
        "venv",
        "site-packages",
        # Rust/Tauri/Maven/Gradle compiled output — can be gigabytes of copied source.
        "target",
        # Bundled Python runtimes shipped inside Tauri/Electron app bundles.
        "bundled-runtime",
    }
)
# Hard cap on files parsed per build (cost bound). When exceeded, parsing is restricted to
# seed files + their import-neighbor directories.
MAX_FILES = 2000
DEFAULT_REPO_MAP_TOKENS = 1024
# Conservative chars/token estimate for budgeting the rendered block.
_CHARS_PER_TOKEN = 4
_ELISION = "    ..."
# Seed-relevance increments (named so the freq tiering bound below is derived, not magic).
_SEED_SELF = 3.0  # a seed file itself
_SEED_HOP1 = 2.0  # file referenced by a seed (1 hop)
_SEED_HOP2 = 0.5  # file referenced by a 1-hop file (2 hop) — smallest nonzero seed score
_MIN_SEED_INCREMENT = _SEED_HOP2
# Global-frequency backfill term ceiling: strictly below the smallest seed increment so any
# seed-scored file always outranks any pure-frequency file. Derived from _MIN_SEED_INCREMENT.
_FREQ_TIER = _MIN_SEED_INCREMENT * 0.98


def repo_map_enabled() -> bool:
    """AGENT_LAB_REPO_MAP (default OFF): symbol-graph repo-map in agent context."""
    return (os.getenv("AGENT_LAB_REPO_MAP") or "").strip().lower() in _TRUE


def _map_token_budget() -> int:
    raw = (os.getenv("AGENT_LAB_REPO_MAP_TOKENS") or "").strip()
    if not raw:
        return DEFAULT_REPO_MAP_TOKENS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_REPO_MAP_TOKENS
    return value if value > 0 else DEFAULT_REPO_MAP_TOKENS


def _iter_python_files(root: Path) -> list[Path]:
    """Workspace Python files, excluding dotdirs and vendored/build dirs, sorted, capped."""
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded + dotted subdirectories in place (deterministic order).
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in EXCLUDE_DIRS)
        for name in sorted(filenames):
            if name.endswith(".py"):
                files.append(Path(dirpath) / name)
    files.sort()
    return files


class _SymbolVisitor(ast.NodeVisitor):
    """Collect top-level + nested def/class signatures and referenced names for one module."""

    def __init__(self, source_lines: list[str]) -> None:
        self.source_lines = source_lines
        self.defs: list[tuple[str, int, str]] = []  # (name, lineno, signature line)
        self.refs: set[str] = set()

    def _signature_line(self, lineno: int) -> str:
        idx = lineno - 1
        if 0 <= idx < len(self.source_lines):
            return self.source_lines[idx].rstrip()
        return ""

    def _record_def(self, node: ast.AST, name: str) -> None:
        lineno = getattr(node, "lineno", 0)
        self.defs.append((name, lineno, self._signature_line(lineno)))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record_def(node, node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record_def(node, node.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._record_def(node, node.name)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        self.refs.add(node.id)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.refs.add(node.attr)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.refs.add(alias.name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.refs.add(alias.name.split(".")[0])
        self.generic_visit(node)


def _extract_file(path: Path) -> tuple[list[tuple[str, int, str]], set[str]] | None:
    """Parse one Python file → (defs, refs). Returns None for unreadable/unparseable files."""
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    visitor = _SymbolVisitor(source.splitlines())
    visitor.visit(tree)
    return visitor.defs, visitor.refs


def _resolve_seed_files(root: Path, plan_md: str) -> set[Path]:
    """Seed files = plan/turn path hints resolved against the workspace root (misses tolerated)."""
    seeds: set[Path] = set()
    for hint in _plan_path_hints(plan_md) + _plan_action_path_hints(plan_md):
        candidate = (root / hint).resolve()
        if candidate.is_file() and candidate.suffix == ".py":
            seeds.add(candidate)
    return seeds


def _build_index(files: list[Path]) -> dict[Path, tuple[list[tuple[str, int, str]], set[str]]]:
    index: dict[Path, tuple[list[tuple[str, int, str]], set[str]]] = {}
    for path in files:
        extracted = _extract_file(path)
        if extracted is not None:
            index[path] = extracted
    return index


def _rank_files(
    index: dict[Path, tuple[list[tuple[str, int, str]], set[str]]],
    seeds: set[Path],
) -> dict[Path, float]:
    """Composite seed + damped global-frequency weighting (zero-dependency, 1-2 hop).

    A file's score is its seed-relevance (seed self / 1-hop / 2-hop increments) PLUS a
    global-frequency term strictly bounded below the smallest seed increment, so any
    seed-scored file always outranks any pure-frequency file while relevant-but-unseeded
    files still backfill spare render budget. With no seeds, the seed term is 0 for all
    and ranking degrades to (a monotonic transform of) pure global frequency — same order.
    """
    # symbol name -> files that define it
    def_files: dict[str, set[Path]] = defaultdict(set)
    for path, (defs, _refs) in index.items():
        for name, _lineno, _sig in defs:
            def_files[name].add(path)

    scores: dict[Path, float] = {path: 0.0 for path in index}

    # Seed term: 1-2 hop neighborhood weighting.
    if seeds:
        first_hop: set[Path] = set(seeds)
        for seed in seeds:
            if seed in scores:
                scores[seed] += _SEED_SELF
            _refs = index.get(seed, ([], set()))[1]
            for name in _refs:
                for target in def_files.get(name, ()):  # noqa: SIM118
                    scores[target] += _SEED_HOP1
                    first_hop.add(target)
        for node in first_hop:
            for name in index.get(node, ([], set()))[1]:
                for target in def_files.get(name, ()):  # noqa: SIM118
                    scores[target] += _SEED_HOP2

    # Global-frequency backfill term, strictly damped below _MIN_SEED_INCREMENT so it can
    # never lift a pure-frequency file above any seed-scored file. Always applied, so
    # relevant-but-unseeded files surface in spare budget instead of being invisible.
    ref_freq: dict[str, int] = defaultdict(int)
    for _path, (_defs, refs) in index.items():
        for name in refs:
            ref_freq[name] += 1
    file_freq: dict[Path, int] = {
        path: sum(ref_freq.get(name, 0) for name, _l, _s in defs) for path, (defs, _refs) in index.items()
    }
    max_freq = max(file_freq.values(), default=0)
    if max_freq > 0:
        for path, freq in file_freq.items():
            scores[path] += _FREQ_TIER * freq / (max_freq + 1)
    return scores


def _render(
    root: Path,
    index: dict[Path, tuple[list[tuple[str, int, str]], set[str]]],
    scores: dict[Path, float],
    budget_chars: int,
) -> str:
    """Render top-ranked files as an elided signature tree within the char budget."""
    ranked = sorted(
        (p for p in index if index[p][0]),
        key=lambda p: (-scores.get(p, 0.0), str(p)),
    )
    lines: list[str] = ["[Repo map] symbol-graph (ast)"]
    used = len(lines[0]) + 1
    for path in ranked:
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path
        header = f"{rel}:"
        defs = sorted(index[path][0], key=lambda d: d[1])
        block = [header, *(f"    {sig or name}" for name, _lineno, sig in defs), _ELISION]
        block_text = "\n".join(block)
        if used + len(block_text) + 1 > budget_chars and len(lines) > 1:
            break
        lines.append(block_text)
        used += len(block_text) + 1
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def build_repo_map_block(run_meta: dict[str, Any] | None, plan_md: str = "") -> str:
    """Symbol-graph repo-map block — the flag-on replacement for build_repo_tree_block.

    Returns "" when the repo_tree context layer is off or the workspace is unbound, so enabling
    the map never smuggles context past a disabled layer and unbound sessions behave like the
    plain tree (empty).
    """
    if not repo_tree_layer_enabled(run_meta):
        return ""
    root = _workspace_root(run_meta)
    if root is None:
        return ""

    files = _iter_python_files(root)
    if not files:
        return ""
    seeds = _resolve_seed_files(root, plan_md)
    if len(files) > MAX_FILES:
        # Cost bound: restrict to seed files + their sibling directories when the tree is huge.
        seed_dirs = {s.parent for s in seeds}
        bounded = [f for f in files if f in seeds or f.parent in seed_dirs]
        files = bounded[:MAX_FILES] if bounded else files[:MAX_FILES]

    index = _build_index(files)
    if not index:
        return ""
    scores = _rank_files(index, seeds)
    budget_chars = _map_token_budget() * _CHARS_PER_TOKEN
    return _render(root, index, scores, budget_chars)
