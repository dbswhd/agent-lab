"""Live delegate spike tests (mock path; optional live codex)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agent_mocks import disable_execute_inbox_mcp

from scripts.soak.live_delegate_spike import SPIKE_MARKER, run_live_delegate_spike


@pytest.fixture
def mock_cursor_for_dry_run(monkeypatch: pytest.MonkeyPatch):
    disable_execute_inbox_mcp(monkeypatch)
    monkeypatch.setenv("CURSOR_API_KEY", "test-key-for-mock")
    monkeypatch.setattr("agent_lab.agents.cursor_agent.is_available", lambda: True)


def test_live_delegate_spike_mock_go(mock_cursor_for_dry_run, tmp_path: Path):
    report = run_live_delegate_spike(work_parent=tmp_path, cleanup=False)
    assert report["status"] == "go", json.dumps(report, indent=2)
    checks = report["checks"]
    assert checks["handoff_attached"]
    assert checks["marker_in_worktree"]
    assert checks["marker_not_on_main"]
    assert checks["main_clean_after_delegate"]


@pytest.mark.live
def test_live_delegate_spike_real_codex(tmp_path: Path):
    if os.getenv("AGENT_LAB_RUN_LIVE", "").strip() not in {"1", "true", "yes"}:
        pytest.skip("set AGENT_LAB_RUN_LIVE=1 for live codex delegate spike")
    from agent_lab.app_config import apply_config_env

    apply_config_env()
    report = run_live_delegate_spike(work_parent=tmp_path, cleanup=False)
    if report["status"] == "skipped":
        pytest.skip(report.get("errors") or ["delegate spike skipped"])
    assert report["status"] == "go", json.dumps(report, indent=2)
    assert SPIKE_MARKER in json.dumps(report.get("checks") or {})
