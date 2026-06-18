from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.runtime.adapters import (
    ExecuteInvokeRequest,
    RepairInvokeRequest,
    invoke_execute,
    invoke_repair,
    normalize_execute_agent,
    pick_repair_agent,
    verify_follow_ups,
)


def test_normalize_execute_agent_defaults() -> None:
    assert normalize_execute_agent(None) == "cursor"
    assert normalize_execute_agent("codex") == "codex"


def test_normalize_execute_agent_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="cursor or codex"):
        normalize_execute_agent("claude")


def test_verify_follow_ups_skips_placeholder() -> None:
    assert verify_follow_ups("") == []
    assert verify_follow_ups("none") == []
    ups = verify_follow_ups("make test")
    assert len(ups) == 1
    assert "make test" in ups[0]


def test_invoke_execute_cursor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _respond(**kwargs):
        captured.update(kwargs)
        return "cursor-ok"

    monkeypatch.setattr("agent_lab.agents.cursor_agent.respond", _respond)
    req = ExecuteInvokeRequest(
        system="sys",
        user="work",
        permissions={},
        cwd=tmp_path,
        verify_follow_ups=["follow"],
    )
    assert invoke_execute("cursor", req) == "cursor-ok"
    assert captured["follow_ups"] == ["follow"]
    assert captured["cwd"] == tmp_path


def test_invoke_execute_codex_appends_verify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _respond(**kwargs):
        captured.update(kwargs)
        return "codex-ok"

    monkeypatch.setattr("agent_lab.agents.codex_agent.respond", _respond)
    ups = verify_follow_ups("pytest -q")
    req = ExecuteInvokeRequest(
        system="sys",
        user="work",
        permissions={},
        cwd=tmp_path,
        verify_follow_ups=ups,
    )
    assert invoke_execute("codex", req) == "codex-ok"
    user = str(captured["user"])
    assert "work" in user
    assert "same execution" in user
    assert "pytest -q" in user


def test_invoke_repair_cursor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _respond(**kwargs):
        captured.update(kwargs)
        return "repaired"

    monkeypatch.setattr("agent_lab.agents.cursor_agent.respond", _respond)
    req = RepairInvokeRequest(
        system="repair",
        user="fix it",
        permissions={},
        cwd=tmp_path,
        verify_follow_ups=["v"],
    )
    assert invoke_repair("cursor", req) == "repaired"
    assert captured["follow_ups"] == ["v"]


def test_pick_repair_agent_prefers_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agent_lab.agents.registry.available_agents",
        lambda: ["cursor", "codex"],
    )
    target = {"executor": "cursor"}
    assert pick_repair_agent(target, "codex") == "codex"


def test_plan_execute_call_execute_agent_uses_adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.plan_execute import _call_execute_agent

    captured: dict[str, object] = {}

    def _invoke(agent_id: str, req: ExecuteInvokeRequest) -> str:
        captured["agent_id"] = agent_id
        captured["user"] = req.user
        return "via-adapter"

    monkeypatch.setattr("agent_lab.plan_execute_prompts.invoke_execute", _invoke)
    out = _call_execute_agent(
        "codex",
        user="do work",
        permissions={},
        cwd=tmp_path,
        on_activity=None,
        verify="none",
    )
    assert out == "via-adapter"
    assert captured["agent_id"] == "codex"
    assert captured["user"] == "do work"
