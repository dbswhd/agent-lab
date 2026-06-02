"""Tests for ~/.agent-lab/config.toml loading."""

from __future__ import annotations

import os
from pathlib import Path

from agent_lab import app_config


def test_write_default_config(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "cfg"
    monkeypatch.setenv("AGENT_LAB_CONFIG_DIR", str(cfg_dir))
    monkeypatch.delenv("AGENT_LAB_CONFIG_PATH", raising=False)
    path = app_config.write_default_config()
    assert path.is_file()
    assert path.parent == cfg_dir
    text = path.read_text(encoding="utf-8")
    assert "[paths]" in text
    assert "[logging]" in text


def test_apply_config_env_sets_pipeline(tmp_path, monkeypatch):
    pipeline = tmp_path / "pipeline"
    pipeline.mkdir()
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    config = cfg_dir / "config.toml"
    config.write_text(
        f'[paths]\nquant_pipeline = "{pipeline}"\n\n[logging]\ndir = "{tmp_path / "logs"}"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_LAB_CONFIG_DIR", str(cfg_dir))
    monkeypatch.delenv("QUANT_PIPELINE_ROOT", raising=False)
    monkeypatch.delenv("AGENT_LAB_LOG_DIR", raising=False)
    app_config.apply_config_env()
    assert os.environ["QUANT_PIPELINE_ROOT"] == str(pipeline.resolve())
    assert os.environ["AGENT_LAB_LOG_DIR"] == str((tmp_path / "logs").resolve())


def test_apply_config_does_not_override_existing_env(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text(
        '[paths]\nquant_pipeline = "/should/not/win"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_LAB_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", "/explicit/env")
    app_config.apply_config_env()
    assert os.environ["QUANT_PIPELINE_ROOT"] == "/explicit/env"


def test_log_dir_creates_directory(tmp_path, monkeypatch):
    log_path = tmp_path / "nested" / "logs"
    monkeypatch.setenv("AGENT_LAB_LOG_DIR", str(log_path))
    resolved = app_config.log_dir()
    assert resolved == log_path.resolve()
    assert log_path.is_dir()


def test_user_agent_lab_root_ignores_bundled_runtime(tmp_path, monkeypatch):
    bundled = tmp_path / "Agent Lab.app/Contents/Resources/runtime"
    bundled.mkdir(parents=True)
    user_lab = tmp_path / "Projects" / "agent-lab"
    user_lab.mkdir(parents=True)
    monkeypatch.setenv("AGENT_LAB_ROOT", str(bundled))
    monkeypatch.setenv("AGENT_LAB_DEV_ROOT", str(user_lab))
    from agent_lab.workspace_roots import is_bundled_app_runtime, user_agent_lab_root

    assert is_bundled_app_runtime(bundled)
    assert user_agent_lab_root() == user_lab.resolve()


def test_list_workspace_presets_uses_dev_root_not_bundled(tmp_path, monkeypatch):
    bundled = tmp_path / "Agent Lab.app/Contents/Resources/runtime"
    bundled.mkdir(parents=True)
    user_lab = tmp_path / "Projects" / "agent-lab"
    user_lab.mkdir(parents=True)
    monkeypatch.setenv("AGENT_LAB_ROOT", str(bundled))
    monkeypatch.setenv("AGENT_LAB_DEV_ROOT", str(user_lab))
    monkeypatch.setattr(
        "agent_lab.session_setup.pipeline_root",
        lambda: None,
    )
    monkeypatch.setattr(
        "agent_lab.session_setup.lecture_script_root",
        lambda: None,
    )
    from agent_lab.session_setup import list_workspace_presets

    presets = list_workspace_presets()
    agent = next(p for p in presets if p["id"] == "agent-lab")
    assert agent["path"] == str(user_lab.resolve())


def test_resolve_sessions_dir_prefers_agent_lab(tmp_path, monkeypatch):
    lab = tmp_path / "agent-lab"
    sessions = lab / "sessions"
    sessions.mkdir(parents=True)
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text(
        f'[paths]\nagent_lab = "{lab}"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_LAB_CONFIG_DIR", str(cfg_dir))
    monkeypatch.delenv("AGENT_LAB_SESSIONS_DIR", raising=False)
    assert app_config.resolve_sessions_dir() == sessions.resolve()
