"""Unit tests for pure / near-pure helpers in room_context.py."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

import agent_lab.room_context as rc


@dataclass
class _Msg:
    role: str
    content: str
    agent: str | None = None
    parallel_round: int | None = None


# ---------------------------------------------------------------------------
# is_pass_response
# ---------------------------------------------------------------------------


def test_is_pass_response_exact():
    assert rc.is_pass_response("PASS") is True


def test_is_pass_response_lowercase():
    assert rc.is_pass_response("pass") is True


def test_is_pass_response_leading_whitespace():
    assert rc.is_pass_response("  PASS") is True


def test_is_pass_response_with_trailing_content_after_newline():
    # "PASS\nextra" — first LINE is PASS → True
    assert rc.is_pass_response("PASS\nsome extra") is True


def test_is_pass_response_inline_extra_fails():
    # First line has more than just PASS → False
    assert rc.is_pass_response("PASS some words") is False


def test_is_pass_response_empty():
    assert rc.is_pass_response("") is False
    assert rc.is_pass_response("   ") is False


def test_is_pass_response_other_text():
    assert rc.is_pass_response("이의 없습니다") is False


# ---------------------------------------------------------------------------
# is_pure_no_objection / is_no_objection_response
# ---------------------------------------------------------------------------


def test_is_pure_no_objection_bare():
    assert rc.is_pure_no_objection("이의 없습니다") is True


def test_is_pure_no_objection_with_short_parenthetical():
    assert rc.is_pure_no_objection("이의 없습니다\n(구현은 다음 단계에서)") is True


def test_is_pure_no_objection_with_long_parenthetical():
    long_note = "(" + "x" * 81 + ")"
    assert rc.is_pure_no_objection(f"이의 없습니다\n{long_note}") is False


def test_is_pure_no_objection_with_amendment():
    assert rc.is_pure_no_objection("이의 없습니다\n하지만 다음 사항을 수정해야 합니다") is False


def test_is_pure_no_objection_empty():
    assert rc.is_pure_no_objection("") is False


def test_is_no_objection_response_delegates():
    assert rc.is_no_objection_response("이의 없습니다") is True
    assert rc.is_no_objection_response("다른 내용") is False


# ---------------------------------------------------------------------------
# _split_plan_sections
# ---------------------------------------------------------------------------


def test_split_plan_sections_empty():
    assert rc._split_plan_sections("") == {}


def test_split_plan_sections_single():
    md = "## 합의\n- 항목 A\n- 항목 B\n"
    sections = rc._split_plan_sections(md)
    assert "합의" in sections
    assert "항목 A" in sections["합의"]


def test_split_plan_sections_multiple():
    md = "## 합의\n- A\n## 미결\n- B\n"
    sections = rc._split_plan_sections(md)
    assert "합의" in sections
    assert "미결" in sections
    assert "A" in sections["합의"]
    assert "B" in sections["미결"]


def test_split_plan_sections_keys_are_lowercase():
    md = "## Agreed Items\n- x\n"
    sections = rc._split_plan_sections(md)
    assert "agreed items" in sections


# ---------------------------------------------------------------------------
# _section_body
# ---------------------------------------------------------------------------


def test_section_body_found_by_prefix():
    sections = {"합의된 항목": "body text"}
    result = rc._section_body(sections, ("합의",))
    assert result == "body text"


def test_section_body_not_found():
    sections = {"합의된 항목": "body text"}
    result = rc._section_body(sections, ("미결",))
    assert result == ""


def test_section_body_substring_match():
    sections = {"open discussion items": "open body"}
    result = rc._section_body(sections, ("open",))
    assert result == "open body"


# ---------------------------------------------------------------------------
# count_messages / current_turn_message_count
# ---------------------------------------------------------------------------


def test_count_messages():
    msgs = [_Msg("user", "hi"), _Msg("agent", "hello", agent="claude")]
    assert rc.count_messages(msgs) == 2


def test_current_turn_message_count_single_turn():
    msgs = [
        _Msg("user", "q"),
        _Msg("agent", "a1", agent="claude"),
        _Msg("agent", "a2", agent="cursor"),
    ]
    assert rc.current_turn_message_count(msgs) == 3


def test_current_turn_message_count_multi_turn():
    msgs = [
        _Msg("user", "q1"),
        _Msg("agent", "a1", agent="claude"),
        _Msg("user", "q2"),
        _Msg("agent", "a2", agent="claude"),
    ]
    # last user is at index 2 → count from index 2 = 2 messages
    assert rc.current_turn_message_count(msgs) == 2


def test_current_turn_message_count_no_user():
    msgs = [_Msg("agent", "only agent")]
    # no user → all messages count
    assert rc.current_turn_message_count(msgs) == 1


# ---------------------------------------------------------------------------
# compact_current_turn_pins
# ---------------------------------------------------------------------------


def test_compact_current_turn_pins_empty():
    kept, dropped = rc.compact_current_turn_pins([], max_chars=1000)
    assert kept == []
    assert dropped == 0


def test_compact_current_turn_pins_dedupes_per_agent():
    msgs = [
        _Msg("user", "q"),
        _Msg("agent", "first reply", agent="claude"),
        _Msg("agent", "second reply", agent="claude"),  # same agent
    ]
    kept, dropped = rc.compact_current_turn_pins(msgs, max_chars=10000)
    # user + latest reply per agent → 2 messages
    assert len(kept) == 2
    assert dropped == 1
    assert kept[0].role == "user"
    assert kept[1].content == "second reply"


def test_compact_current_turn_pins_char_cap_drops_agents():
    msgs = [
        _Msg("user", "q"),
        _Msg("agent", "a" * 100, agent="claude"),
        _Msg("agent", "b" * 100, agent="cursor"),
    ]
    kept, dropped = rc.compact_current_turn_pins(msgs, max_chars=200)
    # char cap forces agent drops; human must survive
    assert kept[0].role == "user"
    assert dropped >= 1


def test_compact_current_turn_pins_no_user():
    msgs = [_Msg("agent", "x", agent="claude")]
    kept, dropped = rc.compact_current_turn_pins(msgs, max_chars=1000)
    assert kept == msgs
    assert dropped == 0


# ---------------------------------------------------------------------------
# extract_status_tags
# ---------------------------------------------------------------------------


def test_extract_status_tags_empty():
    assert rc.extract_status_tags([]) == []


def test_extract_status_tags_finds_proposed():
    msgs = [_Msg("agent", "[PROPOSED: 새로운 구조 도입]", agent="claude")]
    tags = rc.extract_status_tags(msgs, max_items=10)
    assert any("PROPOSED" in t for t in tags)


def test_extract_status_tags_deduplicates():
    line = "[PROPOSED: 중복 항목]"
    msgs = [
        _Msg("agent", line, agent="claude"),
        _Msg("agent", line, agent="cursor"),
    ]
    tags = rc.extract_status_tags(msgs, max_items=10)
    assert len([t for t in tags if "중복" in t]) == 1


def test_extract_status_tags_respects_max_items():
    content = "\n".join(f"[PROPOSED: item {i}]" for i in range(20))
    msgs = [_Msg("agent", content, agent="claude")]
    tags = rc.extract_status_tags(msgs, max_items=3)
    assert len(tags) == 3


# ---------------------------------------------------------------------------
# trim_messages_by_chars
# ---------------------------------------------------------------------------


def test_trim_messages_by_chars_under_budget():
    msgs = [_Msg("user", "short")]
    kept, omitted = rc.trim_messages_by_chars(msgs, max_chars=10000)
    assert kept == msgs
    assert omitted == 0


def test_trim_messages_by_chars_over_budget_drops_oldest():
    msgs = [
        _Msg("user", "old " * 100),
        _Msg("agent", "new", agent="claude"),
    ]
    # Budget just enough for last message
    kept, omitted = rc.trim_messages_by_chars(msgs, max_chars=200)
    assert omitted >= 1
    assert kept[-1].content == "new"


def test_trim_messages_by_chars_empty():
    kept, omitted = rc.trim_messages_by_chars([], max_chars=1000)
    assert kept == []
    assert omitted == 0


# ---------------------------------------------------------------------------
# _split_human_turns / recent_messages_by_turns
# ---------------------------------------------------------------------------


def test_split_human_turns_single():
    msgs = [_Msg("user", "q"), _Msg("agent", "a", agent="claude")]
    turns = rc._split_human_turns(msgs)
    assert len(turns) == 1
    assert len(turns[0]) == 2


def test_split_human_turns_multiple():
    msgs = [
        _Msg("user", "q1"),
        _Msg("agent", "a1", agent="claude"),
        _Msg("user", "q2"),
        _Msg("agent", "a2", agent="claude"),
    ]
    turns = rc._split_human_turns(msgs)
    assert len(turns) == 2


def test_recent_messages_by_turns_within_limit():
    msgs = [_Msg("user", "q"), _Msg("agent", "a", agent="claude")]
    kept, omitted = rc.recent_messages_by_turns(msgs, max_turns=5)
    assert kept == msgs
    assert omitted == 0


def test_recent_messages_by_turns_trims_oldest():
    msgs = []
    for i in range(5):
        msgs.append(_Msg("user", f"q{i}"))
        msgs.append(_Msg("agent", f"a{i}", agent="claude"))
    kept, omitted = rc.recent_messages_by_turns(msgs, max_turns=2)
    assert omitted == 3
    # Only last 2 turns remain
    assert kept[0].content == "q3"


def test_recent_messages_by_turns_empty():
    kept, omitted = rc.recent_messages_by_turns([], max_turns=3)
    assert kept == []
    assert omitted == 0


# ---------------------------------------------------------------------------
# plan_stale_banner
# ---------------------------------------------------------------------------


def test_plan_stale_banner_none_run_meta():
    assert rc.plan_stale_banner(None) is None


def test_plan_stale_banner_no_agreements():
    assert rc.plan_stale_banner({}) is None
    assert rc.plan_stale_banner({"consensus_agreements": []}) is None


def test_plan_stale_banner_with_pending(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(rc, "pending_consensus_agreements", lambda _: [{"excerpt": "some topic"}])
    run_meta = {"consensus_agreements": [{"excerpt": "some topic", "synced": False}]}
    banner = rc.plan_stale_banner(run_meta)
    assert banner is not None
    assert isinstance(banner, str)
    assert len(banner) > 0
