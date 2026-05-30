"""Unified workspace roots for room agents."""

from __future__ import annotations

from agent_lab.workspace_roots import (
    primary_workspace,
    resolve_workspace_roots,
    workspace_roots_block,
)


def test_default_root_is_agent_lab():
    roots = resolve_workspace_roots(None)
    assert len(roots) >= 1
    assert primary_workspace(None) == roots[0]


def test_pipeline_root_when_enabled(tmp_path, monkeypatch):
    pipeline = tmp_path / "quant-pipeline"
    pipeline.mkdir()
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))
    perms = {
        "cursor": {"local_pipeline": True},
        "claude": {"local_pipeline": True},
    }
    roots = resolve_workspace_roots(perms)
    assert pipeline.resolve() in roots


def test_workspace_roots_block_lists_paths():
    block = workspace_roots_block(None)
    assert "Workspace roots" in block
    assert "agent-lab" in block.lower() or "/" in block
