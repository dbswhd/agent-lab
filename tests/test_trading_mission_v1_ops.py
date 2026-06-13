"""v1 operational checklist tests (§7.10)."""

from __future__ import annotations

from pathlib import Path

from agent_lab.trading_mission.thin_runtime import get_intraday_status
from agent_lab.trading_mission.v1_ops import (
    build_blocked_fixture,
    build_fail_ref_fixture,
    run_v1_checklist,
)


def test_fail_ref_plan_gate_reject(tmp_path: Path):
    session = build_fail_ref_fixture(tmp_path)
    report = run_v1_checklist(fail_session=session)
    fail_check = next(c for c in report["checks"] if c["id"] == "fail_ref_plan_gate")
    assert fail_check["ok"] is True


def test_freshness_blocking_fixture(tmp_path: Path):
    session = build_blocked_fixture(tmp_path)
    report = run_v1_checklist(blocked_session=session)
    block_check = next(c for c in report["checks"] if c["id"] == "freshness_blocking")
    assert block_check["ok"] is True


def test_v1_synthetic_checklist_with_ingest(tmp_path: Path, monkeypatch):
    from agent_lab.trading_mission.native_ingest import resolve_quant_pipeline_src

    src = resolve_quant_pipeline_src()
    if src is None:
        return

    monkeypatch.setenv("AGENTIC_USE_NATIVE_INGEST", "1")
    fail_session = build_fail_ref_fixture(tmp_path)
    blocked_session = build_blocked_fixture(tmp_path)

    import sys

    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from quant_pipeline.agentic_trading.pilot_e2e import seed_pilot_session

    pass_session = tmp_path / "pass-session"
    db = tmp_path / "cp.sqlite3"
    seed_pilot_session(pass_session, mission_id="v1-test-pass")

    from agent_lab.trading_mission.ingest_bridge import ingest_proposal_batch

    ingest = ingest_proposal_batch(pass_session, db_path=db, force=True)
    assert ingest["ok"] is True

    report = run_v1_checklist(
        pass_session=pass_session,
        blocked_session=blocked_session,
        fail_session=fail_session,
        db_path=db,
    )
    assert report["ok"] is True
    assert report["passed"] == report["total"]


def test_thin_runtime_readonly(tmp_path: Path, monkeypatch):
    from agent_lab.trading_mission.native_ingest import resolve_quant_pipeline_src

    src = resolve_quant_pipeline_src()
    if src is None:
        return

    import sys

    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from quant_pipeline.agentic_trading.pilot_e2e import seed_pilot_session

    session = tmp_path / "thin-session"
    db = tmp_path / "thin.sqlite3"
    seed_pilot_session(session, mission_id="thin-test")
    monkeypatch.setenv("AGENTIC_USE_NATIVE_INGEST", "1")
    from agent_lab.trading_mission.ingest_bridge import ingest_proposal_batch

    ingest_proposal_batch(session, db_path=db, force=True)

    status = get_intraday_status(session, db_path=db)
    assert status["ok"] is True
    assert status["playbook"]["ok"] is True
    assert status["pending_batch"]["ok"] is True
    assert "full_room_discuss" in status["actions_forbidden"]
