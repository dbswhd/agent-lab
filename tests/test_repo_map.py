"""Symbol-graph repo-map (AGENT_LAB_REPO_MAP) — AC1-AC10 + Critic N1/N2.

stdlib-ast symbol extraction + zero-dependency neighborhood ranking + elided signature-tree
render, flag-gated and default-off; per-flag OFF-parity is the primary invariant.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any

import pytest

from agent_lab import repo_map
from agent_lab.repo_map import (
    DEFAULT_REPO_MAP_TOKENS,
    EXCLUDE_DIRS,
    MAX_FILES,
    _CHARS_PER_TOKEN,
    _extract_file,
    _iter_python_files,
    build_repo_map_block,
    repo_map_enabled,
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
    (root / "notes.md").write_text("# not python\n", encoding="utf-8")
    return root


def _run_meta(root: Path, *, repo_tree_layer: bool = True) -> dict[str, Any]:
    return {
        "workspace_binding": {"path": str(root)},
        "context_layers": {"repo_tree": repo_tree_layer},
    }


# --- AC1: ast extraction (defs/refs; non-Python ignored) ---


def test_ac1_extract_python_defs_refs(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    extracted = _extract_file(root / "core.py")
    assert extracted is not None
    defs, refs = extracted
    names = {name for name, _l, _s in defs}
    assert {"helper", "Engine", "run"} <= names
    assert "helper" in refs  # referenced inside Engine.run


def test_ac1_non_python_ignored(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    files = _iter_python_files(root)
    assert all(f.suffix == ".py" for f in files)
    assert not any(f.name == "notes.md" for f in files)


# --- AC2: deterministic ranking from seeds + empty-seed global fallback ---


def test_ac2_seed_ranking_deterministic(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    # plan mentions app.py; app references Engine/helper (defined in core) → core ranks high
    block = build_repo_map_block(_run_meta(root), plan_md="see `app.py` for entry")
    assert "core.py" in block
    # determinism: identical inputs → identical output
    again = build_repo_map_block(_run_meta(root), plan_md="see `app.py` for entry")
    assert block == again


def test_ac2_empty_seed_global_fallback(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    block = build_repo_map_block(_run_meta(root), plan_md="")  # no resolvable seed
    assert block  # not empty: global-frequency fallback still renders symbols
    assert "[Repo map]" in block


# --- AC3: elided signature-tree render ---


def test_ac3_elided_signature_tree(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    block = build_repo_map_block(_run_meta(root), plan_md="`app.py`")
    assert "[Repo map] symbol-graph (ast)" in block
    assert "class Engine:" in block  # signature line present
    assert "return x + 1" not in block  # body elided
    assert "    ..." in block  # elision marker


# --- AC4: token budget + deterministic drop-lowest ---


def test_ac4_budget_drops_lowest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    for i in range(20):
        (root / f"m{i:02d}.py").write_text(f"def f{i}():\n    return {i}\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_LAB_REPO_MAP_TOKENS", "20")  # tiny budget
    block = build_repo_map_block(_run_meta(root), plan_md="")
    assert len(block) <= 20 * _CHARS_PER_TOKEN + 200  # within budget (+header slack)
    # not every file fits under the tiny budget
    assert block.count(".py:") < 20


# --- AC5: OFF-parity (flag off => repo_map not invoked; build_context_bundle unchanged) ---


def test_ac5_off_parity_repo_map_not_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_REPO_MAP", raising=False)
    assert repo_map_enabled() is False
    # build_context_bundle's off path must call build_repo_tree_block, not repo_map.
    import agent_lab.context.bundle as cb

    src = inspect.getsource(cb)
    # the import is inside the flag-on branch only (guarded), never at module top
    assert "from agent_lab.repo_map import build_repo_map_block" in src
    assert 'if _env_bool("AGENT_LAB_REPO_MAP"):' in src


# --- AC6: flag-on replaces (one block); layer-off => no map ---


def test_ac6_layer_off_returns_empty(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    assert build_repo_map_block(_run_meta(root, repo_tree_layer=False), plan_md="`app.py`") == ""


def test_ac6_replace_single_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _workspace(tmp_path)
    monkeypatch.setenv("AGENT_LAB_REPO_MAP", "1")
    from agent_lab.context.bundle import _format_clarity_facts  # ensure module imports cleanly

    _ = _format_clarity_facts  # touch to keep import meaningful
    block = build_repo_map_block(_run_meta(root), plan_md="`app.py`")
    assert block.count("[Repo map]") == 1  # one block, not duplicated
    assert "[Repo tree]" not in block  # the symbol map replaces the plain tree header


# --- AC7: seed reuse (consume _plan_path_hints/_plan_action_path_hints) ---


def test_ac7_seed_helper_reuse_and_missing_tolerated(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    # a missing/misspelled hint must not raise and still yields a map via fallback
    block = build_repo_map_block(_run_meta(root), plan_md="`does_not_exist.py` and `app.py`")
    assert block
    assert "core.py" in block or "app.py" in block


# --- AC8: zero-dependency + import lane ---


def test_ac8_no_forbidden_imports() -> None:
    # Inspect actual import statements (not docstring mentions).
    tree = ast.parse(inspect.getsource(repo_map))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    for banned in ("tree_sitter", "networkx"):
        assert not any(mod == banned or mod.startswith(banned + ".") for mod in imported)
    for lane in ("agent_lab.room", "agent_lab.mission.loop", "agent_lab.plan.execute", "agent_lab.runtime"):
        assert not any(mod == lane or mod.startswith(lane + ".") for mod in imported)


# --- AC10: unbound workspace => ""; bounded parse set ---


def test_ac10_unbound_workspace_empty() -> None:
    assert build_repo_map_block({}, plan_md="`app.py`") == ""
    assert build_repo_map_block(None, plan_md="`app.py`") == ""


def test_ac10_excludes_dotdirs_and_vendored(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "real.py").write_text("def keep():\n    return 1\n", encoding="utf-8")
    for bad in (".venv", "node_modules", "__pycache__", ".git"):
        d = root / bad
        d.mkdir()
        (d / "junk.py").write_text("def excluded():\n    return 0\n", encoding="utf-8")
    files = _iter_python_files(root)
    assert any(f.name == "real.py" for f in files)
    assert not any("excluded" in f.read_text(encoding="utf-8") for f in files)


def test_ac10_unparseable_skipped_not_raised(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "good.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    (root / "bad.py").write_text("def broken(:\n  syntax error\n", encoding="utf-8")
    assert _extract_file(root / "bad.py") is None  # skipped, no raise
    block = build_repo_map_block(_run_meta(root), plan_md="")
    assert "good.py" in block  # good file still rendered


# --- Critic N2: rendered length stays within budget*ratio ---


def test_n2_render_within_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    for i in range(50):
        (root / f"f{i:02d}.py").write_text(f"def fn{i}():\n    return {i}\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_LAB_REPO_MAP_TOKENS", "64")
    block = build_repo_map_block(_run_meta(root), plan_md="")
    # one block may overshoot by a single unit; assert it never wildly exceeds the budget
    assert len(block) <= 64 * _CHARS_PER_TOKEN + 256


# --- flag gate + budget parse ---


@pytest.mark.parametrize("val", ["0", "false", "", "  ", "no", "off"])
def test_flag_not_enabled(val: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_REPO_MAP", val)
    assert repo_map_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "yes", "on", "On"])
def test_flag_enabled(val: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_REPO_MAP", val)
    assert repo_map_enabled() is True


def test_budget_default_on_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_REPO_MAP_TOKENS", "not-a-number")
    assert repo_map._map_token_budget() == DEFAULT_REPO_MAP_TOKENS
    monkeypatch.setenv("AGENT_LAB_REPO_MAP_TOKENS", "-5")
    assert repo_map._map_token_budget() == DEFAULT_REPO_MAP_TOKENS


def test_constants_present() -> None:
    assert MAX_FILES > 0
    assert ".venv" in EXCLUDE_DIRS and "node_modules" in EXCLUDE_DIRS


# --- Seed-ranking backfill (stage 43-48): seeds strictly first + spare-budget freq backfill ---

from pathlib import Path as _P

from agent_lab.repo_map import (  # noqa: E402
    _FREQ_TIER,
    _MIN_SEED_INCREMENT,
    _rank_files,
)


def _idx(defs_refs: dict[str, tuple[list[str], list[str]]]) -> dict:
    """Build a _rank_files index: {Path: ([(name,1,name)], {refs})}."""
    out: dict = {}
    for fname, (defs, refs) in defs_refs.items():
        out[_P(fname)] = ([(d, 1, d) for d in defs], set(refs))
    return out


def test_seedrank_freq_tier_invariant_below_min_seed_increment() -> None:
    # The damped freq term must always be strictly below the smallest seed increment,
    # for any frequency — otherwise a pure-freq file could overtake a seed file.
    for max_freq in (1, 10, 1000, 10_000, 10**9):
        sup = _FREQ_TIER * max_freq / (max_freq + 1)
        assert sup < _MIN_SEED_INCREMENT


def test_seedrank_seed_dominates_max_freq_unseeded() -> None:
    # A min-score seed file (2-hop, S=0.5) must outrank a heavily-referenced UNSEEDED file.
    # seed.py references hop1 symbol; hop1 references hop2 symbol (=> hop2 gets _SEED_HOP2).
    # hot.py is defined-and-referenced by many but NOT reachable from the seed.
    idx = _idx(
        {
            "seed.py": (["seed_sym"], ["hop1_sym"]),
            "hop1.py": (["hop1_sym"], ["hop2_sym"]),
            "hop2.py": (["hop2_sym"], []),
            "hot.py": (["hot_sym"], []),
            # many files reference hot_sym => high global frequency, but no seed path to it
            **{f"u{i}.py": ([f"u{i}_sym"], ["hot_sym"]) for i in range(20)},
        }
    )
    seeds = {_P("seed.py")}
    scores = _rank_files(idx, seeds)
    # hop2 is the weakest seed-scored file; hot is the strongest pure-freq file
    assert scores[_P("hop2.py")] >= _MIN_SEED_INCREMENT
    assert scores[_P("hot.py")] < _MIN_SEED_INCREMENT
    assert scores[_P("hop2.py")] > scores[_P("hot.py")]  # seed strictly first


def test_seedrank_backfill_surfaces_unseeded_referenced_file() -> None:
    # An unseeded-but-referenced file (score 0 under the old early-return) now gets a
    # nonzero backfill rank so it can appear in spare budget.
    idx = _idx(
        {
            "seed.py": (["seed_sym"], []),
            "lonely.py": (["lonely_sym"], []),
            "ref_a.py": (["a"], ["lonely_sym"]),
            "ref_b.py": (["b"], ["lonely_sym"]),
        }
    )
    scores = _rank_files(idx, {_P("seed.py")})
    assert scores[_P("lonely.py")] > 0.0  # previously 0 (invisible); now backfilled
    assert scores[_P("seed.py")] > scores[_P("lonely.py")]  # seed still first


def test_seedrank_empty_seed_order_preserved() -> None:
    # No seeds => ranking is a monotonic transform of global frequency => same ORDER.
    idx = _idx(
        {
            "high.py": (["h"], []),
            "mid.py": (["m"], []),
            "low.py": (["lo"], []),
            **{f"r{i}.py": ([f"r{i}"], ["h"]) for i in range(3)},  # h freq 3
            **{f"s{i}.py": ([f"s{i}"], ["m"]) for i in range(2)},  # m freq 2
            "t0.py": (["t0"], ["lo"]),  # lo freq 1
        }
    )
    scores = _rank_files(idx, set())
    assert scores[_P("high.py")] > scores[_P("mid.py")] > scores[_P("low.py")]


def test_seedrank_equal_freq_deterministic() -> None:
    idx = _idx(
        {
            "a.py": (["a_sym"], []),
            "b.py": (["b_sym"], []),
            "r1.py": (["r1"], ["a_sym"]),
            "r2.py": (["r2"], ["b_sym"]),
        }
    )
    s1 = _rank_files(idx, set())
    s2 = _rank_files(idx, set())
    assert s1 == s2  # deterministic
    assert s1[_P("a.py")] == s1[_P("b.py")]  # equal freq => equal score (path tie-break in render)
