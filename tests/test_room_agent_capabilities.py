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


def test_context_meta_records_asymmetric_capability_cwd(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    review = tmp_path / "review"
    execute = tmp_path / "execute"
    for path in (repo, review, execute):
        path.mkdir()

    monkeypatch.setattr("agent_lab.workspace_roots.pipeline_root", lambda: repo)
    monkeypatch.setattr("agent_lab.workspace_roots.project_root", lambda: review)

    meta: dict = {
        "turn_profile": "specialist",
        "workspace_binding": {"path": str(execute)},
    }
    ensure_specialist_capabilities(meta)

    def cwd_for(agent: str, parallel_round: int) -> str:
        bundle = build_context_bundle(
            "topic",
            [ChatMessage(role="user", agent=None, content="hi")],
            agent,
            run_meta=meta,
            permissions={},
            parallel_round=parallel_round,
        )
        return str(bundle.meta.to_dict().get("capability_cwd") or "")

    codex_cwd = cwd_for("codex", 1)
    claude_cwd = cwd_for("claude", 1)
    cursor_cwd = cwd_for("cursor", 2)

    assert codex_cwd == str(repo.resolve())
    assert claude_cwd == str(review.resolve())
    assert cursor_cwd == str(execute.resolve())
    assert len({codex_cwd, claude_cwd, cursor_cwd}) == 3
