from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.goal_loop import (
    check_session_goal,
    goal_oracle_check,
    maybe_check_session_goal_after_turn,
    set_session_goal,
)
from agent_lab.run.meta import read_run_meta


def _session(tmp_path: Path) -> Path:
    folder = tmp_path / "session"
    folder.mkdir()
    (folder / "run.json").write_text(
        json.dumps(
            {
                "workflow_id": "room.parallel",
                "run_schema_version": 1,
                "turns": [],
                "actions": [],
                "approvals": [],
                "executions": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return folder


def test_mock_goal_oracle_passes_and_fails_on_backtick_literal(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    passed = goal_oracle_check(
        folder,
        "결론에 `GOAL_OK`를 기록한다",
        [{"content": "검토 완료: GOAL_OK"}],
    )
    failed = goal_oracle_check(
        folder,
        "결론에 `GOAL_OK`를 기록한다",
        [{"content": "아직 검토 중"}],
    )

    assert passed["verdict"] == "pass"
    assert passed["source"] == "mock"
    assert failed["verdict"] == "fail"
    assert "GOAL_OK" in failed["detail"]


def test_mock_goal_oracle_rejects_notready_substring_for_ready_goal(tmp_path: Path) -> None:
    folder = _session(tmp_path)

    result = goal_oracle_check(
        folder,
        "최종 답에 `READY` 포함",
        [{"role": "agent", "content": "Current state: NOTREADY"}],
    )

    assert result["verdict"] == "fail"
    assert "READY" in result["detail"]


def test_mock_goal_oracle_does_not_accept_human_echo(tmp_path: Path) -> None:
    folder = _session(tmp_path)

    result = goal_oracle_check(
        folder,
        "결론에 `GOAL_OK`를 기록한다",
        [
            {"role": "user", "content": "GOAL_OK를 달성해 주세요"},
            {"role": "agent", "content": "아직 검토 중"},
        ],
    )

    assert result["verdict"] == "fail"


def test_check_session_goal_records_achieved_status(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    set_session_goal(folder, "최종 답에 `READY` 포함", max_checks=5)

    result = check_session_goal(folder, [{"content": "최종 답: READY"}])

    assert result["checked"] is True
    run = read_run_meta(folder)
    assert run["goal_loop"]["status"] == "achieved"
    assert run["goal_loop"]["checks"][0]["verdict"] == "pass"
    assert run["goal_loop"]["checks"][0]["source"] == "mock"


def test_check_session_goal_stops_at_max_checks(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    set_session_goal(folder, "결론에 `MISSING` 포함", max_checks=1)

    first = check_session_goal(folder, [{"content": "not yet"}])
    second = check_session_goal(folder, [{"content": "still not yet"}])

    assert first["checked"] is True
    assert first["check"]["verdict"] == "fail"
    assert second == {
        "checked": False,
        "reason": "max_checks_reached",
        "session_goal": read_run_meta(folder)["session_goal"],
        "goal_loop": read_run_meta(folder)["goal_loop"],
    }
    assert len(read_run_meta(folder)["goal_loop"]["checks"]) == 1


def test_after_turn_feature_flag_off_is_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _session(tmp_path)
    set_session_goal(folder, "결론에 `READY` 포함")
    before = read_run_meta(folder)
    monkeypatch.delenv("AGENT_LAB_GOAL_LOOP", raising=False)

    result = maybe_check_session_goal_after_turn(folder, [{"content": "READY"}])

    assert result is None
    assert read_run_meta(folder) == before


def test_after_turn_fail_arms_bounded_auto_continue_signal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _session(tmp_path)
    set_session_goal(folder, "결론에 `READY` 포함")
    monkeypatch.setenv("AGENT_LAB_GOAL_LOOP", "1")
    monkeypatch.setenv("AGENT_LAB_GOAL_AUTO_CONTINUE", "1")

    result = maybe_check_session_goal_after_turn(folder, [{"content": "not yet"}])

    assert result is not None
    loop = read_run_meta(folder)["goal_loop"]
    assert loop["status"] == "open"
    assert loop["auto_continue_pending"] is True
    assert "한 턴 더 토론" in loop["continue_prompt"]


@pytest.mark.integration
def test_auto_continue_runs_exactly_one_extra_discuss_round(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab import room

    folder = _session(tmp_path)
    (folder / "topic.txt").write_text("goal auto continue\n", encoding="utf-8")
    (folder / "plan.md").write_text("", encoding="utf-8")
    (folder / "chat.jsonl").write_text("", encoding="utf-8")
    set_session_goal(folder, "결론에 `READY` 포함")
    monkeypatch.setenv("AGENT_LAB_GOAL_LOOP", "1")
    monkeypatch.setenv("AGENT_LAB_GOAL_AUTO_CONTINUE", "1")
    calls: list[int] = []

    def _rounds(*_args, **_kwargs):
        calls.append(len(calls) + 1)
        content = "not yet" if len(calls) == 1 else "READY"
        return [
            room.ChatMessage(
                role="agent",
                agent="codex",
                content=content,
                parallel_round=1,
            )
        ]

    monkeypatch.setattr(room, "run_agent_rounds", _rounds)

    messages, _plan = room.continue_room_round(
        folder,
        "첫 토론",
        agents=["codex"],
        synthesize=False,
        parallel_rounds=1,
    )

    assert calls == [1, 2]
    assert any(message.content == "READY" for message in messages)
    run = read_run_meta(folder)
    assert run["goal_loop"]["status"] == "achieved"
    assert len(run["goal_loop"]["checks"]) == 2
    assert len(run["turns"]) == 2


@pytest.mark.integration
def test_auto_continue_respects_goal_check_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab import room

    folder = _session(tmp_path)
    (folder / "topic.txt").write_text("goal capped\n", encoding="utf-8")
    (folder / "plan.md").write_text("", encoding="utf-8")
    (folder / "chat.jsonl").write_text("", encoding="utf-8")
    set_session_goal(folder, "결론에 `READY` 포함", max_checks=1)
    monkeypatch.setenv("AGENT_LAB_GOAL_LOOP", "1")
    monkeypatch.setenv("AGENT_LAB_GOAL_AUTO_CONTINUE", "1")
    calls: list[int] = []

    def _rounds(*_args, **_kwargs):
        calls.append(len(calls) + 1)
        return [
            room.ChatMessage(
                role="agent",
                agent="codex",
                content="not yet",
                parallel_round=1,
            )
        ]

    monkeypatch.setattr(room, "run_agent_rounds", _rounds)

    room.continue_room_round(
        folder,
        "첫 토론",
        agents=["codex"],
        synthesize=False,
        parallel_rounds=1,
    )

    assert calls == [1]
    assert len(read_run_meta(folder)["goal_loop"]["checks"]) == 1
