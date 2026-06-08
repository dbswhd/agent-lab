"""Room Hook Router — per-agent routing."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from agent_lab.room_hooks import clear_hooks_config_cache, run_hook_for_agent


def test_per_agent_post_agent_reply_routing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    cursor_script = tmp_path / "cursor.sh"
    cursor_script.write_text("#!/bin/sh\necho cursor-hook\n", encoding="utf-8")
    cursor_script.chmod(cursor_script.stat().st_mode | stat.S_IXUSR)
    codex_script = tmp_path / "codex.sh"
    codex_script.write_text("#!/bin/sh\necho codex-hook\n", encoding="utf-8")
    codex_script.chmod(codex_script.stat().st_mode | stat.S_IXUSR)
    cfg = tmp_path / "hooks.toml"
    cfg.write_text(
        f'[hooks.cursor]\npost_agent_reply = ["{cursor_script}"]\n'
        f'[hooks.codex]\npost_agent_reply = ["{codex_script}"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_LAB_HOOKS_PATH", str(cfg))
    clear_hooks_config_cache()

    cursor = run_hook_for_agent(
        "post_agent_reply",
        "cursor",
        {"event": "post_agent_reply", "content": "hi"},
    )
    codex = run_hook_for_agent(
        "post_agent_reply",
        "codex",
        {"event": "post_agent_reply", "content": "hi"},
    )
    assert "cursor-hook" in cursor.feedback
    assert "codex-hook" in codex.feedback


def test_global_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    script = tmp_path / "global.sh"
    script.write_text("#!/bin/sh\necho global\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    cfg = tmp_path / "hooks.toml"
    cfg.write_text(
        f'[hooks.global]\npre_agent_reply = ["{script}"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_LAB_HOOKS_PATH", str(cfg))
    clear_hooks_config_cache()

    result = run_hook_for_agent(
        "pre_agent_reply",
        "claude",
        {"event": "pre_agent_reply"},
    )
    assert "global" in result.feedback
