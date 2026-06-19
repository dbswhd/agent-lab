"""Tests for default room model persistence."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_persist_and_load_default_room_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab import room_models_config as rmc

    monkeypatch.setattr(rmc, "config_dir", lambda: tmp_path)
    path = rmc.persist_default_room_models(["cursor", "kimi", "claude"])
    assert path.is_file()
    assert rmc.load_default_room_models() == ["cursor", "kimi", "claude"]


def test_apply_default_room_models_to_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab import room_models_config as rmc

    monkeypatch.setattr(rmc, "config_dir", lambda: tmp_path)
    monkeypatch.delenv("AGENT_LAB_ROOM_MODELS", raising=False)
    rmc.persist_default_room_models(["cursor", "local", "claude"])
    loaded = rmc.apply_default_room_models_to_env()
    assert loaded == ["cursor", "local", "claude"]
    import os

    assert os.environ["AGENT_LAB_ROOM_MODELS"] == "cursor,local,claude"
