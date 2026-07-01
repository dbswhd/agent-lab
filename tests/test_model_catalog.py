"""Tests for dynamic model catalog picker."""

from __future__ import annotations

import pytest

from agent_lab.agent import model_catalog as mc


def test_codex_shows_latest_two_versions() -> None:
    rows = mc.visible_models("codex")
    labels = [str(r.get("label")) for r in rows]
    assert labels == ["GPT-5.5", "GPT-5.4"]


def test_claude_latest_per_family() -> None:
    rows = mc.visible_models("claude")
    labels = [str(r.get("label")) for r in rows]
    assert labels == ["Fable 5", "Opus 4.8", "Sonnet 5.0", "Haiku 4.5"]
    fable = rows[0]
    assert fable.get("available") is False
    assert fable.get("coming_soon_note")


def test_model_panel_payload_includes_effort() -> None:
    payload = mc.model_panel_payload("codex", active_model="gpt-5.5", active_effort="medium")
    assert payload["selected_model"] == "gpt-5.5"
    assert payload["selected_effort"] == "medium"
    assert payload["efforts"] == ["minimal", "low", "medium", "high"]
    assert len(payload["options"]) == 2


def test_effort_levels_vary_by_provider_and_model() -> None:
    # Codex exposes 4 tiers; Claude's flagship families expose 5, but the
    # lighter Haiku family overrides down to 3 — tier count is not a single
    # provider-wide constant.
    assert mc.effort_levels("codex") == ["minimal", "low", "medium", "high"]
    assert mc.effort_levels("claude") == ["low", "medium", "high", "xhigh", "max"]
    assert mc.effort_levels("claude", "opus") == ["low", "medium", "high", "xhigh", "max"]
    assert mc.effort_levels("claude", "haiku") == ["low", "medium", "high"]


def test_apply_model_only_keeps_effort(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from agent_lab.agent import model_prefs as mp

    monkeypatch.setenv("CLAUDE_MODEL", "opus")
    monkeypatch.setenv("CLAUDE_REASONING_EFFORT", "high")
    monkeypatch.setattr(mp, "_write_env", lambda k, v: monkeypatch.setenv(k, v))
    label = mp.apply_model_only("claude", "sonnet")
    assert label == "Sonnet 5.0 · high"
    assert mp.current_model_id("claude") == "sonnet"
    assert mp.current_effort("claude") == "high"


def test_apply_effort_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.agent import model_prefs as mp

    monkeypatch.setenv("CODEX_MODEL", "gpt-5.5")
    monkeypatch.setenv("CODEX_REASONING_EFFORT", "high")
    monkeypatch.setenv("CODEX_ROOM_REASONING_EFFORT", "high")
    monkeypatch.setattr(mp, "_write_env", lambda k, v: monkeypatch.setenv(k, v))
    label = mp.apply_effort_only("codex", "low")
    assert label == "gpt-5.5 · low"
    assert mp.current_effort("codex") == "low"
