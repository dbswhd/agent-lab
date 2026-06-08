from __future__ import annotations

from pathlib import Path

from agent_lab.context_bundle import build_context_bundle
from agent_lab.repo_tree_context import (
    _collect_per_dir_agents_files,
    build_per_dir_agents_block,
    build_repo_tree_block,
)


def _run_with_workspace(root: Path) -> dict:
    return {
        "workspace_binding": {"path": str(root)},
        "context_layers": {"repo_tree": True, "mission_wisdom": True},
    }


def test_build_repo_tree_block_lists_entries(tmp_path: Path) -> None:
    ws = tmp_path / "repo"
    ws.mkdir()
    (ws / "src").mkdir()
    (ws / "README.md").write_text("hi", encoding="utf-8")
    block = build_repo_tree_block(_run_with_workspace(ws))
    assert "[Repo tree]" in block
    assert "src/" in block
    assert "README.md" in block


def test_repo_tree_respects_layer_toggle(tmp_path: Path) -> None:
    ws = tmp_path / "repo"
    ws.mkdir()
    run = _run_with_workspace(ws)
    run["context_layers"]["repo_tree"] = False
    assert build_repo_tree_block(run) == ""


def test_per_dir_agents_collects_ancestor_chain(tmp_path: Path) -> None:
    ws = tmp_path / "repo"
    root_agents = ws / "AGENTS.md"
    src = ws / "src" / "auth"
    src.mkdir(parents=True)
    root_agents.write_text("root rules", encoding="utf-8")
    (src / "AGENTS.md").write_text("auth rules", encoding="utf-8")
    plan = "1. Fix\n   - 어디서: `src/auth/handler.py`\n"
    files = _collect_per_dir_agents_files(ws, plan)
    rels = {str(p.relative_to(ws)) for p in files}
    assert "AGENTS.md" in rels
    assert "src/auth/AGENTS.md" in rels


def test_per_dir_agents_from_structured_plan_actions(tmp_path: Path) -> None:
    ws = tmp_path / "repo"
    web = ws / "web" / "src"
    web.mkdir(parents=True)
    (web / "AGENTS.md").write_text("React components only.", encoding="utf-8")
    plan = (
        "## 지금 실행\n"
        "1. Fix button\n"
        "   - 무엇을: restyle\n"
        "   - 어디서: `web/src/Button.tsx`\n"
        "   - 검증: `make test-web`\n"
    )
    files = _collect_per_dir_agents_files(ws, plan)
    rels = {str(p.relative_to(ws)) for p in files}
    assert "web/src/AGENTS.md" in rels


def test_build_per_dir_agents_block_from_plan(tmp_path: Path) -> None:
    ws = tmp_path / "repo"
    src = ws / "src" / "auth"
    src.mkdir(parents=True)
    (src / "AGENTS.md").write_text("Use JWT helpers only.", encoding="utf-8")
    plan = "1. Fix auth\n   - 어디서: `src/auth/handler.py`\n"
    block = build_per_dir_agents_block(_run_with_workspace(ws), plan)
    assert "Per-dir AGENTS.md" in block
    assert "JWT" in block


def test_context_bundle_includes_repo_tree_when_enabled(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "app").mkdir()
    run = _run_with_workspace(ws)
    bundle = build_context_bundle(
        "topic",
        [],
        "claude",
        plan_md="touch `app/main.py`",
        run_meta=run,
    )
    assert "[Repo tree]" in bundle.constraints
    assert "Per-dir" in bundle.constraints or "app" in bundle.constraints
