"""Build proposal harvest (M5) — T-B gates → Inbox build item."""

from __future__ import annotations

from typing import Any

from agent_lab.inbox_harvest import harvest_build_proposal
from agent_lab.room_objections import append_objection

_PLAN_WITH_ACTION = """\
## 합의

- 스윕 추가하기로 합의

## 지금 실행

1. cadence 스윕 스크립트 추가
   - 무엇을: `rebal_freq_sweep.py` 추가
   - 어디서: `quant/strategies/`
   - 검증: `pytest tests/test_sweep.py`
"""

_PLAN_NO_ACTION = """\
## 합의

- 아직 방향만 정함

## 쟁점 / 미결정

- 스윕 범위 미정
"""


def test_tb1_no_action_no_build():
    run_meta: dict[str, Any] = {}
    assert harvest_build_proposal(run_meta, plan_md=_PLAN_NO_ACTION) is None
    assert "human_inbox" not in run_meta


def test_build_proposal_happy_path():
    run_meta: dict[str, Any] = {}
    item = harvest_build_proposal(run_meta, plan_md=_PLAN_WITH_ACTION, human_turn=2)
    assert item is not None
    assert item["kind"] == "build"
    assert item["source"] == "orchestrator"
    assert item["trigger"] == "T-B1"
    assert item["action_ref"] == "now:1"
    assert "rebal_freq_sweep.py" in item["summary"]
    assert item["human_turn_id"] == 2
    assert run_meta.get("inbox_pending") is True


def test_ordering_pending_question_blocks_build():
    run_meta: dict[str, Any] = {
        "human_inbox": [{"id": "q1", "kind": "question", "status": "pending"}],
    }
    assert harvest_build_proposal(run_meta, plan_md=_PLAN_WITH_ACTION) is None
    # no build item added
    assert all(i["kind"] != "build" for i in run_meta["human_inbox"])


def test_tb2_open_block_objection_skips_build():
    run_meta: dict[str, Any] = {}
    append_objection(
        run_meta,
        from_agent="codex",
        act="BLOCK",
        body="스윕 스크립트 위험",
        human_turn=1,
        refs=["plan_action:1"],
    )
    assert harvest_build_proposal(run_meta, plan_md=_PLAN_WITH_ACTION) is None


def test_tb3_pending_execution_skips_build():
    run_meta: dict[str, Any] = {
        "executions": [{"id": "e1", "status": "pending_approval"}],
    }
    assert harvest_build_proposal(run_meta, plan_md=_PLAN_WITH_ACTION) is None


def test_tb3_dedupe_same_action():
    run_meta: dict[str, Any] = {}
    first = harvest_build_proposal(run_meta, plan_md=_PLAN_WITH_ACTION)
    second = harvest_build_proposal(run_meta, plan_md=_PLAN_WITH_ACTION)
    assert first is not None
    assert second is None  # same action_ref already has a build item
    assert sum(1 for i in run_meta["human_inbox"] if i["kind"] == "build") == 1


def test_plan_mode_noop():
    run_meta: dict[str, Any] = {}
    assert harvest_build_proposal(run_meta, plan_md=_PLAN_WITH_ACTION, mode="plan") is None
    assert "human_inbox" not in run_meta
