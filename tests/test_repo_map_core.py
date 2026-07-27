"""Track 2.0b — repo_map_core seam tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.repo_map import build_repo_map_block
from agent_lab.repo_map_core import (
    bound_python_files,
    build_index,
    build_repo_map_core,
    iter_python_files,
    rank_files,
)


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "core.py").write_text(
        "def helper(x):\n    return x + 1\n\n\nclass Engine:\n    def run(self):\n        return helper(1)\n",
        encoding="utf-8",
    )
    (root / "app.py").write_text(
        "from core import Engine, helper\n\n\ndef main():\n    e = Engine()\n    return e.run() + helper(2)\n",
        encoding="utf-8",
    )
    return root


def _run_meta(root: Path) -> dict[str, Any]:
    return {
        "workspace_binding": {"path": str(root)},
        "context_layers": {"repo_tree": True},
    }


def test_build_repo_map_core_matches_wrapper(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    plan_md = "see `app.py` for entry"
    files = iter_python_files(root)
    seeds = {root / "app.py"}
    budget = 1024 * 4
    core_block = build_repo_map_core(root, files, seeds, budget)
    wrapper_block = build_repo_map_block(_run_meta(root), plan_md=plan_md)
    assert core_block == wrapper_block
    assert "core.py" in core_block


def test_build_repo_map_core_respects_budget(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    for i in range(8):
        (root / f"extra_{i}.py").write_text(f"def fn_{i}():\n    return {i}\n", encoding="utf-8")
    files = iter_python_files(root)
    seeds = {root / "app.py"}
    full = build_repo_map_core(root, files, seeds, budget_chars=80_000)
    trimmed = build_repo_map_core(root, files, seeds, budget_chars=220)
    assert full
    assert len(trimmed) < len(full)
    assert trimmed.count(".py:") < full.count(".py:")


def test_build_repo_map_core_empty_files() -> None:
    assert build_repo_map_core(Path("/tmp/unused"), [], set(), budget_chars=1024) == ""


def test_rank_files_name_collision_scores_unrelated_sibling_same_as_referenced(tmp_path: Path) -> None:
    """Known heuristic limit: ranking matches refs to defs by bare *name string*,
    not resolved imports. A same-directory sibling that happens to define a
    function with the same name as one the seed actually calls gets the exact
    same hop-1 score boost as the file the seed truly depends on — the ranker
    cannot tell them apart. This locks the limitation down as a documented
    contract so a future "fix" is a deliberate, tested decision."""
    root = tmp_path / "ws"
    root.mkdir()
    (root / "seed.py").write_text("def main():\n    return run()\n", encoding="utf-8")
    (root / "related.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    (root / "coincidental.py").write_text(
        "def run():\n    '''unrelated domain, same name by coincidence'''\n    return 999\n",
        encoding="utf-8",
    )
    files = iter_python_files(root)
    seeds = {root / "seed.py"}
    bounded = bound_python_files(root, files, seeds)
    index = build_index(bounded)
    scores = rank_files(index, seeds)
    related = scores[root / "related.py"]
    coincidental = scores[root / "coincidental.py"]
    assert related > 0
    assert coincidental == related  # <- the noise: indistinguishable from the real dependency


def test_rank_files_nested_def_ranked_alongside_top_level(tmp_path: Path) -> None:
    """Known heuristic limit: a private nested helper is recorded as a def at
    the same flat level as its enclosing public function — nesting depth is
    not tracked, so a frequently-referenced private helper can outrank a
    barely-referenced public API in the same file's listing."""
    root = tmp_path / "ws"
    root.mkdir()
    (root / "mod.py").write_text(
        "def public_api():\n"
        "    def _private_nested_helper():\n"
        "        return 1\n"
        "    return _private_nested_helper()\n",
        encoding="utf-8",
    )
    files = iter_python_files(root)
    block = build_repo_map_core(root, files, set(), budget_chars=4096)
    assert "def public_api():" in block
    assert "def _private_nested_helper():" in block
    # both defs render as siblings in the same file block — no indentation-based
    # hierarchy distinguishes "public API" from "implementation detail".
    assert block.index("def public_api():") < block.index("def _private_nested_helper():")


def test_bound_python_files_no_seeds_falls_back_to_global_frequency_ranking(tmp_path: Path) -> None:
    """With no seeds (e.g. session start, no plan.md yet), bound_python_files
    keeps the *entire* workspace in scope and rank_files falls back to pure
    cross-file reference-frequency — files with zero incoming references (even
    if semantically important) sort to the bottom, tied at score 0."""
    root = tmp_path / "ws"
    root.mkdir()
    (root / "a.py").write_text("def frequently_called():\n    return 1\n", encoding="utf-8")
    (root / "b.py").write_text(
        "from a import frequently_called\ndef x():\n    return frequently_called()\n", encoding="utf-8"
    )
    (root / "c.py").write_text(
        "from a import frequently_called\ndef y():\n    return frequently_called()\n", encoding="utf-8"
    )
    (root / "isolated.py").write_text("def isolated():\n    return 42\n", encoding="utf-8")
    files = iter_python_files(root)
    bounded = bound_python_files(root, files, set())
    assert set(bounded) == set(files)  # global fallback, not neighborhood-restricted
    index = build_index(bounded)
    scores = rank_files(index, set())
    assert scores[root / "a.py"] > 0
    assert scores[root / "isolated.py"] == 0.0
