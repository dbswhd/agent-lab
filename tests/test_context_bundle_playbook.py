"""HS2-2 — playbook block injection into the R1 context bundle (mock-only)."""

from __future__ import annotations

from agent_lab.context.bundle import _append_playbook_block
from agent_lab.wisdom.playbook import add_bullet


def test_append_playbook_block_noop_when_no_bullets(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PLAYBOOK", "1")
    monkeypatch.setenv("AGENT_LAB_PLAYBOOK_PATH", str(tmp_path / "playbook.jsonl"))
    out = _append_playbook_block("base constraints", topic="아무 주제", parallel_round=1)
    assert out == "base constraints"


def test_append_playbook_block_r1_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PLAYBOOK", "1")
    path = tmp_path / "playbook.jsonl"
    monkeypatch.setenv("AGENT_LAB_PLAYBOOK_PATH", str(path))
    add_bullet("execute 전에 plan.md diff 확인 필수", "fp:a", path=path)

    r1 = _append_playbook_block("base", topic="execute 전에 plan.md diff 확인 필요", parallel_round=1)
    assert "플레이북" in r1
    assert "execute 전에 plan.md diff 확인 필수" in r1

    r2 = _append_playbook_block("base", topic="execute 전에 plan.md diff 확인 필요", parallel_round=2)
    assert r2 == "base"


def test_append_playbook_block_disabled_by_flag(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LAB_PLAYBOOK", raising=False)
    path = tmp_path / "playbook.jsonl"
    monkeypatch.setenv("AGENT_LAB_PLAYBOOK_PATH", str(path))
    add_bullet("execute 전에 plan.md diff 확인 필수", "fp:a", path=path)

    out = _append_playbook_block("base", topic="execute 전에 plan.md diff 확인 필요", parallel_round=1)
    assert out == "base"


def test_append_playbook_block_blank_topic_is_noop(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PLAYBOOK", "1")
    path = tmp_path / "playbook.jsonl"
    monkeypatch.setenv("AGENT_LAB_PLAYBOOK_PATH", str(path))
    add_bullet("execute 전에 plan.md diff 확인 필수", "fp:a", path=path)

    out = _append_playbook_block("base", topic="   ", parallel_round=1)
    assert out == "base"
