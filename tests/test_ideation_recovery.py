"""RI-13 — recovery and honesty about incomplete state.

Three properties across the whole idea-lane path:
  1. resume loses no decision
  2. incomplete work is never presented as ready
  3. zero unintended execution anywhere along it
"""

from __future__ import annotations

import subprocess

import pytest

from agent_lab import ideation
from agent_lab.ideation_export import export_markdown
from agent_lab.room.messages import ChatMessage
from agent_lab.room.turn_flow_support import emit_divergence_options, record_ideation_options
from agent_lab.run.meta import read_run_meta, write_run_meta
from agent_lab.run.state import RunState

WELL_FORMED = """- **제목:** 하루 한 줄 회고
- **핵심 원리:** 매일 밤 알림 하나
- **사용 장면:** 자기 전 한 줄
- **차이:** 길게 못 쓴다
- **tradeoff:** 깊은 기록 불가
- **첫 실험:** 종이로 2주
"""


@pytest.fixture()
def no_subprocess(monkeypatch):
    calls: list[object] = []

    def _boom(*args, **kwargs):
        calls.append(args)
        raise AssertionError(f"unexpected subprocess call: {args!r}")

    for name in ("run", "check_output", "check_call", "Popen", "call"):
        monkeypatch.setattr(subprocess, name, _boom)
    return calls


def _run() -> RunState:
    run = RunState.from_memory({"topic": "하루를 정리하는 뭔가", "agents": ["cursor", "codex", "claude"]})
    ideation.start_ideation(run, ideation.new_ideation(original_concept="하루를 정리하는 뭔가"))
    return run


def _replies(*pairs: tuple[str, str]) -> list[ChatMessage]:
    return [ChatMessage(role="assistant", agent=a, content=t) for a, t in pairs]


def _reload(tmp_path, run) -> RunState:
    """A refresh is a fresh read straight off disk."""
    write_run_meta(tmp_path, dict(run))
    return read_run_meta(tmp_path)


# --- resume loses nothing -------------------------------------------------


def test_a_selection_survives_a_reload(tmp_path, no_subprocess):
    run = _run()
    record_ideation_options(run, _replies(("cursor", WELL_FORMED), ("codex", "다른 접근")))
    ideation.mutate_ideation(run, ideation.reject_option("opt-0-codex", reason="안 맞음"))
    ideation.mutate_ideation(run, ideation.select_option("opt-0-cursor", reason="가장 작다"))

    state = ideation.read_ideation(_reload(tmp_path, run))
    assert state["selection"]["option_id"] == "opt-0-cursor"
    assert state["selection"]["reason"] == "가장 작다"
    assert ideation.rejected_option_ids(state) == ["opt-0-codex"]
    assert state["options"][0]["principle"] == "매일 밤 알림 하나"


def test_a_cancelled_turn_records_nothing_and_leaves_state_resumable(tmp_path, no_subprocess):
    """A cancelled turn must not half-write a batch."""
    run = _run()
    record_ideation_options(run, _replies(("cursor", WELL_FORMED)))
    ideation.mutate_ideation(run, ideation.select_option("opt-0-cursor", reason="이유"))
    before = ideation.read_ideation(run)

    emit_divergence_options(run, _replies(("codex", "취소된 턴의 후보")), lambda *a: None, True)

    after = ideation.read_ideation(_reload(tmp_path, run))
    assert after == before
    assert after["selection"]["option_id"] == "opt-0-cursor"


def test_one_provider_failing_keeps_the_others_candidates(tmp_path, no_subprocess):
    run = _run()
    stored = record_ideation_options(
        run,
        _replies(
            ("cursor", WELL_FORMED),
            ("codex", "[codex error] provider is down"),
            ("claude", "세 번째 접근"),
        ),
    )

    assert [o["id"] for o in stored] == ["opt-0-cursor", "opt-0-codex", "opt-0-claude"]
    state = ideation.read_ideation(_reload(tmp_path, run))
    assert len(state["options"]) == 3
    # the failure is preserved as text, not silently dropped
    assert "error" in state["options"][1]["raw"]


def test_a_condition_change_survives_a_reload(tmp_path, no_subprocess):
    run = _run()
    record_ideation_options(run, _replies(("cursor", WELL_FORMED)))
    ideation.mutate_ideation(run, ideation.select_option("opt-0-cursor"))
    ideation.mutate_ideation(
        run, ideation.change_condition(constraints=["iPhone에서만"], reason="웹은 안 열더라")
    )

    state = ideation.read_ideation(_reload(tmp_path, run))
    changes = ideation.condition_changes(state)
    assert changes[0]["changed"]["constraints"]["added"] == ["iPhone에서만"]
    assert changes[0]["reason"] == "웹은 안 열더라"


def test_a_stale_write_after_a_reload_is_refused_not_applied(tmp_path, no_subprocess):
    run = _run()
    record_ideation_options(run, _replies(("cursor", WELL_FORMED), ("codex", "B안")))
    reloaded = _reload(tmp_path, run)
    revision = ideation.read_ideation(reloaded)["revision"]

    ideation.mutate_ideation(reloaded, ideation.select_option("opt-0-cursor"))

    with pytest.raises(ideation.IdeationStaleError):
        ideation.mutate_ideation(
            reloaded, ideation.select_option("opt-0-codex"), expected_revision=revision
        )
    assert ideation.read_ideation(reloaded)["selection"]["option_id"] == "opt-0-cursor"


# --- incomplete is never shown as ready -----------------------------------


def test_an_unparsed_candidate_is_not_synthesis_ready(no_subprocess):
    from agent_lab.room.context.ideation_quality import option_is_synthesis_ready

    run = _run()
    stored = record_ideation_options(run, _replies(("cursor", "형식을 안 지킨 자유 응답")))
    assert option_is_synthesis_ready(stored[0]) is False
    assert stored[0]["parse_error"]


def test_a_session_with_no_plan_does_not_export_as_ready(no_subprocess):
    run = _run()
    record_ideation_options(run, _replies(("cursor", WELL_FORMED)))
    ideation.mutate_ideation(run, ideation.select_option("opt-0-cursor"))

    md = export_markdown(run, plan_md="")
    assert "아직 계획이 작성되지 않았습니다" in md
    assert "계획 미작성" in md
    assert ideation.plan_input(run)["plan_source_revision"] is None


def test_a_concept_change_marks_the_existing_plan_stale_after_a_reload(tmp_path, no_subprocess):
    run = _run()
    record_ideation_options(run, _replies(("cursor", WELL_FORMED)))
    ideation.mutate_ideation(run, ideation.select_option("opt-0-cursor"))
    ideation.stamp_plan_source(run, "# Plan\n")
    assert ideation.plan_input(_reload(tmp_path, run))["plan_stale"] is False

    ideation.mutate_ideation(run, ideation.change_condition(constraints=["iPhone에서만"]))
    reloaded = _reload(tmp_path, run)

    assert ideation.plan_input(reloaded)["plan_stale"] is True
    assert "계획이 최신 구상보다 오래됐습니다" in export_markdown(reloaded, plan_md="# Plan\n")


def test_an_unselected_session_exports_as_conditional(no_subprocess):
    run = _run()
    record_ideation_options(run, _replies(("cursor", WELL_FORMED), ("codex", "B안")))
    md = export_markdown(run, plan_md="# Plan\n")
    assert "조건부 계획" in md


# --- zero unintended execution across the path ----------------------------


def test_the_whole_path_starts_no_execution(tmp_path, no_subprocess):
    """Explore → select → shape → plan → export, then assert nothing ran."""
    from agent_lab.plan.workflow import PlanWorkflowNotApproved, ensure_plan_workflow_approved

    folder = tmp_path / "journey"
    folder.mkdir()
    (folder / "topic.txt").write_text("하루를 정리하는 뭔가\n", encoding="utf-8")

    run = _run()
    record_ideation_options(run, _replies(("cursor", WELL_FORMED), ("codex", "B안")))
    ideation.mutate_ideation(run, ideation.reject_option("opt-0-codex", reason="안 맞음"))
    ideation.mutate_ideation(run, ideation.select_option("opt-0-cursor", reason="가장 작다"))
    ideation.mutate_ideation(run, ideation.change_condition(constraints=["2주 안에"]))
    ideation.mutate_ideation(run, ideation.set_concept({"mvp": "알림 + 한 줄"}))
    ideation.mutate_ideation(run, ideation.enter_plan_stage())
    ideation.stamp_plan_source(run, "# Plan\n")
    write_run_meta(folder, dict(run))

    export_markdown(read_run_meta(folder), plan_md="# Plan\n")

    final = read_run_meta(folder)
    assert not final.get("executions")
    assert "mission_loop" not in final
    assert "goal_loop" not in final
    assert "verified_loop" not in final
    assert "plan_workflow" not in final
    with pytest.raises(PlanWorkflowNotApproved):
        ensure_plan_workflow_approved(folder)
    assert no_subprocess == []


def test_a_full_room_turn_on_the_idea_lane_starts_no_execution(tmp_path, monkeypatch):
    """The real turn entry point, not just the state helpers."""
    from agent_lab.room import continue_room_round

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    folder = tmp_path / "turn"
    folder.mkdir()
    (folder / "topic.txt").write_text("하루를 정리하는 뭔가\n", encoding="utf-8")
    write_run_meta(folder, dict(_run()))

    continue_room_round(folder, "하루를 정리하는 뭔가", agents=["cursor", "codex"], parallel_rounds=1)

    run = read_run_meta(folder)
    assert not run.get("executions")
    assert "mission_loop" not in run
    assert not (folder / "plan.md").exists()
    state = ideation.read_ideation(run)
    assert state is not None
    assert state["stage"] == ideation.STAGE_EXPLORE


# --- existing sessions ----------------------------------------------------


def test_an_existing_session_is_untouched_by_any_of_this(tmp_path, no_subprocess):
    legacy = {
        "topic": "실행할 작업",
        "plan_workflow": {"enabled": True, "phase": "APPROVED"},
        "executions": [{"id": "e1", "status": "pending_approval"}],
    }
    write_run_meta(tmp_path, dict(legacy))
    run = read_run_meta(tmp_path)

    assert ideation.read_ideation(run) is None
    assert ideation.plan_input(run) is None
    assert ideation.shaping_context(run) is None
    assert ideation.stamp_plan_source(run, "# Plan\n") is None
    assert record_ideation_options(run, _replies(("cursor", WELL_FORMED))) is None
    assert read_run_meta(tmp_path) == legacy
