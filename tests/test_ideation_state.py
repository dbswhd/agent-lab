"""RI-02 — `run.json.ideation` state, revision locking, and preservation."""

from __future__ import annotations

import pytest

from agent_lab import ideation
from agent_lab.run.meta import patch_run_meta, read_run_meta, write_run_meta
from agent_lab.run.state import RunState, RuntimeValidationError, validate_run_data
from agent_lab.session.guidance import preserve_session_meta_from_prev


def _options() -> list[dict[str, str]]:
    return [
        {"id": "opt-a", "title": "A", "principle": "p-a", "difference": "d-a"},
        {"id": "opt-b", "title": "B", "principle": "p-b", "difference": "d-b"},
        {"id": "opt-c", "title": "C", "principle": "p-c", "difference": "d-c"},
    ]


def _session(**brief) -> RunState:
    run = RunState.from_memory({"topic": "막연한 개념"})
    ideation.start_ideation(run, ideation.new_ideation(**brief))
    return run


# --- shape / stage -------------------------------------------------------


def test_new_session_starts_in_explore_at_revision_zero():
    run = _session(original_concept="뭔가 만들고 싶다")
    state = ideation.read_ideation(run)
    assert state["schema_version"] == ideation.SCHEMA_VERSION
    assert state["stage"] == ideation.STAGE_EXPLORE
    assert state["revision"] == 0
    assert state["selection"] is None
    assert state["brief"]["original_concept"] == "뭔가 만들고 싶다"


def test_selection_moves_to_shape_and_bumps_revision():
    run = _session()
    ideation.mutate_ideation(run, ideation.set_options(_options()))
    state = ideation.mutate_ideation(run, ideation.select_option("opt-b", reason="제약에 맞음"))

    assert state["stage"] == ideation.STAGE_SHAPE
    assert state["revision"] == 2
    assert state["selection"]["option_id"] == "opt-b"
    assert state["selection"]["reason"] == "제약에 맞음"
    assert state["selection"]["source_revision"] == 1
    assert ideation.selected_option(state)["title"] == "B"


def test_combine_keeps_parent_links_and_new_id():
    run = _session()
    ideation.mutate_ideation(run, ideation.set_options(_options()))
    state = ideation.mutate_ideation(
        run, ideation.combine_options(["opt-a", "opt-c"], new_id="opt-ac", reason="둘을 합침")
    )

    assert state["selection"]["option_id"] == "opt-ac"
    assert state["selection"]["parent_ids"] == ["opt-a", "opt-c"]
    assert state["stage"] == ideation.STAGE_SHAPE


def test_combine_rejects_unknown_parent_and_duplicate_id():
    run = _session()
    ideation.mutate_ideation(run, ideation.set_options(_options()))
    with pytest.raises(ideation.IdeationError):
        ideation.mutate_ideation(run, ideation.combine_options(["opt-z"], new_id="opt-x"))
    with pytest.raises(ideation.IdeationError):
        ideation.mutate_ideation(run, ideation.combine_options(["opt-a"], new_id="opt-b"))


def test_failed_mutation_leaves_state_and_revision_untouched():
    run = _session()
    ideation.mutate_ideation(run, ideation.set_options(_options()))
    before = ideation.read_ideation(run)
    with pytest.raises(ideation.IdeationError):
        ideation.mutate_ideation(run, ideation.select_option("opt-missing"))
    assert ideation.read_ideation(run) == before


# --- round trip: select → reject → reopen → select ------------------------


def test_decisions_survive_returning_to_explore():
    run = _session()
    ideation.mutate_ideation(run, ideation.set_options(_options()))
    ideation.mutate_ideation(run, ideation.select_option("opt-a", reason="처음 선택"))
    ideation.mutate_ideation(run, ideation.reject_option("opt-c", reason="플랫폼이 안 맞음"))
    state = ideation.mutate_ideation(run, ideation.back_to_explore(reason="다른 방향도 보고 싶다"))

    assert state["stage"] == ideation.STAGE_EXPLORE
    assert state["selection"] is None
    assert ideation.rejected_option_ids(state) == ["opt-c"]
    kinds = [d["kind"] for d in state["decisions"]]
    assert kinds == ["select", "reject", "reopen"]
    assert all("reason" in d for d in state["decisions"])

    state = ideation.mutate_ideation(run, ideation.select_option("opt-b", reason="다시 고름"))
    assert state["selection"]["option_id"] == "opt-b"
    # the earlier rejection is still on the record
    assert ideation.rejected_option_ids(state) == ["opt-c"]


def test_option_id_is_stable_across_reordering():
    run = _session()
    ideation.mutate_ideation(run, ideation.set_options(_options()))
    ideation.mutate_ideation(run, ideation.select_option("opt-b"))
    reordered = list(reversed(_options()))
    state = ideation.mutate_ideation(run, ideation.set_options(reordered))

    assert [o["id"] for o in state["options"]] == ["opt-c", "opt-b", "opt-a"]
    assert state["selection"]["option_id"] == "opt-b"
    assert ideation.selected_option(state)["title"] == "B"


def test_options_require_explicit_ids():
    run = _session()
    with pytest.raises(ideation.IdeationError):
        ideation.mutate_ideation(run, ideation.set_options([{"title": "index 기반 후보"}]))


def test_parse_failure_keeps_raw_text():
    run = _session()
    state = ideation.mutate_ideation(
        run,
        ideation.set_options([{"id": "opt-a", "raw": "형식이 깨진 원문", "parse_error": "no sections"}]),
    )
    assert state["options"][0]["raw"] == "형식이 깨진 원문"
    assert state["options"][0]["parse_error"] == "no sections"


# --- optimistic locking --------------------------------------------------


def test_stale_expected_revision_is_rejected():
    run = _session()
    ideation.mutate_ideation(run, ideation.set_options(_options()), expected_revision=0)
    before = ideation.read_ideation(run)

    with pytest.raises(ideation.IdeationStaleError) as excinfo:
        ideation.mutate_ideation(run, ideation.select_option("opt-a"), expected_revision=0)

    assert excinfo.value.expected == 0
    assert excinfo.value.actual == 1
    assert ideation.read_ideation(run) == before

    state = ideation.mutate_ideation(run, ideation.select_option("opt-a"), expected_revision=1)
    assert state["revision"] == 2


def test_plan_source_goes_stale_when_the_concept_changes():
    run = _session()
    ideation.mutate_ideation(run, ideation.set_options(_options()))
    ideation.mutate_ideation(run, ideation.select_option("opt-a"))
    ideation.mutate_ideation(run, ideation.enter_plan_stage())
    state = ideation.mutate_ideation(run, ideation.record_plan_source(source_hash="abc123"))

    assert state["plan_source_revision"] == state["revision"]
    assert state["plan_source_hash"] == "abc123"
    assert ideation.plan_is_stale(state) is False

    state = ideation.mutate_ideation(run, ideation.set_concept({"mvp": "바뀐 범위"}))
    assert ideation.plan_is_stale(state) is True


# --- persistence ---------------------------------------------------------


def test_state_round_trips_through_run_json(tmp_path):
    run = _session(original_concept="개념")
    ideation.mutate_ideation(run, ideation.set_options(_options()))
    ideation.mutate_ideation(run, ideation.select_option("opt-b", reason="이유"))
    write_run_meta(tmp_path, dict(run))

    reloaded = read_run_meta(tmp_path)
    state = ideation.read_ideation(reloaded)
    assert state["selection"]["option_id"] == "opt-b"
    assert state["revision"] == 2
    assert [o["id"] for o in state["options"]] == ["opt-a", "opt-b", "opt-c"]


def test_patch_run_meta_preserves_ideation(tmp_path):
    run = _session()
    ideation.mutate_ideation(run, ideation.set_options(_options()))
    ideation.mutate_ideation(run, ideation.select_option("opt-c"))
    write_run_meta(tmp_path, dict(run))

    def _unrelated(current):
        current["topic"] = "다른 주제"
        return current

    updated = patch_run_meta(tmp_path, _unrelated)
    assert ideation.read_ideation(updated)["selection"]["option_id"] == "opt-c"


def test_turn_end_rebuild_preserves_ideation():
    prev = _session()
    ideation.mutate_ideation(prev, ideation.set_options(_options()))
    ideation.mutate_ideation(prev, ideation.select_option("opt-a", reason="선택"))

    fresh = RunState.from_memory({"topic": "막연한 개념"})
    preserve_session_meta_from_prev(fresh, dict(prev))

    state = ideation.read_ideation(fresh)
    assert state is not None
    assert state["selection"]["option_id"] == "opt-a"
    assert state["revision"] == 2


def test_invalid_ideation_is_rejected_on_write():
    with pytest.raises(RuntimeValidationError):
        validate_run_data({"ideation": {"schema_version": 1, "revision": 0, "stage": "executing"}})
    with pytest.raises(RuntimeValidationError):
        validate_run_data(
            {
                "ideation": {
                    "schema_version": 1,
                    "revision": 0,
                    "stage": "explore",
                    "brief": {},
                    "options": [{"id": "dup"}, {"id": "dup"}],
                    "decisions": [],
                }
            }
        )


def test_unsupported_schema_version_is_rejected():
    with pytest.raises(RuntimeValidationError):
        validate_run_data({"ideation": {"schema_version": 99, "revision": 0, "stage": "explore"}})


# --- existing sessions ---------------------------------------------------


def test_session_without_ideation_is_untouched(tmp_path):
    legacy = {"topic": "기존 세션", "executions": [], "plan_workflow": {"phase": "DISCUSS"}}
    validate_run_data(legacy)
    write_run_meta(tmp_path, dict(legacy))

    reloaded = read_run_meta(tmp_path)
    assert "ideation" not in reloaded
    assert ideation.read_ideation(reloaded) is None
    assert ideation.is_ideation_session(reloaded) is False

    fresh = RunState.from_memory({"topic": "기존 세션"})
    preserve_session_meta_from_prev(fresh, legacy)
    assert "ideation" not in fresh


def test_mutating_a_non_ideation_session_raises():
    run = RunState.from_memory({"topic": "기존 세션"})
    with pytest.raises(ideation.IdeationError):
        ideation.mutate_ideation(run, ideation.back_to_explore())
