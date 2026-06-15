"""Tests for weekly offline lane (WireUpDecision + runtime push)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.quant]

from agent_lab.trading_mission.offline_lane import (
    offline_lane_ran_this_week,
    run_offline_lane,
    verify_offline_lane,
)
from agent_lab.trading_mission.wireup_decision import (
    build_wireup_decision,
    render_playbook_wireup_section,
)


def _seed_research(pipeline: Path) -> None:
    results = pipeline / "research" / "kr" / "results" / "overlay"
    results.mkdir(parents=True)
    (results / "good_20260601_120000_full.json").write_text(
        json.dumps(
            {
                "strategy": "good",
                "verdict": "PASS",
                "OOS": {"sharpe": 2.1, "mdd": -0.1},
                "fails": [],
            }
        ),
        encoding="utf-8",
    )
    fail_dir = pipeline / "research" / "kr" / "results" / "value"
    fail_dir.mkdir(parents=True)
    (fail_dir / "bad_20260601_120000_full.json").write_text(
        json.dumps(
            {
                "strategy": "bad",
                "is_winner": {"verdict": "FAIL", "fails": ["oos"], "OOS": {"sharpe": 0.1}},
            }
        ),
        encoding="utf-8",
    )


def test_build_wireup_decision_splits_active_and_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline = tmp_path / "pipeline"
    _seed_research(pipeline)
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))

    decision = build_wireup_decision(pipeline, sync_cards=True)

    assert decision["schema"] == "WireUpDecision/v1"
    assert "good" in decision["active_refs"]
    assert "bad" in decision["blocked_refs"]
    assert decision["wireup_ready"] is True


def test_run_offline_lane_writes_artifacts_and_pushes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline = tmp_path / "pipeline"
    _seed_research(pipeline)
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))
    state = tmp_path / "offline_state.json"
    monkeypatch.setenv("AGENT_LAB_OFFLINE_LANE_STATE", str(state))

    session = tmp_path / "sess-weekly"
    report = run_offline_lane(session, pipeline=pipeline, force=True)

    assert report["ok"] is True
    assert report["skipped"] is False
    assert (session / "artifacts" / "wireup_decision.json").is_file()
    assert (pipeline / "data" / "agentic" / "wireup_decision.json").is_file()
    assert (pipeline / "data" / "agentic" / "playbook.md").is_file()

    verify = verify_offline_lane(session)
    assert verify["ok"] is True
    assert "오늘 장중 행동" in (session / "artifacts" / "playbook.md").read_text(encoding="utf-8")


def test_offline_lane_skips_same_week(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline = tmp_path / "pipeline"
    _seed_research(pipeline)
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))
    state = tmp_path / "offline_state.json"
    monkeypatch.setenv("AGENT_LAB_OFFLINE_LANE_STATE", str(state))

    session = tmp_path / "sess-a"
    first = run_offline_lane(session, pipeline=pipeline, force=True)
    assert first["ok"] is True

    second = run_offline_lane(tmp_path / "sess-b", pipeline=pipeline, force=False)
    assert second["skipped"] is True
    assert offline_lane_ran_this_week(state)


def test_playbook_section_includes_intraday_header():
    md = render_playbook_wireup_section(
        {
            "mission_id": "2026-06-13-weekly",
            "generated_at": "2026-06-13T10:00:00+09:00",
            "wireup_ready": True,
            "active_refs": ["kospi_v1"],
            "watch_refs": [],
            "blocked_refs": ["bad"],
        }
    )
    assert "오늘 장중 행동" in md
    assert "kospi_v1" in md
