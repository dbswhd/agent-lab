"""P1 tests for trading goal oracle, plan gate, wisdom tags."""

from __future__ import annotations

import json
from pathlib import Path

from agent_lab.goal_loop import goal_oracle_check
from agent_lab.mission_loop import evaluate_plan_gate
from agent_lab.session_setup import session_setup_options
from agent_lab.trading_mission.plan_gate import trading_plan_gate_issues
from agent_lab.trading_mission.trading_goal_oracle import (
    evaluate_trading_goal,
    is_trading_mission_run,
    mock_trading_goal_oracle_response,
)
from agent_lab.wisdom_index import build_wisdom_index


def _ready_session(tmp_path: Path) -> Path:
    session = tmp_path / "sess-goal"
    session.mkdir()
    artifacts = session / "artifacts"
    artifacts.mkdir()
    (artifacts / "market_snapshot.json").write_text(
        json.dumps(
            {
                "trade_allowed": True,
                "eligible_cards": [
                    {
                        "ref": "research/kr/results/overlay/kospi_v1_pass_full.json",
                        "verdict": "PASS",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (session / "plan.md").write_text(
        """# plan

## 합의
- ingest_ready: true

## 지금 실행

1. **Proposal batch**
   - 무엇을: save proposal batch json
   - 어디서: sessions/x/artifacts/proposal_batch.json
   - 검증: python -m agent_lab.trading_mission.verify --check batch
""",
        encoding="utf-8",
    )
    (artifacts / "playbook.md").write_text(
        "# 오늘 장중 행동\n\n- approve only\n",
        encoding="utf-8",
    )
    (artifacts / "proposal_batch.json").write_text(
        json.dumps(
            {
                "ingest_ready": True,
                "proposals": [
                    {
                        "symbol": "069500",
                        "data_sources": ["overlay:kr_kospi_v1"],
                        "backtest_ref": "research/kr/results/overlay/kospi_v1_pass_full.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (session / "run.json").write_text(
        json.dumps({"session_template": "trading-mission", "mission_kind": "trading_premarket"}),
        encoding="utf-8",
    )
    return session


def test_is_trading_mission_run():
    assert is_trading_mission_run({"session_template": "trading-mission"})
    assert not is_trading_mission_run({"session_template": "general"})


def test_trading_goal_oracle_pass(tmp_path):
    session = _ready_session(tmp_path)
    result = evaluate_trading_goal(session)
    assert result["ok"] is True
    raw = mock_trading_goal_oracle_response(session)
    assert "VERDICT: pass" in raw


def test_goal_loop_uses_trading_artifact_oracle(tmp_path):
    session = _ready_session(tmp_path)
    result = goal_oracle_check(session, "goal with `GOAL_OK`", [])
    assert result["verdict"] == "pass"
    assert result["source"] == "trading_artifact"


def test_trading_plan_gate_rejects_missing_playbook(tmp_path):
    session = tmp_path / "sess-gate"
    session.mkdir()
    (session / "plan.md").write_text(
        "# plan\n\n## 합의\n- ingest_ready: true\n",
        encoding="utf-8",
    )
    issues = trading_plan_gate_issues((session / "plan.md").read_text(), session)
    assert "missing_playbook" in issues


def test_evaluate_plan_gate_trading_checklist_ok(tmp_path):
    session = _ready_session(tmp_path)
    run = json.loads((session / "run.json").read_text(encoding="utf-8"))
    plan = (session / "plan.md").read_text(encoding="utf-8")
    result = evaluate_plan_gate(plan, run=run, session_folder=session)
    assert result["status"] == "ok"


def test_wisdom_index_trading_tags(tmp_path):
    session = _ready_session(tmp_path)
    index = build_wisdom_index(session, force=True)
    docs = index.get("documents") or []
    tagged = [d for d in docs if d.get("tags")]
    assert tagged
    assert any("trading:session:" in t for d in tagged for t in d.get("tags", []))


def test_session_setup_options_includes_trading_preset(monkeypatch):
    monkeypatch.setattr(
        "agent_lab.extensions.quant_trading.quant_pipeline_available",
        lambda: True,
    )
    opts = session_setup_options()
    assert "session_templates" in opts
    ids = [t["id"] for t in opts["session_templates"]]
    assert "trading-mission" in ids
