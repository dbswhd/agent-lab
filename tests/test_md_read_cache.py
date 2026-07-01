"""Tests for mtime-based MD read caches."""

from __future__ import annotations

from pathlib import Path

from agent_lab.platform_md import read_platform_md_for_injection
from agent_lab.workspace import md as workspace_md


def test_platform_md_cache_avoids_repeat_read(monkeypatch, tmp_path: Path) -> None:
    md_path = tmp_path / ".agent-lab" / "PLATFORM.md"
    md_path.parent.mkdir(parents=True)
    md_path.write_text("# Platform\nhello", encoding="utf-8")
    monkeypatch.setenv("AGENT_LAB_ROOT", str(tmp_path))

    calls = {"n": 0}
    original = Path.read_text

    def _counting_read(self: Path, *args, **kwargs):
        if self == md_path:
            calls["n"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _counting_read)

    assert read_platform_md_for_injection() == "# Platform\nhello"
    assert read_platform_md_for_injection() == "# Platform\nhello"
    assert calls["n"] == 1


def test_workspace_md_cache_avoids_repeat_read(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Agents\nrules", encoding="utf-8")
    (tmp_path / "SHARED_CONTEXT.md").write_text("# Shared\nctx", encoding="utf-8")
    run_meta = {"workspace_binding": {"path": str(tmp_path), "label": "test"}}

    calls = {"n": 0}
    original = Path.read_text

    def _counting_read(self: Path, *args, **kwargs):
        if self.name in {"AGENTS.md", "SHARED_CONTEXT.md"}:
            calls["n"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _counting_read)

    assert workspace_md.read_agents_md_for_injection(run_meta).startswith("# Agents")
    assert workspace_md.read_shared_context_for_injection(run_meta).startswith("# Shared")
    assert workspace_md.read_agents_md_for_injection(run_meta).startswith("# Agents")
    assert workspace_md.read_shared_context_for_injection(run_meta).startswith("# Shared")
    assert calls["n"] == 2
