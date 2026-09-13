"""RI-06 — comparable, stably-identified idea options."""

from __future__ import annotations

import pytest

from agent_lab import ideation
from agent_lab.divergence import (
    MAX_DIVERGENCE_OPTIONS,
    format_divergence_options,
    option_id_for,
    parse_idea_option,
)
from agent_lab.room.messages import ChatMessage
from agent_lab.room.turn_flow_support import emit_divergence_options, record_ideation_options
from agent_lab.run.state import RunState

WELL_FORMED = """## 하루 한 줄 회고
- **제목:** 하루 한 줄 회고
- **핵심 원리:** 매일 밤 알림 하나, 한 줄만 받는다.
- **사용 장면:** 자기 전 알림 → 한 줄 입력 → 일요일에 지난 7줄을 본다.
- **차이:** 일기 앱과 달리 길게 쓸 수 없다. 입력 상한이 기능이다.
- **tradeoff:** 깊은 기록은 남기지 못한다.
- **첫 실험:** 종이와 알람만으로 2주 돌려본다.
"""


def _run(stage: str | None = ideation.STAGE_EXPLORE) -> RunState:
    run = RunState.from_memory({"topic": "막연한 개념", "agents": ["cursor", "codex", "claude"]})
    if stage is not None:
        payload = ideation.new_ideation(original_concept="막연한 개념")
        payload["stage"] = stage
        ideation.start_ideation(run, payload)
    return run


def _replies(*pairs: tuple[str, str]) -> list[ChatMessage]:
    return [ChatMessage(role="assistant", agent=agent, content=text) for agent, text in pairs]


# --- parsing -------------------------------------------------------------


def test_a_well_formed_candidate_parses_into_comparable_fields():
    option = parse_idea_option(WELL_FORMED, option_id="opt-0-claude", agent="claude")

    assert option["title"] == "하루 한 줄 회고"
    assert "알림 하나" in option["principle"]
    assert "일요일" in option["usage"]
    assert "일기 앱" in option["difference"]
    assert "깊은 기록" in option["tradeoff"]
    assert "2주" in option["first_experiment"]
    assert "parse_error" not in option


def test_multi_line_sections_stay_together():
    option = parse_idea_option(
        "- **핵심 원리:** 첫 줄\n  이어지는 설명\n- **차이:** 다르다\n",
        option_id="opt-0-codex",
    )
    assert option["principle"] == "첫 줄\n이어지는 설명"
    assert option["difference"] == "다르다"


def test_parse_failure_keeps_the_reply_and_says_so():
    """A candidate must never be silently dropped for bad formatting."""
    option = parse_idea_option("그냥 자유롭게 쓴 답변", option_id="opt-0-cursor", agent="cursor")

    assert option["raw"] == "그냥 자유롭게 쓴 답변"
    assert option["parse_error"] == "no_recognized_sections"
    assert option["title"] == "그냥 자유롭게 쓴 답변"


def test_empty_reply_is_marked_not_guessed():
    option = parse_idea_option("   ", option_id="opt-0-cursor")
    assert option["parse_error"] == "empty_reply"


# --- stable ids ----------------------------------------------------------


def test_ids_are_keyed_by_batch_and_agent_not_position():
    assert option_id_for("claude", batch=3, seat=0) == "opt-3-claude"
    assert option_id_for("claude", batch=3, seat=2) == "opt-3-claude"
    assert option_id_for("claude", batch=4, seat=0) != option_id_for("claude", batch=3, seat=0)
    assert option_id_for("", batch=3, seat=2) == "opt-3-seat2"


def test_a_selection_survives_reordering_the_options():
    run = _run()
    record_ideation_options(run, _replies(("cursor", "A안"), ("codex", "B안"), ("claude", "C안")))
    state = ideation.read_ideation(run)
    chosen = state["options"][1]["id"]
    ideation.mutate_ideation(run, ideation.select_option(chosen))

    reordered = list(reversed(state["options"]))
    state = ideation.mutate_ideation(run, ideation.set_options(reordered))

    assert state["selection"]["option_id"] == chosen
    assert ideation.selected_option(state)["agent"] == "codex"


def test_ids_survive_a_reconnect(tmp_path):
    from agent_lab.run.meta import read_run_meta, write_run_meta

    run = _run()
    record_ideation_options(run, _replies(("cursor", WELL_FORMED), ("codex", "B안")))
    ideation.mutate_ideation(run, ideation.select_option("opt-0-cursor"))
    write_run_meta(tmp_path, dict(run))

    state = ideation.read_ideation(read_run_meta(tmp_path))
    assert [o["id"] for o in state["options"]] == ["opt-0-cursor", "opt-0-codex"]
    assert state["selection"]["option_id"] == "opt-0-cursor"


# --- batch capture -------------------------------------------------------


def test_an_exploration_batch_is_stored_as_options():
    run = _run()
    stored = record_ideation_options(run, _replies(("cursor", WELL_FORMED), ("codex", "다른 접근")))

    assert stored is not None
    assert [o["id"] for o in stored] == ["opt-0-cursor", "opt-0-codex"]
    assert ideation.read_ideation(run)["options"] == stored
    assert ideation.read_ideation(run)["revision"] == 1


def test_empty_replies_do_not_create_an_empty_batch():
    run = _run()
    assert record_ideation_options(run, _replies(("cursor", "   "))) is None
    assert ideation.read_ideation(run)["revision"] == 0


def test_options_are_capped():
    run = _run()
    stored = record_ideation_options(
        run, _replies(*[(f"agent{i}", f"{i}번 안") for i in range(MAX_DIVERGENCE_OPTIONS + 3)])
    )
    assert len(stored) == MAX_DIVERGENCE_OPTIONS


@pytest.mark.parametrize("stage", [None, ideation.STAGE_SHAPE, ideation.STAGE_PLAN])
def test_only_exploration_captures_options(stage):
    run = _run(stage)
    assert record_ideation_options(run, _replies(("cursor", WELL_FORMED))) is None


def test_similar_candidates_are_not_scored_or_dropped():
    """Similarity is the user's judgement, not a correctness signal (§RI-06)."""
    run = _run()
    stored = record_ideation_options(run, _replies(("cursor", "같은 안"), ("codex", "같은 안")))
    assert len(stored) == 2
    assert all("similarity" not in o for o in stored)


# --- event compatibility -------------------------------------------------


def _events():
    seen: list[tuple[str, dict]] = []
    return seen, lambda typ, payload: seen.append((typ, payload))


def test_legacy_event_shape_is_preserved_for_old_consumers():
    run = _run()
    seen, on_event = _events()
    emit_divergence_options(run, _replies(("cursor", WELL_FORMED), ("codex", "B안")), on_event, False)

    assert len(seen) == 1
    typ, payload = seen[0]
    assert typ == "divergence_options"
    assert payload["options"] == format_divergence_options(_replies(("cursor", WELL_FORMED), ("codex", "B안")))
    assert [o["id"] for o in payload["idea_options"]] == ["opt-0-cursor", "opt-0-codex"]
    assert payload["revision"] == 1


def test_existing_divergence_sessions_are_unchanged():
    run = RunState.from_memory({"topic": "t", "turn_profile": "divergence"})
    seen, on_event = _events()
    emit_divergence_options(run, _replies(("cursor", "A"), ("codex", "B")), on_event, False)

    typ, payload = seen[0]
    assert typ == "divergence_options"
    assert payload["count"] == 2
    assert "idea_options" not in payload


def test_a_non_divergence_existing_session_still_emits_nothing():
    run = RunState.from_memory({"topic": "t", "turn_profile": "analyze"})
    seen, on_event = _events()
    emit_divergence_options(run, _replies(("cursor", "A")), on_event, False)
    assert seen == []


def test_a_cancelled_turn_stores_nothing():
    run = _run()
    seen, on_event = _events()
    emit_divergence_options(run, _replies(("cursor", WELL_FORMED)), on_event, True)

    assert seen == []
    assert ideation.read_ideation(run)["revision"] == 0


def test_room_turn_persists_idea_options_after_turn_end(tmp_path, monkeypatch):
    """The event and durable run.json state must agree after a real Room turn."""
    from agent_lab.room import parallel_rounds
    from agent_lab import room
    from agent_lab.run.meta import read_run_meta, write_run_meta

    monkeypatch.setenv("AGENT_LAB_OUTCOME_LEDGER", "0")
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_ADVISOR", "0")
    folder = tmp_path / "room-persist"
    folder.mkdir()
    (folder / "topic.txt").write_text("막연한 개념\n", encoding="utf-8")
    write_run_meta(folder, dict(_run()))

    def fake_invoke(agent, **kwargs):
        return ChatMessage(
            role="assistant",
            agent=str(agent),
            content=f"제목: {agent}안\n핵심 원리: {agent}의 작동 원리",
            parallel_round=kwargs.get("parallel_round"),
        )

    monkeypatch.setattr(parallel_rounds, "_invoke_agent_for_round", fake_invoke)
    monkeypatch.setattr(parallel_rounds, "_teammate_idle_peer_message", lambda *a, **k: None)
    events: list[tuple[str, dict]] = []

    room.continue_room_round(
        folder,
        "아이디어를 구체화해줘",
        agents=["cursor", "codex"],
        parallel_rounds=1,
        on_event=lambda name, payload: events.append((name, payload)),
    )

    persisted = ideation.read_ideation(read_run_meta(folder))
    assert persisted is not None
    assert persisted["revision"] == 1
    assert sorted(option["id"] for option in persisted["options"]) == ["opt-0-codex", "opt-0-cursor"]
    option_event = next(payload for name, payload in events if name == "divergence_options")
    assert option_event["revision"] == persisted["revision"]


def test_two_round_exploration_keeps_only_first_batch_as_candidates(tmp_path, monkeypatch):
    """Follow-up comparison rounds must not create duplicate candidate IDs."""
    from agent_lab.room import parallel_rounds
    from agent_lab import room
    from agent_lab.run.meta import read_run_meta, write_run_meta

    monkeypatch.setenv("AGENT_LAB_OUTCOME_LEDGER", "0")
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_ADVISOR", "0")
    folder = tmp_path / "room-two-rounds"
    folder.mkdir()
    (folder / "topic.txt").write_text("막연한 개념\n", encoding="utf-8")
    write_run_meta(folder, dict(_run()))

    def fake_invoke(agent, **kwargs):
        round_no = kwargs.get("parallel_round")
        return ChatMessage(
            role="assistant",
            agent=str(agent),
            content=f"제목: {agent}안 R{round_no}\n핵심 원리: 비교",
            parallel_round=round_no,
        )

    monkeypatch.setattr(parallel_rounds, "_invoke_agent_for_round", fake_invoke)
    monkeypatch.setattr(parallel_rounds, "_teammate_idle_peer_message", lambda *a, **k: None)

    room.continue_room_round(
        folder,
        "아이디어를 비교해줘",
        agents=["cursor", "codex"],
        parallel_rounds=2,
    )

    persisted = ideation.read_ideation(read_run_meta(folder))
    assert persisted is not None
    assert sorted(option["id"] for option in persisted["options"]) == ["opt-0-codex", "opt-0-cursor"]


def test_provider_failure_is_visible_but_not_a_selectable_option():
    run = _run()
    stored = record_ideation_options(
        run,
        [
            ChatMessage(role="system", agent="codex", content="[codex error] provider is down"),
            ChatMessage(role="assistant", agent="cursor", content="제목: 실제 후보\n핵심 원리: 실제 제안"),
        ],
    )

    assert stored is not None
    assert [option["agent"] for option in stored] == ["cursor"]
