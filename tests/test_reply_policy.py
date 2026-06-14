"""Reply policy matrix (Hook · Communicate reform)."""

from __future__ import annotations

import pytest

from agent_lab.reply_policy import (
    build_guidance_parts,
    envelope_follow_up_block,
    resolve_reply_policy,
)


def test_consensus_r2_strict_by_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AGENT_LAB_ENVELOPE_STRICT", raising=False)
    policy = resolve_reply_policy(parallel_round=2, consensus_mode=True)
    assert policy.envelope_strict is True
    assert policy.inject_envelope_guidance is True
    assert envelope_follow_up_block(policy, context="consensus")


def test_discuss_r2_warn_only(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_ENVELOPE_STRICT", "consensus_only")
    policy = resolve_reply_policy(parallel_round=2, consensus_mode=False)
    assert policy.envelope_strict is False
    assert policy.envelope_warn is True
    assert policy.inject_envelope_guidance is True
    block = envelope_follow_up_block(policy, context="discuss")
    assert block
    assert "ENVELOPE_FORMAT_GUIDANCE_SHORT" not in block
    assert "Speech-act envelope — R2+" in block


def test_minimal_guidance_tier(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_GUIDANCE_TIER", "minimal")
    policy = resolve_reply_policy(parallel_round=1, turn_profile="discuss")
    parts = build_guidance_parts(policy)
    assert not any("MULTI_AGENT" in p for p in parts)


def test_analyze_plus_efficiency_param():
    policy = resolve_reply_policy(
        parallel_round=1,
        turn_profile="analyze",
        efficiency_mode=True,
    )
    assert policy.inject_analysis is True
    assert policy.inject_efficiency is True
    assert not policy.inject_envelope_guidance
