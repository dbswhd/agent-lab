"""Speech-act envelope parsing and consensus classification."""

from __future__ import annotations

from agent_lab.agent_envelope import (
    classify_consensus_reply,
    envelope_act,
    is_endorse_reply,
    parse_agent_response,
)


def test_parse_envelope_and_body():
    raw = (
        '```agent-envelope\n'
        '{"act":"ENDORSE","refs":["L12"],"confidence":0.95}\n'
        '```\n'
        "이의 없습니다"
    )
    parsed = parse_agent_response(raw)
    assert parsed.envelope is not None
    assert parsed.envelope.act == "ENDORSE"
    assert parsed.envelope.refs == ["L12"]
    assert parsed.body == "이의 없습니다"


def test_envelope_amend_overrides_no_objection_text():
    raw = (
        '```agent-envelope\n'
        '{"act":"AMEND","refs":[]}\n'
        '```\n'
        "이의 없습니다\n[PROPOSED: 보완]"
    )
    parsed = parse_agent_response(raw)
    assert envelope_act(parsed.envelope) == "AMEND"
    assert classify_consensus_reply(parsed.body, parsed.envelope.to_dict()) == "substantive"
    assert not is_endorse_reply(parsed.body, parsed.envelope.to_dict())


def test_fallback_text_heuristics_without_envelope():
    assert classify_consensus_reply("이의 없습니다") == "endorse"
    assert classify_consensus_reply("PASS") == "pass"
    assert (
        classify_consensus_reply("이의 없습니다\n[PROPOSED: x]") == "substantive"
    )


def test_no_fence_returns_full_body():
    parsed = parse_agent_response("plain reply")
    assert parsed.envelope is None
    assert parsed.body == "plain reply"
