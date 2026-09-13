"""Actual HTTP commands and Room Scribe persistence, with only provider calls stubbed."""

from __future__ import annotations

import pytest

from test_ideation_api import client as client_fixture, _make_session
from agent_lab.run.meta import read_run_meta, write_run_meta

client = client_fixture


def test_http_selection_conditions_concept_plan_and_refresh(client, tmp_path, monkeypatch):
    folder = _make_session(tmp_path)
    url = f"/api/sessions/{folder.name}/ideation"

    def command(verb, **fields):
        revision = client.get(url).json()["revision"]
        res = client.patch(url, json={"command": verb, "expected_revision": revision, **fields})
        assert res.status_code == 200, res.text
        return res.json()

    command("select", option_id="opt-0-cursor")
    command("condition", constraints=["iOS 전용", "2주 안에"], reason="범위 축소")
    command("concept", concept={"summary": "마감 알림과 한 줄 복습", "mvp": "한 과목"})
    state = client.get(url).json()["ideation"]
    assert state["brief"]["constraints"] == ["iOS 전용", "2주 안에"]
    assert state["concept"]["mvp"] == "한 과목"
    assert state["decisions"][-1]["kind"] == "condition"


def test_plan_request_requires_quality_ready_option(client, tmp_path):
    folder = _make_session(tmp_path)
    url = f"/api/sessions/{folder.name}/ideation"
    response = client.patch(url, json={"command": "plan", "expected_revision": 0})
    assert response.status_code == 422
    assert "needs review" in response.text


def test_synthesize_only_marks_plan_source_and_ready(tmp_path, monkeypatch):
    from agent_lab import room
    from agent_lab.ideation import mutate_ideation, new_ideation, select_option, start_ideation
    from agent_lab.room.messages import ChatMessage
    from agent_lab.room.session_persist import persist_chat_checkpoint
    from agent_lab.room.turn_meta import synthesize_session_plan
    from agent_lab.run.state import RunState

    folder = tmp_path / "ready-plan"
    folder.mkdir()
    (folder / "topic.txt").write_text("학습 자료 도구\n", encoding="utf-8")
    run = RunState.from_memory({"topic": "학습 자료 도구"})
    payload = new_ideation(original_concept="학습 자료 도구")
    payload["options"] = [
        {
            "id": "opt-0-codex",
            "title": "근거형 자료",
            "principle": "출처를 보존한다",
            "usage": "시험 전",
            "difference": "근거가 있다",
            "tradeoff": "검토 시간이 든다",
            "first_experiment": "한 과목으로 검증",
            "quality": {"status": "ready"},
        }
    ]
    start_ideation(run, payload)
    mutate_ideation(run, select_option("opt-0-codex"))
    write_run_meta(folder, dict(run))
    persist_chat_checkpoint(
        folder,
        [ChatMessage(role="user", agent=None, content="학습 자료 도구")],
        topic="학습 자료 도구",
    )
    monkeypatch.setattr(room, "call_agent", lambda *args, **kwargs: "# 계획\n\n## 지금 실행\n1. 검증")
    synthesize_session_plan(folder)
    persisted = read_run_meta(folder)["ideation"]
    assert persisted["plan_status"] == "ready"
    assert persisted["plan_source_revision"] is not None
    assert (folder / "plan.md").is_file()


def test_synthesize_only_marks_failed_when_scribe_promotes_unverified_repo_claim(tmp_path, monkeypatch):
    from agent_lab import room
    from agent_lab.ideation import mutate_ideation, new_ideation, select_option, start_ideation
    from agent_lab.room.messages import ChatMessage
    from agent_lab.room.session_persist import persist_chat_checkpoint
    from agent_lab.room.turn_meta import synthesize_session_plan
    from agent_lab.run.state import RunState

    folder = tmp_path / "failed-plan"
    folder.mkdir()
    (folder / "topic.txt").write_text("학습 자료 도구\n", encoding="utf-8")
    run = RunState.from_memory({"topic": "학습 자료 도구"})
    payload = new_ideation(original_concept="학습 자료 도구")
    payload["options"] = [{
        "id": "opt-0-codex", "title": "근거형 자료", "principle": "출처를 보존한다",
        "usage": "시험 전", "difference": "근거가 있다", "tradeoff": "검토 시간이 든다",
        "first_experiment": "한 과목으로 검증", "quality": {"status": "ready"},
    }]
    start_ideation(run, payload)
    mutate_ideation(run, select_option("opt-0-codex"))
    write_run_meta(folder, dict(run))
    persist_chat_checkpoint(folder, [ChatMessage(role="user", agent=None, content="학습 자료 도구")], topic="학습 자료 도구")
    monkeypatch.setattr(room, "call_agent", lambda *args, **kwargs: "## 지금 실행\n- 어디서: 현재 레포 src/nonexistent.py에 구현됨")
    with pytest.raises(RuntimeError, match="unverified repository claims"):
        synthesize_session_plan(folder)
    assert read_run_meta(folder)["ideation"]["plan_status"] == "failed"


@pytest.mark.parametrize(
    "verb,fields",
    [
        ("condition", {"constraints": []}),
        ("concept", {"concept": {"summary": "수정"}}),
        ("plan", {}),
    ],
)
def test_new_commands_reject_stale_revision(client, tmp_path, verb, fields):
    folder = _make_session(tmp_path)
    res = client.patch(
        f"/api/sessions/{folder.name}/ideation",
        json={
            "command": verb,
            "expected_revision": 999,
            **fields,
        },
    )
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "stale_revision"
    assert read_run_meta(folder)["ideation"]["revision"] == 0
