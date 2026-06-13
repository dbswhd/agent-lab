"""P0 tests for Trading Mission preflight, export, verify."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.trading_mission.blocked import write_blocked_artifacts
from agent_lab.trading_mission.export_batch import build_proposal_batch, write_proposal_batch
from agent_lab.trading_mission.preflight import build_market_snapshot, write_market_snapshot
from agent_lab.trading_mission.topic import render_premarket_topic
from agent_lab.trading_mission.verify import check_artifacts, trading_mission_goal_ok
from agent_lab.session_setup import (
    build_setup_run_meta,
    list_session_templates,
    template_guidance_block,
)
from agent_lab.agents.prompts import room_scribe_prompt


def test_trading_mission_template_listed(monkeypatch):
    monkeypatch.setattr(
        "agent_lab.extensions.quant_trading.quant_pipeline_available",
        lambda: True,
    )
    ids = [t["id"] for t in list_session_templates()]
    assert "trading-mission" in ids


def test_trading_mission_setup_meta():
    meta = build_setup_run_meta(
        workspace_id="quant-pipeline",
        session_template="trading-mission",
    )
    assert meta["session_template"] == "trading-mission"
    assert meta.get("mission_kind") == "trading_premarket"


def test_template_guidance_trading():
    block = template_guidance_block("trading-mission")
    assert "Trading Mission" in block
    assert "ingest_ready" in block


def test_room_scribe_prompt_trading():
    full = room_scribe_prompt({"session_template": "trading-mission"})
    assert "## 합의" in full
    assert "ingest_ready" in full
    default = room_scribe_prompt({"session_template": "general"})
    assert "## 합의" not in default or "ingest_ready" not in default


def test_render_premarket_topic():
    text = render_premarket_topic(max_proposals=3)
    assert "장전" in text
    assert "3" in text
    assert "{{" not in text


def test_preflight_snapshot_shape(tmp_path, monkeypatch):
    pipeline = tmp_path / "pipeline"
    (pipeline / "scripts" / "spec91").mkdir(parents=True)
    freshness_script = pipeline / "scripts" / "spec91" / "quant_control_freshness.py"
    freshness_script.write_text(
        'import json\nprint(json.dumps({"ok": True, "message": "ok", "rows": []}))\n',
        encoding="utf-8",
    )
    results = pipeline / "research" / "kr" / "results" / "demo"
    results.mkdir(parents=True)
    (results / "demo_pass_full.json").write_text(
        json.dumps({"verdict": "PASS", "is_winner": {"verdict": "PASS", "OOS": {"sharpe": 1.2}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))

    snap = build_market_snapshot(pipeline)
    assert snap["trade_allowed"] is True
    assert snap["freshness"]["ok"] is True
    assert any(c.get("verdict") == "PASS" for c in snap["eligible_cards"])


def test_blocked_artifacts_goal_ok(tmp_path):
    session = tmp_path / "sess-blocked"
    session.mkdir()
    snap = {
        "as_of": "2026-06-13T07:30:00+09:00",
        "freshness": {"blocking": True, "message": "stale kor_price"},
        "trade_allowed": False,
        "kill_switch": False,
    }
    write_market_snapshot(session, snap)
    write_blocked_artifacts(session, snap)
    goal = trading_mission_goal_ok(session)
    assert goal["ok"] is True


def test_export_batch_from_draft(tmp_path):
    session = tmp_path / "sess-export"
    artifacts = session / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "market_snapshot.json").write_text(
        json.dumps({"trade_allowed": True, "eligible_cards": []}),
        encoding="utf-8",
    )
    (session / "plan.md").write_text(
        """# plan

## 합의
- ingest_ready: true
- blocking_reason:
- active_strategies: ["vumis"]
- discuss_rounds_used: 1
""",
        encoding="utf-8",
    )
    (artifacts / "proposals_draft.json").write_text(
        json.dumps(
            [
                {
                    "symbol": "069500",
                    "market": "kr",
                    "side": "buy",
                    "quantity": 1,
                    "notional": 100000,
                    "order_type": "market",
                    "thesis": "test thesis for overlay rebalance",
                    "data_sources": ["overlay:kr_kospi_v1"],
                    "backtest_ref": "research/kr/results/overlay/kospi_v1_20260601_full.json",
                    "confidence": 0.6,
                }
            ]
        ),
        encoding="utf-8",
    )
    (artifacts / "playbook.md").write_text(
        "# 오늘 장중 행동\n\n## 규칙\n- approve only\n",
        encoding="utf-8",
    )
    batch = build_proposal_batch(session, mission_id="2026-06-13-premarket")
    assert batch["ingest_ready"] is True
    assert len(batch["proposals"]) == 1
    write_proposal_batch(session, batch)
    report = check_artifacts(session)
    assert report["ok"] is True


def test_resolve_freshness_python_prefers_pipeline_venv(tmp_path, monkeypatch):
    from agent_lab.trading_mission.preflight import _resolve_freshness_python

    pipeline = tmp_path / "pipeline"
    venv_py = pipeline / ".venv" / "bin" / "python"
    venv_py.parent.mkdir(parents=True)
    venv_py.write_text("", encoding="utf-8")
    monkeypatch.delenv("AGENT_LAB_FRESHNESS_PYTHON", raising=False)
    assert _resolve_freshness_python(pipeline) == str(venv_py)

    monkeypatch.setenv("AGENT_LAB_FRESHNESS_PYTHON", "/custom/py")
    assert _resolve_freshness_python(pipeline) == "/custom/py"


def test_ensure_mock_trading_artifacts_seeds_draft(tmp_path):
    from agent_lab.trading_mission.mock_artifacts import ensure_mock_trading_artifacts

    session = tmp_path / "sess-mock"
    artifacts = session / "artifacts"
    artifacts.mkdir(parents=True)
    snap = {
        "trade_allowed": False,
        "eligible_cards": [
            {
                "ref": "kospi_v1",
                "source_file": "research/kr/results/overlay/kospi_v1_20260601_full.json",
                "verdict": "PASS",
                "eligible_for_proposal": True,
            }
        ],
    }
    write_market_snapshot(session, snap)
    (session / "plan.md").write_text("# plan\n\n## Mock plan\n", encoding="utf-8")

    report = ensure_mock_trading_artifacts(session, snap, force_trade_allowed=True)
    assert report["draft_seeded"] is True
    assert report["proposal_count"] == 1
    assert report["trade_allowed"] is True

    batch = build_proposal_batch(session, mission_id="2026-06-13-premarket")
    assert batch["ingest_ready"] is True
    assert len(batch["proposals"]) == 1
