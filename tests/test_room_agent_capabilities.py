"""Agent capability profiles and specialist rounds."""

from __future__ import annotations

from agent_lab.room_agent_capabilities import (
    agent_capability_cwd,
    agent_workspace_lines,
    ensure_specialist_capabilities,
    specialist_round_agents,
)
from agent_lab.context_bundle import build_context_bundle
from agent_lab.room import ChatMessage


def test_specialist_round_agents():
    pool = ["cursor", "codex", "claude"]
    assert specialist_round_agents(pool, 1) == ["codex", "claude"]
    assert specialist_round_agents(pool, 2) == ["cursor"]


def test_asymmetric_workspace_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent_lab.workspace_roots.pipeline_root",
        lambda: tmp_path / "pipe",
    )
    (tmp_path / "pipe").mkdir()
    meta: dict = {}
    ensure_specialist_capabilities(meta)
    perms = {"cursor": {"local_pipeline": True}}
    codex_block = agent_workspace_lines("codex", perms, meta)
    cursor_block = agent_workspace_lines("cursor", perms, meta)
    assert "codex" in codex_block.lower()
    assert str(tmp_path / "pipe") in codex_block or "pipe" in codex_block
    assert agent_capability_cwd("codex", perms, meta) != agent_capability_cwd(
        "cursor", perms, meta
    )
    assert cursor_block != codex_block


def test_custom_cwd_path_overrides_role(tmp_path):
    custom = tmp_path / "agent-home"
    custom.mkdir()
    meta: dict = {
        "agent_capabilities": {
            "codex": {
                "tools": ["codex_cli"],
                "cwd_role": "repo",
                "cwd_path": str(custom),
            }
        }
    }
    cwd = agent_capability_cwd("codex", {}, meta)
    assert cwd == str(custom.resolve())


def test_context_meta_records_capability_cwd():
    meta: dict = {"turn_profile": "specialist"}
    ensure_specialist_capabilities(meta)
    bundle = build_context_bundle(
        "topic",
        [ChatMessage(role="user", agent=None, content="hi")],
        "codex",
        run_meta=meta,
        permissions={},
    )
    d = bundle.meta.to_dict()
    assert d.get("capability_cwd")
