"""Server-side room hooks."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from agent_lab.room.hooks import clear_hooks_config_cache, run_hook
from agent_lab.room.tasks import complete_task, normalize_task


def test_run_hook_exit_2_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    script = tmp_path / "block.sh"
    script.write_text(
        '#!/bin/sh\nread _\necho "nope" >&2\nexit 2\n',
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    cfg = tmp_path / "hooks.toml"
    cfg.write_text(
        f'[hooks]\ntask_completed = ["{script}"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_LAB_HOOKS_PATH", str(cfg))
    clear_hooks_config_cache()

    result = run_hook("task_completed", {"event": "task_completed", "task": {"id": "t-1"}})
    assert result.blocked is True
    assert "nope" in result.feedback


def test_task_completed_hook_blocks_complete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    script = tmp_path / "block.sh"
    script.write_text("#!/bin/sh\necho blocked >&2\nexit 2\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    cfg = tmp_path / "hooks.toml"
    cfg.write_text(f'[hooks]\ntask_completed = ["{script}"]\n', encoding="utf-8")
    monkeypatch.setenv("AGENT_LAB_HOOKS_PATH", str(cfg))
    clear_hooks_config_cache()

    meta: dict = {"tasks": [normalize_task({"id": "t-1", "title": "x", "status": "pending"})]}
    with pytest.raises(ValueError, match="blocked"):
        complete_task(meta, "t-1")


def test_teammate_idle_nonzero_does_not_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    script = tmp_path / "warn.sh"
    script.write_text("#!/bin/sh\necho hook-warn >&2\nexit 1\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    cfg = tmp_path / "hooks.toml"
    cfg.write_text(f'[hooks]\nteammate_idle = ["{script}"]\n', encoding="utf-8")
    monkeypatch.setenv("AGENT_LAB_HOOKS_PATH", str(cfg))
    clear_hooks_config_cache()

    result = run_hook("teammate_idle", {"event": "teammate_idle", "agent": "codex"})
    assert result.blocked is False
    assert result.sub_reason == "nonzero"
    assert "hook-warn" in result.feedback


def test_load_hooks_config_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = tmp_path / "hooks.toml"
    cfg.write_text('[hooks]\ntask_completed = ["echo x"]\n', encoding="utf-8")
    monkeypatch.setenv("AGENT_LAB_HOOKS_PATH", str(cfg))
    clear_hooks_config_cache()

    from agent_lab.room.hooks import load_hooks_config

    first = load_hooks_config()
    second = load_hooks_config()
    assert first == second

    cfg.write_text("[hooks]\n", encoding="utf-8")
    clear_hooks_config_cache()
    cleared = load_hooks_config()
    assert cleared.get("hooks", {}) == {}
