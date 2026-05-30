"""Consensus (자유 토론) phrase detection and anchor picking."""

from __future__ import annotations

from dataclasses import dataclass

from agent_lab.room_consensus import (
    NO_OBJECTION_LINE,
    is_substantive_reply,
    pick_anchor,
)
from agent_lab.room_context import is_no_objection_response, is_pass_response


@dataclass
class _Msg:
    role: str
    agent: str | None
    content: str
    parallel_round: int | None = None


def test_no_objection_first_line_only():
    assert is_no_objection_response("이의 없습니다")
    assert is_no_objection_response("이의 없습니다\n(부연 설명)")
    assert not is_no_objection_response("동의합니다. 이의 없습니다")
    assert not is_no_objection_response("PASS")
    assert not is_no_objection_response(
        "이의 없습니다\n다만 한 가지 추가 리스크 — strip 전에 샘플 확인"
    )
    assert not is_no_objection_response(
        "이의 없습니다\n[PROPOSED: 보완 계획 요약]\n- 단계 1"
    )


def test_substantive_vs_pass_and_no_objection():
    assert not is_substantive_reply("PASS")
    assert not is_substantive_reply(NO_OBJECTION_LINE)
    assert is_substantive_reply("다음은 A부터 검증하자.")
    assert is_substantive_reply(
        "이의 없습니다\n[PROPOSED: 보완 계획]\n- 육안 확인 후 strip"
    )


def test_pick_anchor_latest_substantive():
    msgs = [
        _Msg("user", None, "q"),
        _Msg("agent", "claude", "제안 A", 1),
        _Msg("agent", "codex", "PASS", 1),
        _Msg("agent", "cursor", "제안 B가 더 낫다", 1),
    ]
    anchor = pick_anchor(msgs, ["claude", "codex", "cursor"])
    assert anchor is not None
    assert anchor.agent == "cursor"
    assert "제안 B" in anchor.excerpt
