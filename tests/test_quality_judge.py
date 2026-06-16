"""Tests for the LLM-as-judge quality eval (G8)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent_lab.quality_judge import (
    judge_live_enabled,
    judge_session,
    parse_judge_response,
)


def _good_json() -> str:
    return json.dumps(
        {
            "scores": {"goal_fit": 5, "correctness": 4, "completeness": 4, "clarity": 5, "efficiency": 3},
            "overall": 4.2,
            "verdict": "pass",
            "rationale": "Met the goal with clean diffs.",
        }
    )


def test_parse_clean_json() -> None:
    out = parse_judge_response(_good_json())
    assert out["scores"]["goal_fit"] == 5
    assert out["overall"] == pytest.approx(4.2)
    assert out["verdict"] == "pass"
    assert "goal" in out["rationale"].lower()


def test_parse_clamps_and_derives_overall() -> None:
    raw = json.dumps({"scores": {"goal_fit": 9, "correctness": 0}, "verdict": "pass"})
    out = parse_judge_response(raw)
    assert out["scores"]["goal_fit"] == 5  # clamped high
    assert out["scores"]["correctness"] == 1  # clamped low
    assert out["overall"] == pytest.approx(3.0)  # mean of present dims


def test_parse_json_embedded_in_prose() -> None:
    raw = "Here is my assessment:\n" + _good_json() + "\nThanks."
    assert parse_judge_response(raw)["overall"] == pytest.approx(4.2)


def test_parse_fallback_freetext() -> None:
    out = parse_judge_response("VERDICT: PASS\noverall: 4\nlooks good")
    assert out["verdict"] == "pass"
    assert out["overall"] == pytest.approx(4.0)


def test_parse_empty() -> None:
    out = parse_judge_response("")
    assert out["verdict"] == "fail"
    assert out["overall"] is None


def test_judge_live_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_JUDGE_LIVE", raising=False)
    assert judge_live_enabled() is False
    monkeypatch.setenv("AGENT_LAB_JUDGE_LIVE", "1")
    assert judge_live_enabled() is True


def _session(tmp_path: Path, *, usd: float = 0.0) -> Path:
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "topic.txt").write_text("Add retry to CLI", encoding="utf-8")
    (folder / "plan.md").write_text("## Plan\n- add retry\n", encoding="utf-8")
    (folder / "chat.jsonl").write_text(
        json.dumps({"role": "user", "content": "add retry"}) + "\n"
        + json.dumps({"role": "agent", "agent": "claude", "content": "done"}) + "\n",
        encoding="utf-8",
    )
    run = {"cost_ledger": {"cumulative": {"usd": usd}}} if usd else {}
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")
    return folder


def test_judge_session_disabled_when_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_JUDGE_LIVE", raising=False)
    calls: list[str] = []
    out = judge_session(_session(tmp_path))
    assert out["enabled"] is False
    assert calls == []  # no LLM invoked


def test_judge_session_with_injected_call_attaches_cost(tmp_path: Path) -> None:
    folder = _session(tmp_path, usd=0.84)
    captured: dict[str, Any] = {}

    def fake_judge(prompt: str) -> str:
        captured["prompt"] = prompt
        return _good_json()

    out = judge_session(folder, judge_call=fake_judge)
    assert out["enabled"] is True
    assert out["source"] == "live"
    assert out["overall"] == pytest.approx(4.2)
    assert out["cost"]["usd"] == pytest.approx(0.84)
    assert out["cost"]["usd_per_point"] == pytest.approx(round(0.84 / 4.2, 6))
    # prompt carried goal + plan
    assert "Add retry to CLI" in captured["prompt"]
    assert "add retry" in captured["prompt"]


def test_judge_session_never_raises(tmp_path: Path) -> None:
    def boom(_prompt: str) -> str:
        raise RuntimeError("LLM down")

    out = judge_session(_session(tmp_path), judge_call=boom)
    assert out["enabled"] is False
    assert "judge error" in out["reason"]


def test_score_session_includes_judge_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_JUDGE_LIVE", raising=False)
    from agent_lab.session_score import score_session

    report = score_session(_session(tmp_path))
    assert "judge" in report
    assert report["judge"]["enabled"] is False
    # existing structural keys preserved
    assert "scores" in report and "counts" in report
