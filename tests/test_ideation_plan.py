"""RI-10 — a plan tied to the concept it was written from."""

from __future__ import annotations

import pytest

from agent_lab import ideation
from agent_lab.agents.prompts import IDEATION_SCRIBE_ADDENDUM, ROOM_SCRIBE, room_scribe_prompt
from agent_lab.room.plan_scribe import build_ideation_plan_input_block
from agent_lab.run.state import RunState

OPTIONS = [
    {
        "id": "opt-0-cursor",
        "title": "하루 한 줄 회고",
        "principle": "매일 밤 알림 하나, 한 줄만 받는다",
        "usage": "자기 전 알림 → 한 줄 입력",
        "difference": "길게 쓸 수 없다",
        "tradeoff": "깊은 기록은 못 남긴다",
        "first_experiment": "종이로 2주",
    },
    {"id": "opt-0-claude", "title": "음성 메모", "principle": "말로 남긴다"},
]


def _run(*, select: bool = True, **brief) -> RunState:
    run = RunState.from_memory({"topic": "하루를 정리하는 뭔가"})
    ideation.start_ideation(run, ideation.new_ideation(original_concept="하루를 정리하는 뭔가", **brief))
    ideation.mutate_ideation(run, ideation.set_options(OPTIONS))
    ideation.mutate_ideation(run, ideation.reject_option("opt-0-claude", reason="소리내기 싫다"))
    if select:
        ideation.mutate_ideation(run, ideation.select_option("opt-0-cursor", reason="가장 작다"))
    return run


def _legacy() -> RunState:
    return RunState.from_memory({"topic": "실행할 작업"})


# --- scribe prompt -------------------------------------------------------


def test_idea_lane_gets_the_export_addendum():
    prompt = room_scribe_prompt(dict(_run()))
    assert prompt.startswith(ROOM_SCRIBE)
    assert IDEATION_SCRIBE_ADDENDUM in prompt


def test_existing_sessions_keep_their_scribe_prompt():
    assert room_scribe_prompt(dict(_legacy())) == ROOM_SCRIBE
    assert room_scribe_prompt(None) == ROOM_SCRIBE

    trading = {"topic": "t", "session_template": "trading-mission"}
    assert IDEATION_SCRIBE_ADDENDUM not in room_scribe_prompt(trading)
    assert "trading-mission.md" in room_scribe_prompt(trading)


def test_the_addendum_asks_for_the_section_4_4_content():
    for heading in (
        "## 만들려는 것",
        "## 사용자 시나리오",
        "## MVP 범위 / 비범위",
        "## 위험 가정과 최소 실험",
        "## 첫 작업 지시문",
    ):
        assert heading in IDEATION_SCRIBE_ADDENDUM


def test_the_addendum_separates_fact_from_proposal():
    for marker in ("사실:", "제안:", "미확인:"):
        assert marker in IDEATION_SCRIBE_ADDENDUM
    assert "사실처럼 쓰지 않는다" in IDEATION_SCRIBE_ADDENDUM


def test_the_addendum_grants_no_execution():
    assert "실행되지 않는다" in IDEATION_SCRIBE_ADDENDUM
    assert "자동 실행 권한" in IDEATION_SCRIBE_ADDENDUM
    assert "merge 승인 권한은 포함하지 않는다" in IDEATION_SCRIBE_ADDENDUM


def test_the_base_scribe_still_requires_scope_deps_and_verification():
    """작업별 범위·의존성·검증 — already the writer's contract; pin it."""
    assert "무엇을:" in ROOM_SCRIBE
    assert "어디서:" in ROOM_SCRIBE
    assert "검증:" in ROOM_SCRIBE
    assert "## 실행 순서 (이후)" in ROOM_SCRIBE


# --- decision record input ----------------------------------------------


def test_block_is_empty_for_an_existing_session():
    assert build_ideation_plan_input_block(_legacy()) == ""
    assert build_ideation_plan_input_block(None) == ""


def test_block_carries_the_reason_and_the_rejections():
    block = build_ideation_plan_input_block(_run())
    assert "가장 작다" in block
    assert "음성 메모" in block
    assert "소리내기 싫다" in block
    assert "계획에 되살리지 마세요" in block


def test_block_marks_a_plan_with_no_selection_as_conditional():
    block = build_ideation_plan_input_block(_run(select=False))
    assert "선택된 구상 없음" in block
    assert "조건부" in block


def test_block_does_not_claim_conditional_when_a_choice_exists():
    assert "선택된 구상 없음" not in build_ideation_plan_input_block(_run())


def test_block_labels_assumptions_as_not_facts():
    run = _run(constraints=["2주 안에"], assumptions=["사용자는 알림을 켠다"], open_questions=["혼자 쓰나?"])
    block = build_ideation_plan_input_block(run)
    assert "제약: 2주 안에" in block
    assert "가정 (사실 아님): 사용자는 알림을 켠다" in block
    assert "미결 질문: 혼자 쓰나?" in block


def test_block_carries_a_changed_condition_including_what_was_dropped():
    run = _run(constraints=["웹에서 쓴다"])
    ideation.mutate_ideation(run, ideation.change_condition(constraints=["iPhone에서만"], reason="웹은 안 열더라"))
    block = build_ideation_plan_input_block(run)
    assert "constraints 추가: iPhone에서만" in block
    assert "constraints 해제: 웹에서 쓴다" in block
    assert "더 이상 적용되지 않습니다" in block


def test_block_carries_the_shaped_concept():
    run = _run()
    ideation.mutate_ideation(run, ideation.set_concept({"mvp": "알림 + 한 줄 입력", "non_mvp": "공유 기능"}))
    block = build_ideation_plan_input_block(run)
    assert "알림 + 한 줄 입력" in block
    assert "공유 기능" in block


def test_block_states_the_revision_it_reflects():
    run = _run()
    revision = ideation.read_ideation(run)["revision"]
    assert f"구상 revision: {revision}" in build_ideation_plan_input_block(run)


# --- source linkage / staleness -----------------------------------------


def test_a_written_plan_is_linked_to_the_revision_it_reflected():
    run = _run()
    state = ideation.stamp_plan_source(run, "# Plan\n\n## Goal\n무언가\n")

    assert state["plan_source_revision"] == state["revision"]
    assert state["plan_source_hash"]
    assert ideation.plan_is_stale(state) is False
    assert ideation.plan_input(run)["plan_stale"] is False


def test_changing_the_concept_makes_the_existing_plan_stale():
    run = _run()
    ideation.stamp_plan_source(run, "# Plan\n")
    assert ideation.plan_input(run)["plan_stale"] is False

    ideation.mutate_ideation(run, ideation.change_condition(constraints=["iPhone에서만"]))
    assert ideation.plan_input(run)["plan_stale"] is True

    ideation.stamp_plan_source(run, "# Plan v2\n")
    assert ideation.plan_input(run)["plan_stale"] is False


def test_a_different_plan_body_gets_a_different_hash():
    run = _run()
    first = ideation.stamp_plan_source(run, "# Plan A\n")["plan_source_hash"]
    second = ideation.stamp_plan_source(run, "# Plan B\n")["plan_source_hash"]
    assert first != second


def test_stamping_an_existing_session_does_nothing():
    run = _legacy()
    assert ideation.stamp_plan_source(run, "# Plan\n") is None
    assert "ideation" not in run


def test_a_scribe_turn_stamps_the_source(monkeypatch, tmp_path):
    """The stamp happens where the plan is actually synthesized."""
    from agent_lab.room import plan_scribe
    from agent_lab.room.messages import ChatMessage

    run = _run()
    plan_body = "# Plan\n\n## 지금 실행\n1.\n   - 무엇을: 한다\n   - 어디서: `x.py`\n   - 검증: 됨\n"
    monkeypatch.setattr("agent_lab.room.synthesize_plan", lambda *a, **k: plan_body, raising=False)

    result = plan_scribe._apply_scribe_after_turn(
        topic="하루를 정리하는 뭔가",
        messages=[ChatMessage(role="user", agent="you", content="계획 만들어줘")],
        run_meta=run,
        plan_before="",
        mode="discuss",
        scribe=True,
        user_plan_send=True,
        cancelled=False,
        on_event=None,
        session_folder=None,
    )

    assert result == plan_body
    state = ideation.read_ideation(run)
    assert state["plan_source_revision"] == state["revision"]
    assert state["plan_source_hash"]


def test_a_failed_scribe_turn_stamps_nothing(monkeypatch):
    from agent_lab.room import plan_scribe
    from agent_lab.room.messages import ChatMessage

    run = _run()

    def _boom(*a, **k):
        raise RuntimeError("scribe down")

    monkeypatch.setattr("agent_lab.room.synthesize_plan", _boom, raising=False)

    plan_scribe._apply_scribe_after_turn(
        topic="t",
        messages=[ChatMessage(role="user", agent="you", content="x")],
        run_meta=run,
        plan_before="",
        mode="discuss",
        scribe=True,
        user_plan_send=True,
        cancelled=False,
        on_event=None,
        session_folder=None,
    )

    state = ideation.read_ideation(run)
    assert state["plan_source_revision"] is None
    assert state["plan_source_hash"] is None


@pytest.mark.parametrize("stage", [ideation.STAGE_EXPLORE, ideation.STAGE_SHAPE])
def test_plan_input_is_available_at_every_stage(stage):
    """The Scribe only runs at `plan` stage (RI-03), but the record itself is
    stage-independent — a conditional plan can be asked for from anywhere."""
    run = _run(select=False)
    ideation.mutate_ideation(run, ideation.set_options(OPTIONS))
    data = ideation.plan_input(run)
    assert data is not None
    assert data["stage"] in (ideation.STAGE_EXPLORE, ideation.STAGE_SHAPE, ideation.STAGE_PLAN)
