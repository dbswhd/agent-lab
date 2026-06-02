"""pre_execute hooks before plan dry-run (Phase G2)."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from agent_lab.room_hooks import PreExecuteBlocked, run_pre_execute_hooks


def test_pre_execute_hook_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = tmp_path / "hooks.toml"
    cfg.write_text("[hooks]\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_LAB_HOOKS_PATH", str(cfg))
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
