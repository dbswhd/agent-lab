"""Symbol-graph repo-map core — pure root/files/seeds/budget (Track 2.0b seam).

Future PyO3 target: :func:`build_repo_map_core`. Layer flags, workspace binding, and
plan seed resolution stay in ``repo_map.py``.
"""

from __future__ import annotations

import ast
import os
from collections import defaultdict
from pathlib import Path

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
        "target",
        "bundled-runtime",
    }
)
MAX_FILES = 2000
DEFAULT_REPO_MAP_TOKENS = 1024
_CHARS_PER_TOKEN = 4
_ELISION = "    ..."
_SEED_SELF = 3.0
_SEED_HOP1 = 2.0
_SEED_HOP2 = 0.5
_MIN_SEED_INCREMENT = _SEED_HOP2
_FREQ_TIER = _MIN_SEED_INCREMENT * 0.98


def iter_python_files(root: Path) -> list[Path]:
    """Workspace Python files, excluding dotdirs and vendored/build dirs, sorted."""
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in EXCLUDE_DIRS)
        for name in sorted(filenames):
            if name.endswith(".py"):
                files.append(Path(dirpath) / name)
    files.sort()
    return files


def _seed_import_neighbors(files: list[Path], seeds: set[Path]) -> set[Path]:
    """In-tree files imported by the seeds — cross-directory hop-1.

    Resolves ``from a.b import c`` / ``import a.b`` to files by path suffix, so
    the seed neighborhood spans packages (incl. ``src/`` layout) without parsing
    the whole tree. Match is separator-anchored so ``io.py`` never matches
    ``audio.py``. Relative imports are left to the same-directory sibling rule.
    """
    suffixes: set[str] = set()
    for seed in seeds:
        try:
            tree = ast.parse(seed.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level or not node.module:
                    continue
                mods = [node.module, *(f"{node.module}.{a.name}" for a in node.names)]
            elif isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            else:
                continue
            for mod in mods:
                rel = mod.replace(".", "/")
                suffixes.add(f"/{rel}.py")
                suffixes.add(f"/{rel}/__init__.py")
    if not suffixes:
        return set()
    return {f for f in files if any(f.as_posix().endswith(suf) for suf in suffixes)}


def bound_python_files(root: Path, files: list[Path], seeds: set[Path], *, max_files: int = MAX_FILES) -> list[Path]:
    """Restrict the parse set to the seed neighborhood.

    With resolvable seeds, parse only the seeds, their import targets (cross-dir
    hop-1) and same-directory siblings — not the whole tree. This keeps repo-map
    build cost proportional to the relevant subgraph instead of repo size. With
    no seeds, keep the global set (the frequency fallback ranking needs it).
    Both paths cap at ``max_files``.
    """
    if not seeds:
        return files if len(files) <= max_files else files[:max_files]
    seed_dirs = {s.parent for s in seeds}
    neighbors = _seed_import_neighbors(files, seeds)
    bounded = [f for f in files if f in seeds or f.parent in seed_dirs or f in neighbors]
    if not bounded:
        bounded = files
    return bounded[:max_files]


class _SymbolVisitor(ast.NodeVisitor):
    def __init__(self, source_lines: list[str]) -> None:
        self.source_lines = source_lines
        self.defs: list[tuple[str, int, str]] = []
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


def extract_file(path: Path) -> tuple[list[tuple[str, int, str]], set[str]] | None:
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


def build_index(files: list[Path]) -> dict[Path, tuple[list[tuple[str, int, str]], set[str]]]:
    index: dict[Path, tuple[list[tuple[str, int, str]], set[str]]] = {}
    for path in files:
        extracted = extract_file(path)
        if extracted is not None:
            index[path] = extracted
    return index


def rank_files(
    index: dict[Path, tuple[list[tuple[str, int, str]], set[str]]],
    seeds: set[Path],
) -> dict[Path, float]:
    def_files: dict[str, set[Path]] = defaultdict(set)
    for path, (defs, _refs) in index.items():
        for name, _lineno, _sig in defs:
            def_files[name].add(path)

    scores: dict[Path, float] = {path: 0.0 for path in index}

    if seeds:
        first_hop: set[Path] = set(seeds)
        for seed in seeds:
            if seed in scores:
                scores[seed] += _SEED_SELF
            _refs = index.get(seed, ([], set()))[1]
            for name in _refs:
                for target in def_files.get(name, ()):
                    scores[target] += _SEED_HOP1
                    first_hop.add(target)
        for node in first_hop:
            for name in index.get(node, ([], set()))[1]:
                for target in def_files.get(name, ()):
                    scores[target] += _SEED_HOP2

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


def render_repo_map(
    root: Path,
    index: dict[Path, tuple[list[tuple[str, int, str]], set[str]]],
    scores: dict[Path, float],
    budget_chars: int,
) -> str:
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


def build_repo_map_core(
    root: Path,
    files: list[Path],
    seeds: set[Path],
    budget_chars: int,
) -> str:
    """Pure repo-map render — no run_meta, layers, or env."""
    if not files:
        return ""
    bounded = bound_python_files(root, files, seeds)
    index = build_index(bounded)
    if not index:
        return ""
    scores = rank_files(index, seeds)
    return render_repo_map(root, index, scores, budget_chars)
