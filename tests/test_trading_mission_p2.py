"""P2 tests — scheduler, watcher, delta export."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_lab.trading_mission.delta_export import (
    build_proposal_delta,
    delta_mission_id,
    write_proposal_delta,
)
from agent_lab.trading_mission.scheduler import (
    is_premarket_due,
    premarket_already_ran,
    scheduled_premarket_time,
    should_run_premarket,
)
from agent_lab.trading_mission.watcher import (
    _detect_events,
    _fingerprint,
    enqueue_events,
    read_pending_queue,
    watcher_tick,
)

_KST = timezone(timedelta(hours=9))


def test_scheduled_premarket_time_default(monkeypatch):
    monkeypatch.delenv("AGENT_LAB_TRADING_SCHEDULE", raising=False)
    assert scheduled_premarket_time() == (7, 30)


def test_is_premarket_due():
    morning = datetime(2026, 6, 13, 8, 0, tzinfo=_KST)
    early = datetime(2026, 6, 13, 6, 0, tzinfo=_KST)
    assert is_premarket_due(now=morning) is True
    assert is_premarket_due(now=early) is False


def test_premarket_already_ran():
    state = {"last_premarket_date": "2026-06-13"}
    assert premarket_already_ran(state, day="2026-06-13")
    assert not premarket_already_ran(state, day="2026-06-14")


def test_should_run_premarket_weekend():
    sat = datetime(2026, 6, 13, 8, 0, tzinfo=_KST)
    assert should_run_premarket(now=sat) is False


def test_detect_action_flag_event():
    prev = {"action_flag": False, "freshness_blocking": False, "kill_switch": False}
    curr = {"action_flag": True, "freshness_blocking": False, "kill_switch": False}
    events = _detect_events(prev, curr)
    assert len(events) == 1
    assert events[0]["trigger"] == "ACTION_REQUIRED.flag"


def test_fingerprint_from_snapshot():
    snap = {
        "freshness": {"blocking": True},
        "overlay_signals": {"kr_kospi_v1": {"flag": "ACTION_REQUIRED.flag"}},
        "kill_switch": False,
        "trade_allowed": False,
    }
    fp = _fingerprint(snap)
    assert fp["freshness_blocking"] is True
    assert fp["action_flag"] is True


def test_enqueue_and_read_queue(tmp_path, monkeypatch):
    q = tmp_path / "queue.jsonl"
    monkeypatch.setenv("AGENT_LAB_TRADING_MISSION_QUEUE", str(q))
    n = enqueue_events([{"kind": "delta", "trigger": "test", "reason": "x"}], queue_path=q)
    assert n == 1
    pending = read_pending_queue(queue_path=q)
    assert len(pending) == 1


def test_build_proposal_delta_caps_proposals(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_TRADING_DELTA_MAX_PROPOSALS", "2")
    session = tmp_path / "sess-delta"
    artifacts = session / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "market_snapshot.json").write_text(
        json.dumps({"trade_allowed": True, "eligible_cards": []}),
        encoding="utf-8",
    )
    (session / "plan.md").write_text("## 합의\n- ingest_ready: true\n", encoding="utf-8")
    drafts = [{"symbol": f"S{i}", "market": "kr", "side": "buy", "quantity": 1,
               "notional": 1, "order_type": "market", "thesis": "x" * 12,
               "data_sources": ["a"], "confidence": 0.5, "expires_at": "2026-06-13T15:20:00+09:00"}
              for i in range(5)]
    (artifacts / "proposals_draft.json").write_text(json.dumps(drafts), encoding="utf-8")
    delta = build_proposal_delta(session, trigger="test")
    assert len(delta["proposals"]) <= 2
    assert delta["kind"] == "delta"
    write_proposal_delta(session, delta)
    assert (artifacts / "proposal_delta.json").is_file()


def test_watcher_tick_no_pipeline(monkeypatch):
    monkeypatch.setattr(
        "agent_lab.trading_mission.watcher.detect_pipeline_root",
        lambda: None,
    )
    report = watcher_tick(enqueue=False)
    assert report["ok"] is False
