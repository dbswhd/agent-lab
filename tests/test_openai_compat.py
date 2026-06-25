"""Tests for OpenAI-compatible chat completions API (P2-7)."""

from __future__ import annotations

from app.server.routers.openai_compat import (
    _build_completion,
    _chunk,
    _extract_system,
    _extract_topic,
    _resolve_preset,
    _Message,
)


def test_extract_topic_last_user_message() -> None:
    msgs = [
        _Message(role="system", content="you are helpful"),
        _Message(role="user", content="first question"),
        _Message(role="assistant", content="answer"),
        _Message(role="user", content="follow up"),
    ]
    assert _extract_topic(msgs) == "follow up"


def test_extract_topic_single_user_message() -> None:
    msgs = [_Message(role="user", content="hello world")]
    assert _extract_topic(msgs) == "hello world"


def test_extract_topic_empty_messages() -> None:
    assert _extract_topic([]) == ""


def test_extract_topic_no_user_message_falls_back_to_last() -> None:
    msgs = [_Message(role="assistant", content="hey")]
    assert _extract_topic(msgs) == "hey"


def test_extract_system_present() -> None:
    msgs = [
        _Message(role="system", content="be concise"),
        _Message(role="user", content="q"),
    ]
    assert _extract_system(msgs) == "be concise"


def test_extract_system_absent() -> None:
    msgs = [_Message(role="user", content="q")]
    assert _extract_system(msgs) is None


def test_resolve_preset_gpt4_maps_to_consensus() -> None:
    assert _resolve_preset("gpt-4") == "consensus"


def test_resolve_preset_gpt4o_maps_to_consensus() -> None:
    assert _resolve_preset("gpt-4o") == "consensus"


def test_resolve_preset_gpt35_maps_to_fast() -> None:
    assert _resolve_preset("gpt-3.5-turbo") == "fast"


def test_resolve_preset_agent_lab_fast() -> None:
    assert _resolve_preset("agent-lab-fast") == "fast"


def test_resolve_preset_agent_lab_thorough() -> None:
    assert _resolve_preset("agent-lab-thorough") == "thorough"


def test_resolve_preset_unknown_defaults_to_consensus() -> None:
    assert _resolve_preset("unknown-model") == "consensus"


def test_build_completion_shape() -> None:
    result = _build_completion("cmpl-123", "agent-lab-balanced", "Hello there")
    assert result["id"] == "cmpl-123"
    assert result["object"] == "chat.completion"
    assert result["model"] == "agent-lab-balanced"
    assert len(result["choices"]) == 1
    assert result["choices"][0]["message"]["role"] == "assistant"
    assert result["choices"][0]["message"]["content"] == "Hello there"
    assert result["choices"][0]["finish_reason"] == "stop"


def test_build_completion_includes_session_id() -> None:
    result = _build_completion("cmpl-x", "m", "content", session_id="sess-abc")
    assert result["agentlab"]["session_id"] == "sess-abc"


def test_build_completion_no_session_id() -> None:
    result = _build_completion("cmpl-x", "m", "content")
    assert "agentlab" not in result


def test_chunk_format() -> None:
    out = _chunk("cmpl-x", "agent-lab-fast", "Hello")
    assert out.startswith("data: ")
    assert out.endswith("\n\n")
    import json
    payload = json.loads(out[6:])
    assert payload["object"] == "chat.completion.chunk"
    assert payload["choices"][0]["delta"]["content"] == "Hello"
    assert payload["choices"][0]["finish_reason"] is None


def test_chunk_finish() -> None:
    out = _chunk("cmpl-x", "m", "", finish=True)
    import json
    payload = json.loads(out[6:])
    assert payload["choices"][0]["finish_reason"] == "stop"
    assert payload["choices"][0]["delta"] == {}
