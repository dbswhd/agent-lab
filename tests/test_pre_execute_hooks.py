"""pre_execute hooks before plan dry-run (Phase G2)."""

from __future__ import annotations

import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_lab.room.hooks import PreExecuteBlocked, clear_hooks_config_cache, run_hook, run_pre_execute_hooks
from agent_lab.subprocess_env import subprocess_env


def test_pre_execute_hook_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = tmp_path / "hooks.toml"
    cfg.write_text("[hooks]\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_LAB_HOOKS_PATH", str(cfg))
    clear_hooks_config_cache()
    result = run_pre_execute_hooks(
        {"team_lead": "cursor"},
        {"what": "edit file", "index": 1},
        session_id="sess-1",
    )
    assert result["blocked"] is False


def test_pre_execute_hook_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    script = tmp_path / "block.sh"
    script.write_text("#!/bin/sh\necho verify failed >&2\nexit 2\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    cfg = tmp_path / "hooks.toml"
    cfg.write_text(f'[hooks]\npre_execute = ["{script}"]\n', encoding="utf-8")
    monkeypatch.setenv("AGENT_LAB_HOOKS_PATH", str(cfg))
    clear_hooks_config_cache()
    result = run_pre_execute_hooks(
        {},
        {"what": "x", "index": 1},
    )
    assert result["blocked"] is True
    assert "verify failed" in (result.get("feedback") or "")


def test_pre_execute_blocked_exception_carries_payload():
    pv = {"blocked": True, "feedback": "nope"}
    exc = PreExecuteBlocked("nope", pre_verify=pv)
    assert exc.pre_verify == pv


def test_run_hook_subprocess_uses_filtered_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = tmp_path / "hooks.toml"
    cfg.write_text('[hooks]\npre_execute = ["echo ok"]\n', encoding="utf-8")
    monkeypatch.setenv("AGENT_LAB_HOOKS_PATH", str(cfg))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-hook-leak-test")
    clear_hooks_config_cache()

    captured: dict[str, object] = {}

    def _fake_run(*args: object, **kwargs: object) -> object:
        captured["env"] = kwargs.get("env")
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with patch("agent_lab.room.hooks.subprocess.run", side_effect=_fake_run):
        run_hook("pre_execute", {"workspace": str(tmp_path)})

    env = captured.get("env")
    assert isinstance(env, dict)
    assert env == subprocess_env()
    assert "ANTHROPIC_API_KEY" not in env
