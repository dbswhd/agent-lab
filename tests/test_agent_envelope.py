"""Speech-act envelope parsing and consensus classification."""

from __future__ import annotations

import pytest

from agent_lab.agent_envelope import (
    classify_consensus_reply,
    envelope_act,
    envelope_protocol_block,
    is_endorse_reply,
    parse_agent_response,
    parse_agent_response_v2,
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


def test_fallback_text_heuristics_without_envelope(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("AGENT_LAB_LEGACY_ENDORSE", "1")
    assert classify_consensus_reply("이의 없습니다") == "endorse"
    assert classify_consensus_reply("PASS") == "pass"
    assert (
        classify_consensus_reply("이의 없습니다\n[PROPOSED: x]") == "substantive"
    )


def test_endorse_envelope_with_proposed_body_is_substantive():
    raw = (
        '```agent-envelope\n'
        '{"act":"ENDORSE","refs":[],"confidence":0.9}\n'
        '```\n'
        "이의 없습니다\n[PROPOSED: follow-up item]"
    )
    parsed = parse_agent_response(raw)
    env = parsed.envelope.to_dict() if parsed.envelope else None
    assert classify_consensus_reply(parsed.body, env) == "substantive"
    assert not is_endorse_reply(parsed.body, env)


def test_no_fence_returns_full_body():
    parsed = parse_agent_response("plain reply")
    assert parsed.envelope is None
    assert parsed.body == "plain reply"
    assert not parsed.envelope_parse_error


def test_invalid_fence_strips_body_and_flags_error():
    raw = '```agent-envelope\nnot json\n```\n'
    parsed = parse_agent_response(raw)
    assert parsed.envelope is None
    assert parsed.envelope_parse_error
    assert parsed.body == raw.strip()


def test_invalid_fence_with_trailing_body():
    raw = '```agent-envelope\n{broken\n```\n짧은 동의'
    parsed = parse_agent_response(raw)
    assert parsed.envelope is None
    assert parsed.envelope_parse_error
    assert parsed.body == "짧은 동의"


def test_parse_agent_response_v2_structured_preferred():
    structured = {"act": "ENDORSE", "refs": ["L1"]}
    parsed = parse_agent_response_v2("본문", structured=structured)
    assert parsed.envelope is not None
    assert parsed.envelope.act == "ENDORSE"
    assert parsed.body == "본문"


def test_legacy_endorse_off_neutral_without_envelope(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("AGENT_LAB_LEGACY_ENDORSE", raising=False)
    assert classify_consensus_reply("이의 없습니다") == "neutral"


def test_legacy_endorse_default_off():
    assert classify_consensus_reply("이의 없습니다") == "neutral"
    assert (
        classify_consensus_reply(
            "이의 없습니다",
            {"act": "ENDORSE", "refs": []},
        )
        == "endorse"
    )


def test_envelope_protocol_block_includes_efficiency_and_discuss():
    block = envelope_protocol_block(context="discuss")
    assert "회의 · R2+ 순차" in block
    assert "ENDORSE" in block
    assert "PASS" in block
    assert "decision-fork" in block
    assert "refs" in block
