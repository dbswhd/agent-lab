from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_eval_loop_profile_row_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_MOCK_STRUCTURED_ENVELOPE", "1")
    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "0")
    monkeypatch.delenv("AGENT_LAB_MOCK_ACT_SCRIPT", raising=False)

    from agent_lab.loop_probe_eval import eval_loop_profile_row

    row = eval_loop_profile_row("cursor")
    assert row is not None
    assert row["agent"] == "cursor"
    assert row["eval_source"] == "mock"
    assert row["supports_tools"] is True
    assert row["supports_json_envelope"] is True


def test_run_loop_model_eval_writes_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_MOCK_STRUCTURED_ENVELOPE", "1")
    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "0")
    monkeypatch.delenv("AGENT_LAB_MOCK_ACT_SCRIPT", raising=False)

    out = tmp_path / "loop_model_eval.json"
    from agent_lab.loop_probe_eval import run_loop_model_eval

    rows = run_loop_model_eval(["cursor"], registry_path=out)
    assert len(rows) == 1
    assert out.is_file()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(payload.get("profiles"), list)
    assert payload["profiles"][0]["agent"] == "cursor"


def test_static_eval_skips_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "0")
    calls: list[str] = []

    def _fail(*_a: object, **_k: object) -> None:
        calls.append("call")
        raise RuntimeError("should not call")

    monkeypatch.setattr("agent_lab.agents.registry.call_agent_reply", _fail)

    from agent_lab.loop_probe_eval import eval_loop_profile_row

    row = eval_loop_profile_row("cursor", static_only=True)
    assert row is not None
    assert row["eval_source"] == "static"
    assert calls == []
