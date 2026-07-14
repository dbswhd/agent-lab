"""Structured logging + in-memory counters wrapping the dual-write mirror_* calls."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from agent_lab.mission.dual_write import mirror_inbox_resolution, mirror_plan_approval, mirror_plan_rejection
from agent_lab.mission.dual_write_observability import dual_write_counters_snapshot, reset_dual_write_counters


@pytest.fixture(autouse=True)
def _reset_counters():
    reset_dual_write_counters()
    yield
    reset_dual_write_counters()


def _session(tmp_path: Path) -> Path:
    folder = tmp_path / "session-1"
    folder.mkdir()
    (folder / "plan.md").write_text("# Plan\n\n- ship", encoding="utf-8")
    (folder / "run.json").write_text('{"plan_workflow":{"enabled":true,"phase":"HUMAN_PENDING"}}', encoding="utf-8")
    os.environ["AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS"] = folder.name
    return folder


def test_disabled_call_is_counted_but_not_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    folder = _session(tmp_path)
    with caplog.at_level(logging.INFO, logger="agent_lab.mission.dual_write"):
        result = mirror_plan_approval(folder, goal="ship")
    assert result["enabled"] is False
    snapshot = dual_write_counters_snapshot()
    assert snapshot["disabled_calls_total"] == 1
    assert snapshot["operations"] == {}
    assert caplog.records == []  # disabled is routine noise — no log line


def test_mirrored_call_is_counted_and_logged_info(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    folder = _session(tmp_path)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    with caplog.at_level(logging.INFO, logger="agent_lab.mission.dual_write"):
        result = mirror_plan_approval(folder, goal="ship")
    assert result["mirrored"] is True
    snapshot = dual_write_counters_snapshot()
    assert snapshot["operations"]["plan_approve"]["mirrored"] == 1
    assert any(r.levelno == logging.INFO and "plan_approve" in r.getMessage() for r in caplog.records)


def test_cohort_blocked_call_is_counted_separately_from_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    folder = _session(tmp_path)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", "some-other-session")
    with caplog.at_level(logging.INFO, logger="agent_lab.mission.dual_write"):
        result = mirror_plan_approval(folder, goal="ship")
    assert result["mirrored"] is False
    assert result["reason"] == "cohort_not_selected"
    snapshot = dual_write_counters_snapshot()
    assert snapshot["operations"]["plan_approve"]["blocked_cohort"] == 1
    assert snapshot["operations"]["plan_approve"]["error"] == 0
    assert any(r.levelno == logging.INFO for r in caplog.records)


def test_real_failure_is_counted_as_error_and_logged_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    folder = _session(tmp_path)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    # No Mission journal exists yet for this session -> mirror_inbox_resolution
    # takes the "mission_journal_missing" error path (mirrored=False, enabled=True).
    with caplog.at_level(logging.INFO, logger="agent_lab.mission.dual_write"):
        result = mirror_inbox_resolution(folder, item_id="item-1", answer="go")
    assert result["mirrored"] is False
    assert result["reason"] == "mission_journal_missing"
    snapshot = dual_write_counters_snapshot()
    assert snapshot["operations"]["inbox_resolve"]["error"] == 1
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_expected_boundary_is_not_counted_as_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from agent_lab.mission.dual_write_observability import record_dual_write_event

    folder = _session(tmp_path)
    result = {
        "enabled": True,
        "operation": "inbox_create",
        "mirrored": False,
        "reason": "mission_not_ready_to_execute",
    }
    with caplog.at_level(logging.INFO, logger="agent_lab.mission.dual_write"):
        record_dual_write_event(folder, result)
    snapshot = dual_write_counters_snapshot()
    assert snapshot["operations"]["inbox_create"]["expected_boundary"] == 1
    assert snapshot["operations"]["inbox_create"]["error"] == 0
    assert any(r.levelno == logging.INFO for r in caplog.records)
    assert not any(r.levelno == logging.WARNING for r in caplog.records)


def test_counters_accumulate_across_multiple_operations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _session(tmp_path)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    mirror_plan_approval(folder, goal="ship")
    mirror_plan_rejection(folder, note="revise", goal="ship")
    snapshot = dual_write_counters_snapshot()
    assert "plan_approve" in snapshot["operations"]
    assert "plan_reject" in snapshot["operations"]
