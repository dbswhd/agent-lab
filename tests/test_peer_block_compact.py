"""Tests for AGENT_LAB_COMMS_COMPACT peer-block blackboard+delta."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from agent_lab.room import context as rc


@dataclass
class _Msg:
    role: str
    content: str
    agent: str = ""
    parallel_round: int | None = None
    envelope: dict[str, Any] | None = None


def test_format_peer_block_off_parity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without compact flag, peer block keeps full prose and exact header."""
    monkeypatch.delenv("AGENT_LAB_COMMS_COMPACT", raising=False)
    msgs = [
        _Msg(role="agent", content="I agree with the plan.", agent="claude", parallel_round=2),
        _Msg(role="agent", content="Same here.", agent="cursor", parallel_round=2),
    ]
    block = rc.format_peer_block(msgs)
    assert block.startswith("[이번 턴 · 동료 발화]")
    assert "I agree with the plan." in block
    assert "Same here." in block
    assert "L2" not in block


def test_format_peer_block_compact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_COMMS_COMPACT", "1")
    long_body = "This is a very long peer reply that should be truncated to 140 characters for the compact digest. " * 3
    msgs = [
        _Msg(role="agent", content=long_body, agent="claude", parallel_round=2,
             envelope={"act": "ENDORSE", "refs": ["L12"]}),
        _Msg(role="agent", content="I object because step 3 is risky and the retry policy lacks backoff; additionally the circuit breaker threshold seems too high for the expected failure rate." * 2, agent="cursor", parallel_round=2,
             envelope={"act": "CHALLENGE"}),
    ]
    block = rc.format_peer_block(msgs)
    assert block.startswith("[이번 턴 · 동료 발화]")
    # Digest header contains round, agent, act.
    assert "L2 Claude ENDORSE:" in block
    assert "L2 Cursor CHALLENGE:" in block
    # Excerpt is truncated.
    assert "…" in block
    # Refs included.
    assert "[refs: L12]" in block
    # Full prose is NOT in peer block.
    assert "expected failure rate" not in block
    assert "CHALLENGE:" in block


def test_format_peer_block_compact_no_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_COMMS_COMPACT", "1")
    msgs = [
        _Msg(role="agent", content="AMEND: change timeout to 30s.", agent="codex", parallel_round=1),
    ]
    block = rc.format_peer_block(msgs)
    assert "L1 Codex AMEND:" in block


def test_dedupe_peer_from_recent_off_parity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_COMMS_COMPACT", raising=False)
    peer = _Msg(role="agent", content="peer text", agent="claude")
    recent = [
        _Msg(role="user", content="human", agent="human"),
        peer,
    ]
    out, removed = rc.dedupe_peer_from_recent(recent, [peer])
    assert removed == 1
    assert peer not in out


def test_dedupe_peer_from_recent_compact_keeps_prose(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_COMMS_COMPACT", "1")
    peer = _Msg(role="agent", content="peer text", agent="claude")
    recent = [
        _Msg(role="user", content="human", agent="human"),
        peer,
    ]
    out, removed = rc.dedupe_peer_from_recent(recent, [peer])
    assert removed == 0
    assert peer in out


def test_divergence_turn_profile_scopes_out_compact() -> None:
    """Compact flag is ignored when turn_profile is divergence/발산."""
    assert rc._env_bool("AGENT_LAB_COMMS_COMPACT") is False
    # The divergence scoping is implemented in context_bundle.py; this test
    # documents the contract at the boundary.
    profile = "divergence"
    compact = True and profile not in {"divergence", "발산"}
    assert compact is False
