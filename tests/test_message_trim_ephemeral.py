"""Tests for ephemeral system message capping (synthesis + peer digest)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from agent_lab.room.context.message_trim import (
    cap_ephemeral_system_messages,
    format_thread_numbered_slice,
    prepare_recent_messages,
)
from agent_lab.room.team_orchestration import _SYNTHESIS_MARKER


@dataclass
class _Msg:
    role: str
    agent: str | None
    content: str
    visibility: str | None = None
    parallel_round: int | None = None


def _peer_digest(n: int) -> _Msg:
    return _Msg(
        "system",
        None,
        f"[peer digest — internal coordination snapshot]\n\nturn {n}",
        visibility="peer",
    )


def _synthesis(n: int) -> _Msg:
    return _Msg(
        "system",
        None,
        f"{_SYNTHESIS_MARKER}\n\nsummary {n}",
        visibility="human",
    )


def test_cap_ephemeral_keeps_last_three_peer_digests():
    messages = [_peer_digest(i) for i in range(6)]
    capped = cap_ephemeral_system_messages(messages, max_keep=3)
    assert len(capped) == 3
    assert capped == messages[-3:]


def test_cap_ephemeral_keeps_last_three_synthesis():
    messages = [_synthesis(i) for i in range(5)]
    capped = cap_ephemeral_system_messages(messages, max_keep=3)
    assert len(capped) == 3
    assert capped == messages[-3:]


def test_cap_ephemeral_preserves_non_ephemeral_system_messages():
    keep = _Msg("system", None, "[plan 미결]\nopen item")
    messages = [_peer_digest(1), keep, _peer_digest(2), _peer_digest(3), _peer_digest(4)]
    capped = cap_ephemeral_system_messages(messages, max_keep=2)
    assert keep in capped
    assert capped.count(keep) == 1
    assert len([m for m in capped if "peer digest" in m.content.lower()]) == 2


def test_cap_ephemeral_object_identity_for_l_refs():
    messages = [_Msg("user", None, "q1"), _synthesis(1), _Msg("user", None, "q2"), _synthesis(2)]
    full = list(messages)
    capped = cap_ephemeral_system_messages(messages, max_keep=1)
    assert capped[-1] is full[-1]
    numbered, first_l, last_l = format_thread_numbered_slice(full, capped)
    assert first_l == 1
    assert last_l == 4
    assert "L1 Human" in numbered
    assert "L3 Human" in numbered
    assert "L4 System" in numbered
    assert "L2 System" not in numbered


def test_prepare_recent_messages_caps_ephemeral_after_turn_split():
    messages: list[_Msg] = []
    for turn in range(10):
        messages.append(_Msg("user", None, f"question {turn}"))
        messages.append(_Msg("agent", "claude", f"answer {turn}", 1))
        messages.append(_peer_digest(turn))
        messages.append(_synthesis(turn))
    trimmed, _, _, _ = prepare_recent_messages(messages, max_turns=10, max_chars=500_000)
    digests = [m for m in trimmed if "peer digest" in (m.content or "").lower()]
    synths = [m for m in trimmed if (m.content or "").startswith(_SYNTHESIS_MARKER)]
    assert len(digests) <= 3
    assert len(synths) <= 3
    assert digests == [_peer_digest(i) for i in range(7, 10)]
    assert synths == [_synthesis(i) for i in range(7, 10)]


def test_cap_respects_env_max_keep(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_EPHEMERAL_SYSTEM_MAX_KEEP", "1")
    messages = [_peer_digest(i) for i in range(4)]
    capped = cap_ephemeral_system_messages(messages)
    assert len(capped) == 1
    assert capped[0] is messages[-1]
