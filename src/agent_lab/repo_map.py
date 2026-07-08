"""Symbol-graph repo-map for agent context (AGENT_LAB_REPO_MAP).

Optional, additive, default-off. Core AST/rank/render: :mod:`repo_map_core` (Track 2.0b seam).
"""

from __future__ import annotations

from agent_lab.env_flags import env_bool
from agent_lab.run.state import RunStateLike
import os
from pathlib import Path

from agent_lab.context.layers import repo_tree_layer_enabled
from agent_lab.repo_map_core import (
    DEFAULT_REPO_MAP_TOKENS,
    EXCLUDE_DIRS,  # noqa: F401 — public re-export
    MAX_FILES,  # noqa: F401 — public re-export
    _CHARS_PER_TOKEN,
    _FREQ_TIER,  # noqa: F401 — public re-export
    _MIN_SEED_INCREMENT,  # noqa: F401 — public re-export
    _SEED_HOP1,  # noqa: F401 — public re-export
    _SEED_HOP2,  # noqa: F401 — public re-export
    _SEED_SELF,  # noqa: F401 — public re-export
    build_repo_map_core,
    build_index,
    extract_file,
    iter_python_files,
    rank_files,
    render_repo_map,
)
from agent_lab.repo_tree_context import (
    _plan_action_path_hints,
    _plan_path_hints,
    _workspace_root,
)

# Test / bench backward-compat aliases
_iter_python_files = iter_python_files
_extract_file = extract_file
_build_index = build_index
_rank_files = rank_files
_render = render_repo_map


def repo_map_enabled() -> bool:
    return env_bool("AGENT_LAB_REPO_MAP")


def _map_token_budget() -> int:
    raw = (os.getenv("AGENT_LAB_REPO_MAP_TOKENS") or "").strip()
    if not raw:
        return DEFAULT_REPO_MAP_TOKENS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_REPO_MAP_TOKENS
    return value if value > 0 else DEFAULT_REPO_MAP_TOKENS


def _resolve_seed_files(root: Path, plan_md: str) -> set[Path]:
    seeds: set[Path] = set()
    for hint in _plan_path_hints(plan_md) + _plan_action_path_hints(plan_md):
        candidate = (root / hint).resolve()
        if candidate.is_file() and candidate.suffix == ".py":
            seeds.add(candidate)
    return seeds


def build_repo_map_block(run_meta: RunStateLike | None, plan_md: str = "") -> str:
    """Symbol-graph repo-map block — flag-on replacement for build_repo_tree_block."""
    if not repo_tree_layer_enabled(run_meta):
        return ""
    root = _workspace_root(run_meta)
    if root is None:
        return ""

    files = iter_python_files(root)
    if not files:
        return ""
    seeds = _resolve_seed_files(root, plan_md)
    budget_chars = _map_token_budget() * _CHARS_PER_TOKEN
    return build_repo_map_core(root, files, seeds, budget_chars)
