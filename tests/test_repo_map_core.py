"""Track 2.0b — repo_map_core seam tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.repo_map import build_repo_map_block
from agent_lab.repo_map_core import build_repo_map_core, iter_python_files


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
