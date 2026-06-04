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


def test_bootstrap_workspace_memory_files(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "README.md").write_text("# Demo\n\nSample workspace.\n", encoding="utf-8")
    bootstrap_workspace_memory(ws, overwrite=True)
    assert (ws / ".agent-lab" / "PROJECT.md").is_file()
    assert (ws / "AGENTS.md").is_file()
    assert (ws / "SHARED_CONTEXT.md").is_file()
