"""MD-P3: AGENTS.md + SHARED_CONTEXT.md workspace injection."""

from __future__ import annotations

from pathlib import Path

from agent_lab.project_memory import bootstrap_workspace_memory
from agent_lab.session_guidance import build_session_guidance_block


def test_workspace_md_injection_order(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    bootstrap_workspace_memory(ws, overwrite=True)
    block = build_session_guidance_block(
        {"workspace_binding": {"path": str(ws), "label": "ws"}}
    )
    assert block.index("SHARED_CONTEXT") < block.index("PROJECT.md")
    assert block.index("PROJECT.md") < block.index("AGENTS.md")
    assert "Codex" in block


def test_per_dir_agents_hierarchy_in_session_guidance(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    src = ws / "src" / "auth"
    src.mkdir(parents=True)
    (ws / "AGENTS.md").write_text("root-only", encoding="utf-8")
    (src / "AGENTS.md").write_text("auth-specific rules", encoding="utf-8")
    plan = (
        "## 지금 실행\n"
        "1. Fix handler\n"
        "   - 무엇을: patch\n"
        "   - 어디서: `src/auth/handler.py`\n"
        "   - 검증: pytest\n"
    )
    block = build_session_guidance_block(
        {"workspace_binding": {"path": str(ws), "label": "ws"}},
        plan_md=plan,
    )
    assert "per-dir hierarchy" in block
    assert "auth-specific" in block
    assert "root-only" not in block or "auth-specific" in block


def test_flat_agents_md_when_no_plan_paths(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "AGENTS.md").write_text("flat workspace guide", encoding="utf-8")
    block = build_session_guidance_block(
        {"workspace_binding": {"path": str(ws), "label": "ws"}},
        plan_md="## 합의\nno file paths here\n",
    )
    assert "Codex workspace guide" in block
    assert "flat workspace guide" in block


def test_bootstrap_workspace_memory_files(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "README.md").write_text("# Demo\n\nSample workspace.\n", encoding="utf-8")
    bootstrap_workspace_memory(ws, overwrite=True)
    assert (ws / ".agent-lab" / "PROJECT.md").is_file()
    assert (ws / "AGENTS.md").is_file()
    assert (ws / "SHARED_CONTEXT.md").is_file()
