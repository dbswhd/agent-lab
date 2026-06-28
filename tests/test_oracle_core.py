"""Oracle core — structured parsing, evidence, live opt-in policy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_lab.goal_loop import goal_oracle_check
from agent_lab.oracle_core import (
    build_execute_oracle_prompt,
    literal_matches_text,
    mock_execute_oracle_response,
    mock_goal_oracle_response,
    oracle_live_enabled,
    parse_oracle_response,
    verify_literals,
)
from agent_lab.plan.execute_merge import oracle_verify
from agent_lab.plan.actions import PlanAction


def test_parse_structured_oracle_response():
    raw = "VERDICT: pass\nREASON: literals present\nEVIDENCE:\n- found `OK` in src/app.py"
    parsed = parse_oracle_response(raw)
    assert parsed["verdict"] == "pass"
    assert "literals" in parsed["detail"]
    assert parsed["evidence"] == ["found `OK` in src/app.py"]


def test_parse_legacy_pass_fail_prefix():
    assert parse_oracle_response("PASS: all good")["verdict"] == "pass"
    assert parse_oracle_response("FAIL: missing token")["verdict"] == "fail"


def test_mock_execute_oracle_emits_evidence(tmp_path: Path):
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir(parents=True)
    target.write_text("FLAG_OK = 1\n", encoding="utf-8")
    raw = mock_execute_oracle_response(
        "`src/app.py` contains `FLAG_OK`",
        [f"--- src/app.py ---\n{target.read_text()}"],
    )
    parsed = parse_oracle_response(raw)
    assert parsed["verdict"] == "pass"
    assert parsed["evidence"]


def test_oracle_verify_includes_evidence_and_source(tmp_path: Path):
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir(parents=True)
    target.write_text("DONE\n", encoding="utf-8")
    action = PlanAction(
        index=1,
        what="x",
        where="`src/app.py`",
        verify="`src/app.py` contains `DONE`",
        refs=(),
        raw="",
        kind="now",
    )
    result = oracle_verify(action, ["src/app.py"], workspace_root=tmp_path)
    assert result["verdict"] == "pass"
    assert result["source"] == "mock"
    assert result.get("evidence")
    assert result.get("prompt_version")


def test_goal_oracle_check_structured_mock(tmp_path: Path) -> None:
    session = tmp_path / "sess"
    session.mkdir()
    messages = [
        {"role": "agent", "content": "We recorded `GOAL_OK` in the summary."},
    ]
    check = goal_oracle_check(
        session,
        "결론에 `GOAL_OK`를 기록한다",
        messages,
    )
    assert check["verdict"] == "pass"
    assert check["source"] == "mock"
    assert check.get("evidence")


def test_oracle_live_enabled_unified_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_ORACLE_LIVE", raising=False)
    monkeypatch.delenv("AGENT_LAB_GOAL_ORACLE_LIVE", raising=False)
    assert oracle_live_enabled(goal=False) is False
    assert oracle_live_enabled(goal=True) is False
    monkeypatch.setenv("AGENT_LAB_ORACLE_LIVE", "1")
    assert oracle_live_enabled(goal=False) is True
    assert oracle_live_enabled(goal=True) is True


def test_verify_literals_skips_paths():
    assert verify_literals("`src/a.py` contains `TOKEN`") == ["TOKEN"]


def test_literal_matches_text_rejects_embedded_substring():
    assert literal_matches_text("READY", "STATUS = READY") is True
    assert literal_matches_text("READY", "NOTREADY") is False
    assert literal_matches_text("READY", "not ready") is True
    assert literal_matches_text("GOAL_OK", "review complete: GOAL_OK") is True
    assert literal_matches_text("GOAL_OK", "NO_GOAL_OK_EXTRA") is False


def test_mock_goal_oracle_rejects_ready_substring_in_notready():
    raw = mock_goal_oracle_response(
        "최종 답에 `READY` 포함",
        "Agent: status is NOTREADY for now.",
    )
    parsed = parse_oracle_response(raw)
    assert parsed["verdict"] == "fail"
    assert "READY" in parsed["detail"]


def test_mock_execute_oracle_rejects_ready_substring_in_notready():
    raw = mock_execute_oracle_response(
        "`src/app.py` contains `READY`",
        ["--- src/app.py ---\nNOTREADY = True\n"],
    )
    parsed = parse_oracle_response(raw)
    assert parsed["verdict"] == "fail"


def test_build_execute_prompt_includes_commands():
    prompt = build_execute_oracle_prompt(
        "run `make test` and ensure `OK` in output",
        ["--- a.py ---\nOK"],
    )
    assert "make test" in prompt
    assert "VERDICT:" in prompt
    assert "independent verification Oracle" not in prompt


def test_oracle_system_prompts_are_isolated_from_room():
    from agent_lab.oracle_core import ORACLE_SYSTEM_EXECUTE, ORACLE_SYSTEM_GOAL, oracle_system_prompt

    assert "NOT a Room discuss agent" in oracle_system_prompt("execute")
    assert "NOT a Room discuss agent" in oracle_system_prompt("goal")
    assert "Cursor" not in ORACLE_SYSTEM_EXECUTE
    assert "group chat" not in ORACLE_SYSTEM_GOAL


def test_invoke_oracle_live_uses_isolated_invoke(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab import oracle_core

    monkeypatch.setenv("AGENT_LAB_ORACLE_LIVE", "1")
    monkeypatch.setenv("AGENT_LAB_ORACLE_MODEL", "claude-sonnet-test")
    captured: dict[str, Any] = {}

    def _fake_invoke(system: str, user: str, **kwargs: Any) -> str:
        captured["system"] = system
        captured["kwargs"] = kwargs
        return "VERDICT: pass\nREASON: ok\nEVIDENCE:\n- checked"

    monkeypatch.setattr("agent_lab.claude.cli.invoke", _fake_invoke)
    raw, source = oracle_core.invoke_oracle("execute", "criterion block")
    assert source == "live"
    assert "Execute Oracle" in captured["system"]
    assert captured["kwargs"]["room_turn"] is False
    assert captured["kwargs"]["scribe"] is True
    assert captured["kwargs"]["model"] == "claude-sonnet-test"
    assert raw.startswith("VERDICT: pass")


def test_build_oracle_result_includes_model_for_live() -> None:
    from agent_lab.oracle_core import build_oracle_result

    result = build_oracle_result(
        raw="VERDICT: pass\nREASON: ok",
        source="live",
        kind="execute",
        model="claude-oracle-model",
    )
    assert result["model"] == "claude-oracle-model"
    assert result["prompt_version"] == "2026-06-26"
