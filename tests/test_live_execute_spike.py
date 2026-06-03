"""Live M0 worktree spike (mocked unit + optional live integration)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agent_lab.live_execute_spike import (
    SPIKE_MARKER,
    SPIKE_REL_PATH,
    run_live_worktree_merge_spike,
    run_live_worktree_spike,
)


def _mock_respond(**kwargs):
    cwd = Path(kwargs["cwd"])
    target = cwd / "src" / "spike.txt"
    text = target.read_text(encoding="utf-8")
    if "LIVE_M0_OK" not in text:
        target.write_text(text.rstrip() + "\nLIVE_M0_OK\n", encoding="utf-8")
    return "VERIFICATION: PASS — LIVE_M0_OK present"


@pytest.fixture
def mock_cursor(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CURSOR_API_KEY", "test-key-for-mock")
    monkeypatch.setattr("agent_lab.agents.cursor_agent.is_available", lambda: True)
    monkeypatch.setattr("agent_lab.agents.cursor_agent.respond", _mock_respond)
    monkeypatch.setattr(
        "agent_lab.live_execute_spike._preflight_cursor",
        lambda: {
            "sdk_available": True,
            "ready": True,
            "degraded": False,
            "bridge_mode": "mock",
        },
    )


def test_live_spike_go_with_mocked_cursor(mock_cursor, tmp_path: Path):
    report = run_live_worktree_spike(work_parent=tmp_path, cleanup=False)
    assert report["status"] == "go", report
    checks = report["checks"]
    assert checks["isolation_worktree"]
    assert checks["main_clean_after_dry_run"]
    assert checks["cwd_is_worktree_root"]
    assert checks["worktree_removed_after_reject"]
    assert checks["main_clean_after_reject"]


def test_live_merge_spike_go_with_mocked_cursor(mock_cursor, tmp_path: Path):
    report = run_live_worktree_merge_spike(work_parent=tmp_path, cleanup=False)
    assert report["status"] == "go", report
    checks = report["checks"]
    assert checks["isolation_worktree"]
    assert checks["pending_approval"]
    assert checks["main_clean_after_dry_run"]
    assert checks["approve_status_merged"]
    assert checks["merge_commit_sha_present"]
    assert checks["head_is_merge_commit"]
    assert checks["base_head_changed"]
    assert checks["base_branch_contains_marker"]
    assert checks["main_clean_after_merge"]
    assert checks["worktree_removed_after_merge"]
    assert checks["exec_branch_removed_after_merge"]
    assert report["merge"]["status"] == "merged"
    assert report["merge"]["commit_sha"]
    assert SPIKE_MARKER in (tmp_path / "repo" / SPIKE_REL_PATH).read_text(encoding="utf-8")
    assert report["rollback"]["pre_merge_sha"]


def test_live_spike_skipped_when_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.setattr("agent_lab.agents.cursor_agent.is_available", lambda: False)
    report = run_live_worktree_spike(work_parent=tmp_path, cleanup=False)
    assert report["status"] == "skipped"


@pytest.mark.live
def test_live_spike_real_cursor_integration(tmp_path: Path):
    """Run only with AGENT_LAB_RUN_LIVE=1 and real CURSOR_API_KEY + bridge."""
    if os.getenv("AGENT_LAB_RUN_LIVE", "").strip() not in {"1", "true", "yes"}:
        pytest.skip("set AGENT_LAB_RUN_LIVE=1 to run live Cursor spike")
    from agent_lab.app_config import apply_config_env

    apply_config_env()
    report = run_live_worktree_spike(work_parent=tmp_path, cleanup=False)
    if report["status"] == "skipped":
        pytest.skip(report.get("errors") or ["cursor unavailable"])
    assert report["status"] == "go", json.dumps(report, indent=2)


@pytest.mark.live
def test_live_merge_spike_real_cursor_integration(tmp_path: Path):
    """Run only with AGENT_LAB_RUN_LIVE=1 and real CURSOR_API_KEY + bridge."""
    if os.getenv("AGENT_LAB_RUN_LIVE", "").strip() not in {"1", "true", "yes"}:
        pytest.skip("set AGENT_LAB_RUN_LIVE=1 to run live Cursor merge spike")
    from agent_lab.app_config import apply_config_env

    apply_config_env()
    report = run_live_worktree_merge_spike(work_parent=tmp_path, cleanup=False)
    if report["status"] == "skipped":
        pytest.skip(report.get("errors") or ["cursor unavailable"])
    assert report["status"] == "go", json.dumps(report, indent=2)
