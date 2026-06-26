"""Kimi Work push payload text extraction (fixture + live daimon shapes)."""

from __future__ import annotations

from agent_lab.kimi_work_push_payload import (
    assistant_reasoning_text,
    assistant_reply_text,
    push_message_parts,
    thinking_activity_delta,
    thinking_activity_line,
)


def test_push_message_parts_top_level() -> None:
    payload = {"parts": [{"kind": "text", "text": "a"}]}
    assert len(push_message_parts(payload)) == 1


def test_push_message_parts_nested_live() -> None:
    payload = {
        "conversationKey": "main:conversation:abc",
        "message": {
            "role": "assistant",
            "parts": [
                {"kind": "reasoning", "text": "think"},
                {"kind": "text", "text": "kimi-work-probe-ok"},
            ],
        },
    }
    assert len(push_message_parts(payload)) == 2
    assert assistant_reply_text(payload) == "kimi-work-probe-ok"


def test_assistant_reply_text_skips_reasoning() -> None:
    payload = {
        "message": {
            "parts": [
                {"kind": "reasoning", "text": "hidden"},
                {"kind": "text", "text": "visible"},
            ],
        },
    }
    assert assistant_reply_text(payload) == "visible"


def test_assistant_reply_text_fixture_top_level() -> None:
    assert assistant_reply_text({"text": "hello"}) == "hello"


def test_assistant_reply_text_ignores_top_level_when_parts_only_reasoning() -> None:
    payload = {
        "text": "추가 근거 수집: Cursor가 주장한",
        "message": {
            "parts": [
                {"kind": "reasoning", "text": "추가 근거 수집: Cursor가 주장한"},
            ],
        },
    }
    assert assistant_reply_text(payload) == ""


def test_assistant_reply_text_prefers_parts_over_top_level_reasoning() -> None:
    payload = {
        "text": "추가 근거 수집: internal chain-of-thought",
        "message": {
            "parts": [
                {"kind": "reasoning", "text": "think"},
                {"kind": "text", "text": "execute는 cursor|codex만"},
            ],
        },
    }
    assert assistant_reply_text(payload) == "execute는 cursor|codex만"


def test_assistant_reply_text_cot_snapshots_until_visible_text_part() -> None:
    reasoning_only = {
        "text": "추가",
        "message": {"parts": [{"kind": "reasoning", "text": "추가"}]},
    }
    with_text = {
        "text": "추가 근거 수집: still hidden",
        "message": {
            "parts": [
                {"kind": "reasoning", "text": "추가 근거 수집: still hidden"},
                {"kind": "text", "text": "최종 답변"},
            ],
        },
    }
    assert assistant_reply_text(reasoning_only) == ""
    assert assistant_reply_text(with_text) == "최종 답변"


def test_assistant_reasoning_text_from_parts_and_top_level() -> None:
    payload = {
        "text": "추가 근거 수집: Cursor가 주장한",
        "message": {"parts": [{"kind": "reasoning", "text": "추가 근거 수집: Cursor가 주장한"}]},
    }
    assert assistant_reasoning_text(payload) == "추가 근거 수집: Cursor가 주장한"
    assert assistant_reasoning_text(
        {
            "message": {
                "parts": [
                    {"kind": "reasoning", "text": "hidden"},
                    {"kind": "text", "text": "visible"},
                ],
            },
        },
    ) == ""


def test_thinking_activity_line_truncates_tail() -> None:
    long = "A" * 120
    line = thinking_activity_line(long, tail=20)
    assert line.startswith("[thinking] …")
    assert line.endswith("A" * 20)


def test_thinking_activity_delta_emits_suffix_only() -> None:
    prev = "사용자는 src"
    cumulative = "사용자는 src/agent_lab 또는 app/server"
    line = thinking_activity_delta(prev, cumulative, tail=40)
    assert line.startswith("[thinking]")
    assert "/agent_lab" in line
    assert "app/server" in line
