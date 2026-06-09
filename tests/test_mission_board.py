"""Mission Board + turn budget (MB-1, MB-2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.mission_board import (
    begin_human_turn,
    build_goal_chain,
    checkout_lane,
    clear_checkout,
    default_lane_roles,
    get_mission_board,
    get_turn_budget,
    public_mission_board_payload,
    public_turn_budget_payload,
    record_agent_call,
    record_autorun_tick,
    sync_mission_board,
)


def _write_run(folder: Path, run: dict) -> None:
    (folder / "run.json").write_text(
        json.dumps(run, indent=2) + "\n",
        encoding="utf-8",
    )


def test_default_lane_roles_has_three_discuss_agents():
    roles = default_lane_roles()
    assert roles["discuss"] == ["cursor", "codex", "claude"]


def test_build_goal_chain_with_plan_action(tmp_path: Path):
    run = {
        "verified_loop": {"loop_goal": {"text": "Ship feature"}},
        "mission_loop": {
            "enabled": True,
            "phase": "EXECUTE_QUEUE",
            "current_action_index": 1,
        },
    }
    plan_md = """1. First action
- 무엇을: do thing
- 어디서: src/
- 검증: make test
"""
    chain = build_goal_chain(run, plan_md=plan_md)
    kinds = [c["kind"] for c in chain]
    assert "verified_loop.loop_goal" in kinds
    assert any(c.get("index") == 1 for c in chain if c["kind"] == "plan_action")


def test_begin_human_turn_resets_agent_calls(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    _write_run(
        folder,
        {
            "turn_budget": {
                "caps": {"agent_calls_per_human_turn": 9},
                "counters": {"agent_calls_per_human_turn": 5, "human_turn": 1},
            }
        },
    )
    begin_human_turn(folder, human_turn=2)
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    counters = run["turn_budget"]["counters"]
    assert counters["human_turn"] == 2
    assert counters["agent_calls_per_human_turn"] == 0


def test_record_agent_call_increments_and_overflow_inbox(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    _write_run(
        folder,
        {
            "turn_budget": {
                "caps": {"agent_calls_per_human_turn": 2},
                "counters": {"agent_calls_per_human_turn": 0, "human_turn": 1},
            }
        },
    )
    record_agent_call(folder, human_turn=1, agent="cursor")
    record_agent_call(folder, human_turn=1, agent="codex")
    tb = record_agent_call(folder, human_turn=1, agent="claude")
    assert tb["counters"]["agent_calls_per_human_turn"] == 3
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert run["turn_budget"]["overflow"]["key"] == "agent_calls_per_human_turn"
    inbox = run.get("human_inbox") or []
    assert any(item.get("source") == "turn_budget" for item in inbox)


def test_checkout_lane_and_clear(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    _write_run(folder, {})
    checkout_lane(folder, "execute", action_index=2, execution_id="exec-1")
    board = get_mission_board(json.loads((folder / "run.json").read_text()))
    assert board["checkout"]["lane"] == "execute"
    assert board["checkout"]["action_index"] == 2
    clear_checkout(folder)
    board2 = get_mission_board(json.loads((folder / "run.json").read_text()))
    assert board2["checkout"] is None


def test_sync_mission_board_persists_goal_chain(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "plan.md").write_text(
        "1. Alpha\n- 무엇을: x\n- 어디서: y\n- 검증: z\n",
        encoding="utf-8",
    )
    run = {
        "mission_loop": {
            "enabled": True,
            "phase": "EXECUTE_QUEUE",
            "current_action_index": 1,
        }
    }
    sync_mission_board(run, plan_md=(folder / "plan.md").read_text())
    assert run["mission_board"]["goal_chain"]
    public = public_mission_board_payload(run)
    assert public["checked_out"] is False


def test_record_autorun_tick_hourly_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = tmp_path / "sess"
    folder.mkdir()
    _write_run(
        folder,
        {
            "turn_budget": {
                "caps": {"autorun_ticks_per_hour": 100},
                "counters": {
                    "autorun_ticks_this_hour": 0,
                    "autorun_tick_hour": None,
                },
            }
        },
    )
    monkeypatch.setattr(
        "agent_lab.mission_board._hour_bucket",
        lambda: "2026-06-09T10",
    )
    tb1 = record_autorun_tick(folder)
    tb2 = record_autorun_tick(folder)
    assert tb1["counters"]["autorun_ticks_this_hour"] == 1
    assert tb2["counters"]["autorun_ticks_this_hour"] == 2


def test_public_turn_budget_payload_budget_pct():
    run = {
        "turn_budget": {
            "caps": {"agent_calls_per_human_turn": 10},
            "counters": {"agent_calls_per_human_turn": 5},
        }
    }
    from agent_lab.mission_board import refresh_turn_budget

    refresh_turn_budget(run)
    payload = public_turn_budget_payload(run)
    assert payload["budget_pct"] == 50
