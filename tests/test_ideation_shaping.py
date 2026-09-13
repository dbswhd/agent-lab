"""RI-09 — shaping a chosen direction from recorded decisions, not inference."""

from __future__ import annotations

import pytest

from agent_lab import ideation
from agent_lab.agents.prompts import IDEATION_SHAPE_INSTRUCTION
from agent_lab.room.messages import build_ideation_shaping_block
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
    {"id": "opt-0-codex", "title": "자동 수집 타임라인", "principle": "기록을 모아 재구성"},
    {"id": "opt-0-claude", "title": "음성 메모", "principle": "말로 남긴다"},
]


def _session(stage: str = ideation.STAGE_EXPLORE) -> RunState:
    run = RunState.from_memory({"topic": "하루를 정리하는 뭔가"})
    payload = ideation.new_ideation(original_concept="하루를 정리하는 뭔가")
    payload["stage"] = stage
    ideation.start_ideation(run, payload)
    ideation.mutate_ideation(run, ideation.set_options(OPTIONS))
    return run


def _shaped() -> RunState:
    run = _session()
    ideation.mutate_ideation(run, ideation.reject_option("opt-0-claude", reason="말하기 싫은 시간대다"))
    ideation.mutate_ideation(run, ideation.select_option("opt-0-cursor", reason="가장 작게 시작된다"))
    return run


# --- context data --------------------------------------------------------


def test_shaping_context_is_absent_outside_the_shape_stage():
    assert ideation.shaping_context(_session()) is None
    assert ideation.shaping_context(RunState.from_memory({"topic": "기존 세션"})) is None
    assert ideation.shaping_context(None) is None

    run = _shaped()
    ideation.mutate_ideation(run, ideation.enter_plan_stage())
    assert ideation.shaping_context(run) is None


def test_shaping_context_carries_the_choice_and_its_reason():
    ctx = ideation.shaping_context(_shaped())
    assert ctx is not None
    assert ctx["selection"]["option_id"] == "opt-0-cursor"
    assert ctx["selection"]["reason"] == "가장 작게 시작된다"
    assert ctx["selected_option"]["principle"] == "매일 밤 알림 하나, 한 줄만 받는다"


def test_rejections_travel_with_their_reasons():
    ctx = ideation.shaping_context(_shaped())
    assert ctx["rejected"] == [
        {"id": "opt-0-claude", "title": "음성 메모", "reason": "말하기 싫은 시간대다"}
    ]


def test_a_later_rejection_reason_replaces_the_earlier_one():
    run = _shaped()
    ideation.mutate_ideation(run, ideation.back_to_explore())
    ideation.mutate_ideation(run, ideation.reject_option("opt-0-claude", reason="더 정확한 이유"))
    ideation.mutate_ideation(run, ideation.select_option("opt-0-cursor"))

    rejected = ideation.shaping_context(run)["rejected"]
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "더 정확한 이유"


def test_combined_selection_carries_its_parents():
    run = _session()
    ideation.mutate_ideation(
        run,
        ideation.combine_options(["opt-0-cursor", "opt-0-codex"], new_id="opt-ac", reason="둘을 합침"),
    )
    ctx = ideation.shaping_context(run)
    assert ctx["selection"]["parent_ids"] == ["opt-0-cursor", "opt-0-codex"]
    assert [o["id"] for o in ctx["parent_options"]] == ["opt-0-cursor", "opt-0-codex"]


# --- changed conditions --------------------------------------------------


def test_a_changed_condition_is_recorded_with_its_reason():
    run = _shaped()
    state = ideation.mutate_ideation(
        run,
        ideation.change_condition(
            constraints=["iOS만", "2주 안에"], reason="웹은 안 쓰게 됐다"
        ),
    )

    changes = ideation.condition_changes(state)
    assert len(changes) == 1
    assert changes[0]["changed"]["constraints"]["added"] == ["iOS만", "2주 안에"]
    assert changes[0]["reason"] == "웹은 안 쓰게 됐다"
    assert ideation.shaping_context(run)["constraints"] == ["iOS만", "2주 안에"]


def test_only_newly_added_conditions_are_flagged_as_changed():
    run = _shaped()
    ideation.mutate_ideation(run, ideation.change_condition(constraints=["2주 안에"]))
    state = ideation.mutate_ideation(
        run, ideation.change_condition(constraints=["2주 안에", "iOS만"], reason="플랫폼 변경")
    )

    changes = ideation.condition_changes(state)
    assert [c["changed"]["constraints"]["added"] for c in changes] == [["2주 안에"], ["iOS만"]]


def test_a_dropped_condition_is_reported_as_released():
    """"실은 웹이 아니라 iPhone" is a removal — a seat that only sees the
    addition keeps designing for the web."""
    run = _shaped()
    ideation.mutate_ideation(run, ideation.change_condition(constraints=["웹에서 쓴다"]))
    state = ideation.mutate_ideation(
        run, ideation.change_condition(constraints=["iPhone에서만"], reason="웹은 안 열게 되더라")
    )

    delta = ideation.condition_changes(state)[-1]["changed"]["constraints"]
    assert delta["added"] == ["iPhone에서만"]
    assert delta["removed"] == ["웹에서 쓴다"]
    assert ideation.shaping_context(run)["constraints"] == ["iPhone에서만"]

    block = build_ideation_shaping_block(run)
    assert "constraints 해제: 웹에서 쓴다" in block
    assert "더 이상 적용되지 않습니다" in block


def test_an_unchanged_condition_records_nothing():
    run = _shaped()
    before = ideation.read_ideation(run)
    ideation.mutate_ideation(run, ideation.change_condition(constraints=[]))
    after = ideation.read_ideation(run)

    assert ideation.condition_changes(after) == []
    assert after["brief"] == before["brief"]


def test_set_brief_still_overwrites_quietly():
    """`change_condition` is additive over `set_brief`, not a replacement."""
    run = _shaped()
    state = ideation.mutate_ideation(run, ideation.set_brief(constraints=["조용히 바뀐 조건"]))
    assert state["brief"]["constraints"] == ["조용히 바뀐 조건"]
    assert ideation.condition_changes(state) == []


# --- rendered block ------------------------------------------------------


def test_block_is_empty_outside_shaping():
    assert build_ideation_shaping_block(_session()) == ""
    assert build_ideation_shaping_block(RunState.from_memory({"topic": "기존 세션"})) == ""
    assert build_ideation_shaping_block(None) == ""


def test_block_states_the_choice_the_reasons_and_the_rejections():
    block = build_ideation_shaping_block(_shaped())

    assert "하루 한 줄 회고" in block
    assert "가장 작게 시작된다" in block
    assert "매일 밤 알림 하나" in block
    assert "음성 메모" in block
    assert "말하기 싫은 시간대다" in block
    assert "새 근거 없이 다시 제안하지 마세요" in block
    assert "대화 요약이 아니라 기록된 결정" in block


def test_block_puts_a_changed_condition_above_earlier_answers():
    run = _shaped()
    ideation.mutate_ideation(
        run, ideation.change_condition(constraints=["iOS만"], reason="웹은 안 쓰게 됐다")
    )
    block = build_ideation_shaping_block(run)

    assert "바꾼 조건" in block
    assert "이전 답변보다 우선" in block
    assert "constraints 추가: iOS만" in block
    assert "웹은 안 쓰게 됐다" in block


def test_block_says_so_when_nothing_is_selected_yet():
    run = _session(ideation.STAGE_SHAPE)
    block = build_ideation_shaping_block(run)
    assert "아직 없음" in block
    assert "임의로 정하지 마세요" in block


def test_a_rejection_with_no_recorded_reason_is_marked_not_invented():
    run = _session()
    ideation.mutate_ideation(run, ideation.reject_option("opt-0-claude"))
    ideation.mutate_ideation(run, ideation.select_option("opt-0-cursor"))

    assert "(이유 미기록)" in build_ideation_shaping_block(run)


# --- prompt --------------------------------------------------------------


def test_shape_instruction_separates_fact_proposal_and_unverified():
    for marker in ("사실:", "제안:", "미확인:"):
        assert marker in IDEATION_SHAPE_INSTRUCTION
    assert "읽지 않은 경로" in IDEATION_SHAPE_INSTRUCTION
    assert "기각한 후보" in IDEATION_SHAPE_INSTRUCTION
    assert "새 대안을 늘리지 말고" in IDEATION_SHAPE_INSTRUCTION


# --- payload -------------------------------------------------------------


@pytest.mark.parametrize("stage", [ideation.STAGE_EXPLORE, ideation.STAGE_PLAN])
def test_payload_carries_the_block_only_while_shaping(tmp_path, stage):
    from agent_lab.room.parallel_rounds import preview_agent_payload
    from agent_lab.run.meta import write_run_meta

    run = _shaped()
    if stage != ideation.STAGE_SHAPE:
        ideation.mutate_ideation(
            run,
            ideation.back_to_explore() if stage == ideation.STAGE_EXPLORE else ideation.enter_plan_stage(),
        )
    folder = tmp_path / f"sess-{stage}"
    folder.mkdir()
    (folder / "topic.txt").write_text("하루를 정리하는 뭔가\n", encoding="utf-8")
    write_run_meta(folder, dict(run))

    text, _ = preview_agent_payload(folder, "cursor", agents=["cursor"], parallel_round=1)
    assert "[구상 구체화 입력" not in text


def test_shaping_payload_carries_the_decisions(tmp_path):
    from agent_lab.room.parallel_rounds import preview_agent_payload
    from agent_lab.run.meta import write_run_meta

    run = _shaped()
    ideation.mutate_ideation(run, ideation.change_condition(constraints=["iOS만"], reason="플랫폼 변경"))
    folder = tmp_path / "sess-shape"
    folder.mkdir()
    (folder / "topic.txt").write_text("하루를 정리하는 뭔가\n", encoding="utf-8")
    write_run_meta(folder, dict(run))

    text, _ = preview_agent_payload(folder, "cursor", agents=["cursor"], parallel_round=1)
    assert "[구상 구체화 입력" in text
    assert "가장 작게 시작된다" in text
    assert "말하기 싫은 시간대다" in text
    assert "iOS만" in text
    assert "사실:" in text and "제안:" in text and "미확인:" in text


def test_existing_sessions_get_no_shaping_block(tmp_path):
    from agent_lab.room.parallel_rounds import preview_agent_payload
    from agent_lab.run.meta import write_run_meta

    folder = tmp_path / "sess-legacy"
    folder.mkdir()
    (folder / "topic.txt").write_text("실행할 작업\n", encoding="utf-8")
    write_run_meta(folder, {"topic": "실행할 작업"})

    text, _ = preview_agent_payload(folder, "cursor", agents=["cursor"], parallel_round=1)
    assert "[구상 구체화 입력" not in text
    assert "[구상 구체화]" not in text
