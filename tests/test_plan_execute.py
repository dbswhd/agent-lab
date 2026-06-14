"""Plan action parser and execute container preservation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_mocks import disable_execute_inbox_mcp

from agent_lab.plan_actions import (
    find_dry_run_action,
    parse_plan_action_sections,
    parse_plan_actions,
)
from agent_lab.plan_execute import list_plan_actions, resolve_execution, run_dry_run
from agent_lab.plan_pending import PlanSnapshotRequired, approve_pending_plan, ensure_plan_snapshot_approved
from agent_lab.plan_execute_paths import paths_relative_to_workspace
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


def _seed_approved_plan_snapshot(
    folder: Path,
    plan_md: str,
    *,
    action_index: int = 1,
    kind: str = "now",
) -> None:
    action = find_dry_run_action(plan_md, action_index, kind=kind)
    assert action is not None
    try:
        ensure_plan_snapshot_approved(folder, action, plan_md)
    except PlanSnapshotRequired as exc:
        approve_pending_plan(folder, exc.pending_plan["id"])


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


def _write_pending_consensus(
    folder: Path,
    *,
    excerpt: str = "topic",
    message_count: int = 1,
) -> None:
    from agent_lab.run_meta import write_run_meta

    write_run_meta(
        folder,
        {
            "consensus_agreements": [
                {
                    "id": "agr-test",
                    "excerpt": excerpt,
                    "status": "reached",
                    "plan_synced": False,
                    "message_count": message_count,
                }
            ],
        },
    )


def test_duplicate_index_resolves_by_kind():
    plan = """## 지금 실행
1.
   - 무엇을: now action
   - 어디서: `now.txt`
   - 검증: now ok

## 실행 순서 (이후)
1.
   - 무엇을: roadmap action
   - 어디서: `roadmap.txt`
   - 검증: roadmap ok
"""
    now = find_dry_run_action(plan, 1, kind="now")
    roadmap = find_dry_run_action(plan, 1, kind="roadmap")
    assert now is not None and now.what == "now action"
    assert roadmap is not None and roadmap.what == "roadmap action"
    assert now.action_id == "plan-action-now-1"
    assert roadmap.action_id == "plan-action-roadmap-1"


def test_expected_paths_filter_backtick_false_positives():
    plan = """## 지금 실행
1.
   - 무엇을: dry-run 감사 추가
   - 어디서: `build.mjs` `page.evaluate` `9.2→9.3` `10.6→10.7`
   - 검증: diff 확인
"""
    actions = parse_plan_actions(plan)
    assert actions[0].expected_paths() == ["build.mjs"]


def test_snapshot_absolute_path_normalized_to_cwd_relative(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session = tmp_path / "sess"
    session.mkdir()
    target = workspace / "build.mjs"
    target.write_text("before\n", encoding="utf-8")

    snapshot_paths = paths_relative_to_workspace(workspace, [str(target.resolve())])
    assert snapshot_paths == ["build.mjs"]

    exec_id = "exec-abs-path"
    manifest = create_snapshot(
        session,
        exec_id=exec_id,
        cwd=workspace,
        expected_paths=snapshot_paths,
    )
    assert manifest["files"]["build.mjs"]["existed"] is True

    target.write_text("after\n", encoding="utf-8")
    touched = compute_touched_paths(
        session,
        exec_id=exec_id,
        cwd=workspace,
        manifest=manifest,
        expected_paths=snapshot_paths,
    )
    assert touched == ["build.mjs"]
    diff, diff_stat = build_diff(
        session,
        exec_id=exec_id,
        cwd=workspace,
        manifest=manifest,
        touched_paths=touched,
    )
    assert "after" in diff
    assert diff_stat


def test_verification_paths_from_verify_field():
    plan = """## 지금 실행
1.
   - 무엇을: dry-run 감사 실행
   - 어디서: `build.mjs`
   - 검증: 레이아웃 변경 없이 `break-report.json` 로그 출력
"""
    actions = parse_plan_actions(plan)
    assert actions[0].expected_paths() == ["build.mjs"]
    assert actions[0].verification_paths() == ["break-report.json"]
    assert actions[0].monitored_paths() == ["build.mjs", "break-report.json"]


def test_root_dir_listing_detects_new_sibling_file(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session = tmp_path / "sess"
    session.mkdir()
    target = workspace / "build.mjs"
    target.write_text("before\n", encoding="utf-8")

    exec_id = "exec-root-sibling"
    manifest = create_snapshot(
        session,
        exec_id=exec_id,
        cwd=workspace,
        expected_paths=["build.mjs"],
    )
    assert manifest["dir_listings"]["."]

    artifact = workspace / "break-report.json"
    artifact.write_text("{}\n", encoding="utf-8")

    touched = compute_touched_paths(
        session,
        exec_id=exec_id,
        cwd=workspace,
        manifest=manifest,
        expected_paths=["build.mjs"],
    )
    assert "break-report.json" in touched


def test_approve_empty_source_diff_with_verification_paths_is_review_required(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session = tmp_path / "sess"
    session.mkdir()
    exec_id = "exec-artifact-review"
    target = workspace / "build.mjs"
    target.write_text("same\n", encoding="utf-8")
    create_snapshot(
        session,
        exec_id=exec_id,
        cwd=workspace,
        expected_paths=["build.mjs", "break-report.json"],
    )

    (session / "run.json").write_text(
        json.dumps(
            {
                "executions": [
                    {
                        "id": exec_id,
                        "status": "pending_approval",
                        "snapshot_id": exec_id,
                        "workspace_root": str(workspace),
                        "expected_paths": ["build.mjs"],
                        "verification_paths": ["break-report.json"],
                        "snapshot_paths": ["build.mjs", "break-report.json"],
                        "source_snapshot_paths": ["build.mjs"],
                        "artifact_snapshot_paths": ["break-report.json"],
                        "paths_outside_expected": [],
                        "draft_summary": "break-report.json generated",
                        "empty_source_diff": True,
                        "needs_artifact_review": True,
                        "verification_artifacts": {
                            "ok": True,
                            "pdf_path": str(workspace / "book.pdf"),
                            "pdf_page_count": 26,
                            "break_report": {
                                "path": str(workspace / "break-report.json"),
                                "baselinePdfPageCount": 26,
                            },
                        },
                    }
                ]
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "agent_lab.plan_execute.resolve_execute_workspace",
        lambda _permissions=None, _expected=None: (workspace, {}),
    )

    result = resolve_execution(
        session,
        execution_id=exec_id,
        vote="approve",
        permissions={},
    )
    assert result["execution"]["status"] == "review_required"


def test_approve_blocks_without_verification_artifacts(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session = tmp_path / "sess"
    session.mkdir()
    exec_id = "exec-gate-block"
    (session / "run.json").write_text(
        json.dumps(
            {
                "executions": [
                    {
                        "id": exec_id,
                        "status": "pending_approval",
                        "needs_artifact_review": True,
                        "verification_paths": ["break-report.json"],
                        "verification_artifacts": {"ok": False},
                    }
                ]
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "agent_lab.plan_execute.resolve_execute_workspace",
        lambda _permissions=None, _expected=None: (workspace, {}),
    )
    with pytest.raises(ValueError, match="PDF"):
        resolve_execution(
            session,
            execution_id=exec_id,
            vote="approve",
            permissions={},
        )


def test_dry_run_rejects_when_expected_paths_missing(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session = tmp_path / "sess"
    session.mkdir()
    (session / "plan.md").write_text(
        """## 지금 실행
1.
   - 무엇을: 테스트 액션
       - 어디서: `deep/nested/missing.txt`
   - 검증: 파일 변경 확인
""",
        encoding="utf-8",
    )
    (session / "run.json").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr("agent_lab.agents.cursor_agent.is_available", lambda: True)
    monkeypatch.setattr(
        "agent_lab.plan_execute.resolve_execute_workspace",
        lambda _permissions=None, _expected=None: (workspace, {}),
    )
    monkeypatch.setattr(
        "agent_lab.plan_execute.workspace_path_info",
        lambda cwd, _expected: {
            "path": str(cwd),
            "label": "workspace",
            "paths_found": [],
            "paths_missing": ["deep/nested/missing.txt"],
        },
    )

    plan_md = (session / "plan.md").read_text(encoding="utf-8")
    _seed_approved_plan_snapshot(session, plan_md)
    with pytest.raises(ValueError, match="none of the expected plan paths exist"):
        run_dry_run(session, action_index=1, permissions={})


def test_dry_run_allows_new_file_under_workspace(tmp_path: Path, monkeypatch):
    disable_execute_inbox_mcp(monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session = tmp_path / "sess"
    session.mkdir()
    target = workspace / "RECIPE.md"
    (session / "plan.md").write_text(
        f"""## 지금 실행
1.
   - 무엇을: 레시피 작성
   - 어디서: `{target}`
   - 검증: RECIPE.md 생성
""",
        encoding="utf-8",
    )
    (session / "run.json").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr("agent_lab.agents.cursor_agent.is_available", lambda: True)
    monkeypatch.setattr(
        "agent_lab.plan_execute.resolve_execute_workspace",
        lambda _permissions=None, _expected=None: (workspace, {}),
    )
    monkeypatch.setattr(
        "agent_lab.agents.cursor_agent.respond",
        lambda **_kwargs: "created RECIPE.md",
    )

    plan_md = (session / "plan.md").read_text(encoding="utf-8")
    _seed_approved_plan_snapshot(session, plan_md)
    execution = run_dry_run(session, action_index=1, permissions={})
    assert execution["status"] == "pending_approval"
    assert execution["workspace_label"] or execution.get("workspace_root")

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


def test_maybe_auto_scribe_rescribes_when_plan_exists(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "topic.txt").write_text("topic\n", encoding="utf-8")
    (folder / "chat.jsonl").write_text('{"role":"user","content":"hi"}\n', encoding="utf-8")
    (folder / "plan.md").write_text("## existing plan\n", encoding="utf-8")
    _write_pending_consensus(folder, excerpt="topic")
    with patch(
        "agent_lab.room.synthesize_session_plan",
        return_value=(SAMPLE_PLAN, "합의 반영"),
    ) as mock_synth:
        result = maybe_auto_scribe_after_consensus(
            folder,
            consensus_meta={"status": "reached", "anchor": {"excerpt": "topic"}},
            synthesize=True,
            cancelled=False,
        )
    mock_synth.assert_called_once_with(
        folder,
        on_event=None,
        permissions=None,
        trigger="consensus_reached",
        previous_plan_md="## existing plan\n",
    )
    assert result == SAMPLE_PLAN


def test_maybe_auto_scribe_idempotent_when_already_synced(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "plan.md").write_text("## synced plan\n", encoding="utf-8")
    from agent_lab.run_meta import write_run_meta

    write_run_meta(
        folder,
        {
            "consensus_agreements": [
                {
                    "id": "agr-1",
                    "excerpt": "topic",
                    "status": "reached",
                    "plan_synced": True,
                    "message_count": 1,
                }
            ],
        },
    )
    with patch("agent_lab.room.synthesize_session_plan") as mock_synth:
        result = maybe_auto_scribe_after_consensus(
            folder,
            consensus_meta={"status": "reached", "anchor": {"excerpt": "topic"}},
            synthesize=True,
            cancelled=False,
        )
    mock_synth.assert_not_called()
    assert result == "## synced plan\n"


def test_maybe_auto_scribe_on_consensus_reached(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    _write_pending_consensus(folder)
    with patch(
        "agent_lab.room.synthesize_session_plan",
        return_value=(SAMPLE_PLAN, "합의된 점 반영"),
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
        previous_plan_md="",
    )


def test_maybe_auto_scribe_emits_dry_run_proposal(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    _write_pending_consensus(folder, excerpt="parser 섹션")
    events: list[tuple[str, dict]] = []

    def on_event(event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    def _fake_synth(session_folder, **kwargs):
        (session_folder / "plan.md").write_text(NEW_FORMAT_PLAN, encoding="utf-8")
        return NEW_FORMAT_PLAN, "합의 반영"

    with patch(
        "agent_lab.room.synthesize_session_plan",
        side_effect=_fake_synth,
    ):
        result = maybe_auto_scribe_after_consensus(
            folder,
            consensus_meta={"status": "reached", "excerpt": "parser 섹션"},
            synthesize=False,
            cancelled=False,
            on_event=on_event,
        )

    assert result == NEW_FORMAT_PLAN
    event_types = [name for name, _ in events]
    assert "consensus_plan_synced" in event_types
    assert "consensus_dry_run_proposal" in event_types

    _, proposal = next(
        (item for item in events if item[0] == "consensus_dry_run_proposal"),
    )
    assert proposal["has_executable"] is True
    assert proposal["action_key"] == "now:1"
    assert proposal["recommended"]["what"].startswith("plan parser")


def test_consensus_auto_scribe_harvests_inbox(tmp_path: Path, monkeypatch) -> None:
    from agent_lab.run_meta import read_run_meta

    folder = tmp_path / "sess-consensus-harvest"
    folder.mkdir()
    (folder / "run.json").write_text("{}\n", encoding="utf-8")
    (folder / "topic.txt").write_text("Build parser\n", encoding="utf-8")
    _write_pending_consensus(folder, excerpt="parser")
    monkeypatch.setattr(
        "agent_lab.room.synthesize_session_plan",
        lambda *_a, **_k: (NEW_FORMAT_PLAN, "합의 반영"),
    )
    result = maybe_auto_scribe_after_consensus(
        folder,
        consensus_meta={"status": "reached", "anchor": {"excerpt": "parser"}},
        synthesize=False,
        cancelled=False,
    )
    assert result == NEW_FORMAT_PLAN
    run = read_run_meta(folder)
    builds = [i for i in run.get("human_inbox", []) if i.get("kind") == "build"]
    assert len(builds) == 1
    assert builds[0]["action_ref"] == "now:1"


def test_ensure_consensus_plan_sync_backfill(tmp_path: Path, monkeypatch) -> None:
    from agent_lab.room import ensure_consensus_plan_sync
    from agent_lab.run_meta import read_run_meta, write_run_meta

    folder = tmp_path / "sess-backfill"
    folder.mkdir()
    (folder / "topic.txt").write_text("topic\n", encoding="utf-8")
    (folder / "chat.jsonl").write_text(
        "\n".join(f'{{"role":"user","content":"m{i}"}}' for i in range(3)) + "\n",
        encoding="utf-8",
    )
    write_run_meta(
        folder,
        {
            "consensus_agreements": [
                {
                    "id": "agr-1",
                    "excerpt": "스윕 추가",
                    "status": "reached",
                    "plan_synced": False,
                    "message_count": 3,
                }
            ],
        },
    )
    monkeypatch.setattr(
        "agent_lab.room.synthesize_session_plan",
        lambda *_a, **_k: (NEW_FORMAT_PLAN, "합의 반영"),
    )
    assert ensure_consensus_plan_sync(folder) is True
    run = read_run_meta(folder)
    assert run["consensus_agreements"][0]["plan_synced"] is True
    assert ensure_consensus_plan_sync(folder) is False


def test_maybe_auto_scribe_materializes_returned_plan_for_proposal(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    _write_pending_consensus(folder, excerpt="parser 섹션")
    events: list[tuple[str, dict]] = []

    def on_event(event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    with patch(
        "agent_lab.room.synthesize_session_plan",
        return_value=(NEW_FORMAT_PLAN, "합의 반영"),
    ):
        maybe_auto_scribe_after_consensus(
            folder,
            consensus_meta={"status": "reached", "excerpt": "parser 섹션"},
            synthesize=False,
            cancelled=False,
            on_event=on_event,
        )

    assert (folder / "plan.md").read_text(encoding="utf-8") == NEW_FORMAT_PLAN
    _, proposal = next(
        (item for item in events if item[0] == "consensus_dry_run_proposal"),
    )
    assert proposal["has_executable"] is True
    assert proposal["action_key"] == "now:1"


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


def test_list_plan_actions_includes_execute_workspace(tmp_path: Path, monkeypatch):
    agent_lab = tmp_path / "agent-lab"
    agent_lab.mkdir()
    lecture = tmp_path / "lecture-book"
    lecture.mkdir()
    (lecture / "extract_lecturenote.py").write_text("# x\n", encoding="utf-8")

    monkeypatch.setenv("AGENT_LAB_ROOT", str(agent_lab))
    monkeypatch.setenv("LECTURE_SCRIPT_ROOT", str(lecture))

    session = tmp_path / "sess"
    session.mkdir()
    (session / "plan.md").write_text(
        """## 지금 실행
1.
   - 무엇을: lecturenote 추출
   - 어디서: `extract_lecturenote.py`
   - 검증: 스크립트 실행
""",
        encoding="utf-8",
    )

    result = list_plan_actions(session)
    ws = result["recommended"]["execute_workspace"]
    assert ws["label"] == "lecture-script"
    assert "extract_lecturenote.py" in ws["paths_found"]


def test_dry_run_failure_restores_snapshot(tmp_path: Path, monkeypatch):
    disable_execute_inbox_mcp(monkeypatch)
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
        "agent_lab.plan_execute.resolve_execute_workspace",
        lambda _permissions=None, _expected=None: (workspace, {}),
    )

    plan_md = (session / "plan.md").read_text(encoding="utf-8")
    _seed_approved_plan_snapshot(session, plan_md)
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
    create_snapshot(
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
                        "workspace_root": str(workspace),
                        "expected_paths": ["target.txt"],
                        "snapshot_paths": ["target.txt"],
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
        "agent_lab.plan_execute.resolve_execute_workspace",
        lambda _permissions=None, _expected=None: (workspace, {}),
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


def test_resolve_execution_apply_isolation_records_verify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.mission_loop import enable_mission_loop
    from agent_lab.run_meta import patch_run_meta, read_run_meta
    from agent_lab.trust_budget import set_trust_budget

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session = tmp_path / "sess-apply-verify"
    session.mkdir()
    exec_id = "exec-apply-1"
    enable_mission_loop(session, start_autonomous=False)
    set_trust_budget(session, {"auto_merge_remaining": 1})

    def _merge_review(run: dict) -> dict:
        run["executions"] = [
            {
                "id": exec_id,
                "status": "pending_approval",
                "action_index": 1,
                "isolation_effective": "apply",
                "expected_paths": ["src/app.py"],
                "action_verify": "make test",
            }
        ]
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "enabled": True,
                "phase": "MERGE_REVIEW",
                "current_action_index": 1,
                "pending_action_indices": [1],
                "last_execution_id": exec_id,
            }
        )
        return run

    patch_run_meta(session, _merge_review)
    monkeypatch.setattr(
        "agent_lab.plan_execute.resolve_execute_workspace",
        lambda _permissions=None, _expected=None: (workspace, {}),
    )
    monkeypatch.setattr(
        "agent_lab.plan_execute.verify_after_merge",
        lambda *a, **k: {
            "status": "passed",
            "oracle": {"verdict": "pass", "detail": "mock ok"},
        },
    )

    result = resolve_execution(
        session,
        execution_id=exec_id,
        vote="approve",
        permissions={},
        approved_by="auto",
    )
    execution = result["execution"]
    assert execution["status"] == "completed"
    assert execution["oracle"]["verdict"] == "pass"
    assert execution.get("verify_after_merge") is not None
    run = read_run_meta(session)
    assert run["mission_loop"]["phase"] == "MISSION_DONE"
