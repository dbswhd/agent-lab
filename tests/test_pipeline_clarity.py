"""G002 — dedicated clarity scorer + concrete-anchor detection."""
from __future__ import annotations

import pytest

from agent_lab import clarity


@pytest.mark.parametrize(
    "text",
    [
        "fix src/agent_lab/run_meta.py",
        "implement #42",
        "fix processKeywordDetector",
        "update UserModel",
        "patch user_model",
        "add login - acceptance criteria: returns 401",
        "add ```ts const x = 1 ```",
    ],
)
def test_detect_concrete_anchors_true(text: str) -> None:
    assert clarity.detect_concrete_anchors(text) is True


@pytest.mark.parametrize("text", ["make it better", "improve the app", "do the thing", ""])
def test_detect_concrete_anchors_false(text: str) -> None:
    assert clarity.detect_concrete_anchors(text) is False


def test_score_ambiguity_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    assert clarity.score_ambiguity("fix src/foo.py") == 0.0
    assert clarity.score_ambiguity("make it better") == 0.8
    assert clarity.score_ambiguity("") == 1.0


def test_clarity_threshold_met(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    anchored = {"verified_loop": {"loop_goal": {"text": "fix src/foo.py null check"}}}
    vague = {"verified_loop": {"loop_goal": {"text": "make it better"}}}
    assert clarity.clarity_threshold_met(anchored) is True
    assert clarity.clarity_threshold_met(vague) is False


def test_parse_score_conservative() -> None:
    assert clarity._parse_score("0.2") == 0.2
    assert clarity._parse_score("ambiguity is 0.9 overall") == 0.9
    assert clarity._parse_score("no number here") == 0.8
