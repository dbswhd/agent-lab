"""Tests for dynamic model catalog picker."""

from __future__ import annotations

import os

import pytest

from agent_lab.agent import model_catalog as mc


def test_codex_shows_all_5_6_tiers_plus_previous_generation() -> None:
    rows = mc.visible_models("codex")
    labels = [str(r.get("label")) for r in rows]
    # expand_top_version: every gpt-5.6 sibling tier (sol/terra/luna) shows,
    # plus one row of the previous generation (5.5).
    assert labels == ["GPT-5.6-Sol", "GPT-5.6-Terra", "GPT-5.6-Luna", "GPT-5.5"]


def test_resolve_latest_versions_collapses_same_version_siblings() -> None:
    # Synthetic stand-in for gpt-5.6-{sol,terra,luna}: three ids tied at the
    # same version. Without de-duping by version, the top-2 slice would be
    # ["a-flagship", "a-lite"] and drop version 5 entirely.
    models = [
        {"id": "a-flagship", "label": "A Flagship", "version": [6, 0, 0]},
        {"id": "a-lite", "label": "A Lite", "version": [6, 0, 0]},
        {"id": "b", "label": "B", "version": [5, 0, 0]},
    ]
    rows = mc._resolve_latest_versions(models, count=2)
    assert [r["id"] for r in rows] == ["a-flagship", "b"]


def test_resolve_latest_versions_expand_top_version_keeps_all_siblings() -> None:
    models = [
        {"id": "a-flagship", "label": "A Flagship", "version": [6, 0, 0]},
        {"id": "a-lite", "label": "A Lite", "version": [6, 0, 0]},
        {"id": "a-mini", "label": "A Mini", "version": [6, 0, 0]},
        {"id": "b", "label": "B", "version": [5, 0, 0]},
        {"id": "c", "label": "C", "version": [4, 0, 0]},
    ]
    rows = mc._resolve_latest_versions(models, count=2, expand_top_version=True)
    assert [r["id"] for r in rows] == ["a-flagship", "a-lite", "a-mini", "b"]


def test_cursor_catalog_curates_main_provider_families() -> None:
    rows = mc.visible_models("cursor")
    ids = {r["id"] for r in rows}
    assert {
        "default",
        "composer-2.5",
        "gpt-5.6-sol",
        "claude-opus-4-8",
        "grok-4.5",
    }.issubset(ids)


def test_cursor_families_expose_their_own_effort_tiers() -> None:
    # Cursor folds the tier into the model id itself, so — unlike Codex/Claude
    # — every selectable family carries its own "efforts" list; families
    # differ in which tiers Cursor actually offers (Grok has no xhigh/max —
    # verified live via Cursor.models.list(), see provider.py history).
    assert mc.effort_levels("cursor", "claude-opus-4-8") == [
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    ]
    assert mc.effort_levels("cursor", "grok-4.5") == ["low", "medium", "high"]
    assert mc.effort_levels("cursor", "composer-2.5") == []
    assert mc.effort_levels("cursor", "default") == []


def test_claude_latest_per_family() -> None:
    rows = mc.visible_models("claude")
    labels = [str(r.get("label")) for r in rows]
    assert labels == ["Fable 5", "Opus 4.8", "Sonnet 5.0", "Haiku 4.5"]
    fable = rows[0]
    assert fable.get("available", True) is True
    assert not fable.get("coming_soon_note")


def test_model_panel_payload_includes_effort() -> None:
    payload = mc.model_panel_payload("codex", active_model="gpt-5.5", active_effort="medium")
    assert payload["selected_model"] == "gpt-5.5"
    assert payload["selected_effort"] == "medium"
    # gpt-5.5's own discovered efforts (no "minimal", adds "xhigh") override
    # the provider-level default list — see model_catalog.py effort_levels().
    assert payload["efforts"] == ["low", "medium", "high", "xhigh"]
    assert len(payload["options"]) == 4


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


def test_cursor_apply_model_folds_default_effort_into_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab.agent import model_prefs as mp

    monkeypatch.setattr(mp, "_write_env", lambda k, v: monkeypatch.setenv(k, v))
    label = mp.apply_model_only("cursor", "claude-opus-4-8")
    assert label == "Claude Opus 4.8 · high"
    assert os.environ["CURSOR_MODEL"] == "claude-opus-4-8-high"
    assert mp.current_model_id("cursor") == "claude-opus-4-8"
    assert mp.current_effort("cursor") == "high"


def test_cursor_apply_effort_composes_into_stored_model_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab.agent import model_prefs as mp

    monkeypatch.setenv("CURSOR_MODEL", "claude-opus-4-8-high")
    monkeypatch.setattr(mp, "_write_env", lambda k, v: monkeypatch.setenv(k, v))
    label = mp.apply_effort_only("cursor", "xhigh")
    assert label == "claude-opus-4-8 · xhigh"
    assert os.environ["CURSOR_MODEL"] == "claude-opus-4-8-xhigh"
    assert mp.current_model_id("cursor") == "claude-opus-4-8"
    assert mp.current_effort("cursor") == "xhigh"


def test_cursor_switching_family_falls_back_when_tier_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab.agent import model_prefs as mp

    # Opus supports "xhigh"; Grok doesn't — switching families must land on
    # Grok's own default tier rather than composing an invalid id.
    monkeypatch.setenv("CURSOR_MODEL", "claude-opus-4-8-xhigh")
    monkeypatch.setattr(mp, "_write_env", lambda k, v: monkeypatch.setenv(k, v))
    label = mp.apply_model_only("cursor", "grok-4.5")
    assert label == "Grok 4.5 · high"
    assert os.environ["CURSOR_MODEL"] == "grok-4.5-high"


def test_cursor_switching_to_no_effort_model_drops_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab.agent import model_prefs as mp

    monkeypatch.setenv("CURSOR_MODEL", "claude-opus-4-8-high")
    monkeypatch.setattr(mp, "_write_env", lambda k, v: monkeypatch.setenv(k, v))
    label = mp.apply_model_only("cursor", "composer-2.5")
    assert label == "Composer 2.5"
    assert os.environ["CURSOR_MODEL"] == "composer-2.5"
    assert mp.current_effort("cursor") is None


def test_cursor_apply_effort_rejects_unsupported_tier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab.agent import model_prefs as mp

    monkeypatch.setenv("CURSOR_MODEL", "grok-4.5-high")
    monkeypatch.setattr(mp, "_write_env", lambda k, v: monkeypatch.setenv(k, v))
    with pytest.raises(ValueError):
        mp.apply_effort_only("cursor", "xhigh")
