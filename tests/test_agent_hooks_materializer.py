"""Agent hooks materializer."""

from __future__ import annotations

from agent_lab.agent.hooks_materializer import materialize_agent_hooks


def test_materialize_writes_manifest(tmp_path):
    written = materialize_agent_hooks(
        tmp_path,
        codex={"version": 1, "hooks": {}},
        claude={"PostEdit": []},
    )
    assert (tmp_path / ".agent-lab" / "agent-hooks" / "manifest.json").is_file()
    assert "codex" in written
    assert "claude" in written
