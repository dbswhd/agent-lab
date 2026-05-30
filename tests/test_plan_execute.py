"""Plan action parser and execute container preservation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from agent_lab.plan_actions import parse_plan_action_sections, parse_plan_actions
from agent_lab.plan_execute import resolve_execution, run_dry_run
from agent_lab.plan_execute_snapshot import (
    build_diff,
    compute_touched_paths,
    create_snapshot,
    restore_snapshot,
)
from agent_lab.room import (
    ChatMessage,
    _write_session_files,
    consensus_reached,
    maybe_auto_scribe_after_consensus,
)

SAMPLE_PLAN = """## 다음에 할 일
1.
   - 무엇을: ROOM_SCRIBE 다음 액션 포맷을 3필드로 고정한다.
   - 어디서: `prompts.py` `ROOM_SCRIBE`
   - 검증: 정리 1회 후 `plan.md` 다음 액션에 3필드 포함 수동 확인.
   (ref: chat.jsonl#L42)

2. Human `#3 코드 OK` 전까지 `prompts.py` 수정 보류. (ref: chat.jsonl#L55)

3.
   - 무엇을: discuss turn 이후 execute 기록을 보존한다.
   - 어디서: `room.py`
   - 검증: discuss 1턴 후 `executions[]`가 유지된다.
"""

NEW_FORMAT_PLAN = """## 지금 실행
1.
   - 무엇을: plan parser에 지금 실행 섹션을 추가한다.
   - 어디서: `plan_actions.py`
   - 검증: pytest 통과.
   (ref: chat.jsonl#L10)

## 실행 순서 (이후)
2. Human 승인 전까지 UI 변경 보류. (ref: chat.jsonl#L11)

3.
   - 무엇을: roadmap 3필드 액션을 dry-run 허용한다.
   - 어디서: `plan_execute.py`
   - 검증: roadmap index로 dry-run 가능.
   (ref: chat.jsonl#L12)
"""


def test_parse_three_field_actions_only():
    actions = parse_plan_actions(SAMPLE_PLAN)
    assert len(actions) == 2
    assert actions[0].index == 1
    assert "ROOM_SCRIBE" in actions[0].what
    assert actions[0].expected_paths() == ["prompts.py"]
    assert actions[1].index == 3
    assert "executions" in actions[1].verify


def test_parse_empty_without_section():
    assert parse_plan_actions("## 합의된 점\n- nothing") == []


def test_legacy_sections_recommended_and_roadmap():
    sections = parse_plan_action_sections(SAMPLE_PLAN)
    assert sections["recommended"] is not None
    assert sections["recommended"]["index"] == 1
    assert sections["recommended"]["recommended"] is True
    assert len(sections["roadmap"]) == 2
    assert sections["roadmap"][0]["executable"] is False
    assert sections["roadmap"][1]["executable"] is True
    assert len(sections["actions"]) == 2


def test_now_and_roadmap_sections():
    sections = parse_plan_action_sections(NEW_FORMAT_PLAN)
    assert sections["recommended"]["index"] == 1
    assert sections["recommended"]["kind"] == "now"
    assert len(sections["roadmap"]) == 2
    assert sections["roadmap"][0]["executable"] is False
    assert sections["roadmap"][1]["executable"] is True
    assert sections["roadmap"][1]["kind"] == "roadmap"


def test_execute_containers_preserved_on_discuss_turn(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "topic.txt").write_text("topic\n", encoding="utf-8")
    (folder / "plan.md").write_text("# plan\n", encoding="utf-8")
    (folder / "run.json").write_text(
        json.dumps(
            {
                "actions": [{"action_id": "plan-action-4", "index": 4}],
                "approvals": [{"id": "appr-1", "vote": "approve"}],
                "executions": [{"id": "exec-1", "status": "completed"}],
                "turns": [{"mode": "discuss", "status": "completed"}],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    msgs = [
        ChatMessage(role="user", agent=None, content="hello"),
        ChatMessage(role="agent", agent="cursor", content="hi", parallel_round=1),
    ]
    _write_session_files(
        folder,
        "topic",
        msgs,
        "# plan\n",
        turn_meta={"mode": "discuss", "status": "completed"},
    )
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert run["actions"] == [{"action_id": "plan-action-4", "index": 4}]
    assert run["approvals"] == [{"id": "appr-1", "vote": "approve"}]
    assert run["executions"] == [{"id": "exec-1", "status": "completed"}]
    assert len(run["turns"]) == 2


def test_consensus_reached_helper():
    assert not consensus_reached(None)
    assert not consensus_reached({"status": "open"})
    assert not consensus_reached({"status": "incomplete"})
    assert consensus_reached({"status": "reached", "anchor": {"agent": "cursor"}})


def test_last_plan_update_consensus_trigger(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "topic.txt").write_text("topic\n", encoding="utf-8")
    msgs = [ChatMessage(role="user", agent=None, content="hello")]
    _write_session_files(
        folder,
        "topic",
        msgs,
        SAMPLE_PLAN,
        turn_meta={
            "mode": "plan",
            "status": "completed",
            "synthesize_only": True,
            "plan_trigger": "consensus_reached",
            "completed_at": "2026-05-31T00:00:00+00:00",
        },
    )
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    lpu = run["last_plan_update"]
    assert lpu["trigger"] == "consensus_reached"
    assert lpu["synthesize_only"] is False


def test_maybe_auto_scribe_skips_when_not_reached(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    with patch("agent_lab.room.synthesize_session_plan") as mock_synth:
        result = maybe_auto_scribe_after_consensus(
            folder,
            consensus_meta={"status": "incomplete"},
            synthesize=False,
            cancelled=False,
        )
    assert result is None
    mock_synth.assert_not_called()


def test_maybe_auto_scribe_skips_plan_mode(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    with patch("agent_lab.room.synthesize_session_plan") as mock_synth:
        result = maybe_auto_scribe_after_consensus(
            folder,
            consensus_meta={"status": "reached"},
            synthesize=True,
            cancelled=False,
        )
    assert result is None
    mock_synth.assert_not_called()


def test_maybe_auto_scribe_on_consensus_reached(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    with patch(
        "agent_lab.room.synthesize_session_plan",
        return_value=SAMPLE_PLAN,
    ) as mock_synth:
        result = maybe_auto_scribe_after_consensus(
            folder,
            consensus_meta={"status": "reached"},
            synthesize=False,
            cancelled=False,
        )
    assert result == SAMPLE_PLAN
    mock_synth.assert_called_once_with(
        folder,
        on_event=None,
        permissions=None,
        trigger="consensus_reached",
    )


def test_snapshot_restore_on_reject(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session = tmp_path / "sess"
    session.mkdir()
    pkg = workspace / "pkg"
    pkg.mkdir()
    target = pkg / "target.txt"
    target.write_text("before\n", encoding="utf-8")
    other = workspace / "other.txt"
    other.write_text("untouched wip\n", encoding="utf-8")

    exec_id = "exec-test123"
    manifest = create_snapshot(
        session,
        exec_id=exec_id,
        cwd=workspace,
        expected_paths=["pkg/target.txt"],
    )

    target.write_text("cursor edit\n", encoding="utf-8")
    created = pkg / "new_file.txt"
    created.write_text("new\n", encoding="utf-8")
    other.write_text("still wip\n", encoding="utf-8")

    touched = compute_touched_paths(
        session,
        exec_id=exec_id,
        cwd=workspace,
        manifest=manifest,
        expected_paths=["pkg/target.txt"],
    )
    assert "pkg/target.txt" in touched
    assert "pkg/new_file.txt" in touched
    diff, diff_stat = build_diff(
        session,
        exec_id=exec_id,
        cwd=workspace,
        manifest=manifest,
        touched_paths=touched,
    )
    assert "cursor edit" in diff
    assert diff_stat

    restore_snapshot(session, exec_id=exec_id, cwd=workspace, manifest=manifest)

    assert target.read_text(encoding="utf-8") == "before\n"
    assert other.read_text(encoding="utf-8") == "still wip\n"
    assert not created.exists()


def test_dry_run_failure_restores_snapshot(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session = tmp_path / "sess"
    session.mkdir()
    (session / "plan.md").write_text(
        """## 지금 실행
1.
   - 무엇을: 테스트 액션
   - 어디서: `target.txt`
   - 검증: 파일 변경 확인
""",
        encoding="utf-8",
    )
    (session / "run.json").write_text("{}\n", encoding="utf-8")
    target = workspace / "target.txt"
    target.write_text("before\n", encoding="utf-8")

    def _fail(**_kwargs):
        target.write_text("partial cursor edit\n", encoding="utf-8")
        raise RuntimeError("cursor boom")

    monkeypatch.setattr("agent_lab.agents.cursor_agent.is_available", lambda: True)
    monkeypatch.setattr("agent_lab.agents.cursor_agent.respond", _fail)
    monkeypatch.setattr(
        "agent_lab.plan_execute.primary_workspace",
        lambda _permissions=None: workspace,
    )

    try:
        run_dry_run(session, action_index=1, permissions={})
        assert False, "expected failure"
    except RuntimeError as e:
        assert "Cursor execute failed" in str(e)

    assert target.read_text(encoding="utf-8") == "before\n"
    assert not (session / ".execute-snapshots").exists()


def test_resolve_reject_restores_files(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session = tmp_path / "sess"
    session.mkdir()
    exec_id = "exec-resolve01"
    target = workspace / "target.txt"
    target.write_text("before\n", encoding="utf-8")
    manifest = create_snapshot(
        session,
        exec_id=exec_id,
        cwd=workspace,
        expected_paths=["target.txt"],
    )
    target.write_text("cursor edit\n", encoding="utf-8")

    (session / "run.json").write_text(
        json.dumps(
            {
                "executions": [
                    {
                        "id": exec_id,
                        "status": "pending_approval",
                        "snapshot_id": exec_id,
                        "expected_paths": ["target.txt"],
                        "paths_outside_expected": [],
                    }
                ]
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "agent_lab.plan_execute.primary_workspace",
        lambda _permissions=None: workspace,
    )

    result = resolve_execution(
        session,
        execution_id=exec_id,
        vote="reject",
        permissions={},
    )
    assert result["execution"]["status"] == "rejected"
    assert target.read_text(encoding="utf-8") == "before\n"
    assert not (session / ".execute-snapshots" / exec_id).exists()
