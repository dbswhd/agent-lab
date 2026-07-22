"""P1-1 — consensus_rounds.py must not permanently void consensus on a single
transient agent-call failure. Before this fix, one agent erroring mid-round
(API/timeout/reconnect) made ``run_consensus_agent_rounds`` return
``{"status": "failed", "reason": "agent_error"}`` even when every other agent
cleanly ENDORSEd — which in turn meant ``record_consensus_agreement`` (gated
on ``status == "reached"``) never fired, permanently blocking the chat-native
execute-hint / consensus dry-run proposal that depends on it."""

from __future__ import annotations

from typing import Any

import pytest

from agent_lab.room.consensus_rounds import _retry_once_after_transient_failure
from agent_lab.room.messages import ChatMessage


def _err(agent: str, content: str = "boom") -> ChatMessage:
    return ChatMessage(role="system", agent=agent, content=content)


def _reply(agent: str, content: str = "이의 없습니다") -> ChatMessage:
    return ChatMessage(role="agent", agent=agent, content=content)


def _common_kwargs() -> dict[str, Any]:
    return {
        "parallel_round": 1,
        "on_event": None,
        "permissions": None,
        "human_turn_index": 0,
        "plan_md": "",
        "run_meta": None,
        "context_log": None,
        "efficiency_mode": False,
        "task_type": "consensus",
    }


class TestRetryOnceAfterTransientFailure:
    def test_no_failures_is_a_passthrough_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[Any] = []
        monkeypatch.setattr(
            "agent_lab.room.consensus_rounds.run_parallel_round",
            lambda *a, **k: calls.append(k) or [],
        )
        batch = [_reply("codex"), _reply("claude")]
        out = _retry_once_after_transient_failure("t", [], batch, **_common_kwargs())
        assert out is batch
        assert calls == []  # never invokes a retry round when nothing failed

    def test_retries_only_the_failed_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: list[list[str]] = []

        def _fake_round(topic: str, messages: Any, agents: Any = None, **kwargs: Any) -> list[ChatMessage]:
            captured.append([str(a) for a in (agents or [])])
            return [_reply("codex", "이의 없습니다 (retry)")]

        monkeypatch.setattr("agent_lab.room.consensus_rounds.run_parallel_round", _fake_round)
        batch = [_err("codex"), _reply("claude")]
        out = _retry_once_after_transient_failure("t", [], batch, **_common_kwargs())

        assert captured == [["codex"]]  # only the failed agent is retried, not the whole active set
        agents_out = {m.agent: m for m in out}
        assert agents_out["codex"].role == "agent"  # system-error superseded by the retry's reply
        assert agents_out["codex"].content == "이의 없습니다 (retry)"
        assert agents_out["claude"].role == "agent"  # untouched peer reply preserved
        assert agents_out["codex"].retry_of_turn == 0

    def test_retry_that_fails_again_still_reports_system_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "agent_lab.room.consensus_rounds.run_parallel_round",
            lambda *a, **k: [_err("codex", "still broken")],
        )
        batch = [_err("codex"), _reply("claude")]
        out = _retry_once_after_transient_failure("t", [], batch, **_common_kwargs())

        from agent_lab.room.messages import _agent_turn_failed

        assert _agent_turn_failed(out) is True  # caller's existing agent_error path still applies


def test_round1_transient_error_does_not_void_whole_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Integration-level: round 1 has one transient failure among two agents;
    the retry succeeds, so the turn must NOT short-circuit to
    {"status": "failed", "reason": "agent_error", "rounds": 1}."""
    from agent_lab.room.consensus_rounds import run_consensus_agent_rounds

    call_log: list[list[str]] = []

    def _fake_round(topic: str, messages: Any, agents: Any = None, **kwargs: Any) -> list[ChatMessage]:
        ids = [str(a) for a in (agents or [])]
        call_log.append(ids)
        if ids == ["codex", "claude"]:
            return [_err("codex"), _reply("claude")]
        if ids == ["codex"]:
            return [_reply("codex", "이의 없습니다 (retry)")]
        return []  # any later review/recombination/anchor round — nothing further to add

    monkeypatch.setattr("agent_lab.room.consensus_rounds.run_parallel_round", _fake_round)

    events: list[tuple[str, dict]] = []
    _replies, result = run_consensus_agent_rounds(
        topic="t",
        messages=[],
        agents=["codex", "claude"],
        on_event=lambda name, payload: events.append((name, payload)),
        run_meta={},
    )

    assert call_log[0] == ["codex", "claude"]
    assert call_log[1] == ["codex"]  # retry happened before falling through to later rounds
    assert not (
        isinstance(result, dict) and result.get("status") == "failed" and result.get("rounds") == 1
    )
    assert ("consensus_retry", {"round": 1, "agents": ["codex"], "message": "codex 호출 실패 — 해당 에이전트만 1회 재시도합니다."}) in events


def test_debate_loop_round_transient_error_does_not_void_whole_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same fix, second call site: a transient failure in the debate loop
    (round >= 2, not round 1) must also retry-then-continue instead of
    permanently failing the whole consensus computation."""
    from agent_lab.room.consensus_rounds import run_consensus_agent_rounds

    call_log: list[tuple[list[str], int | None]] = []

    def _fake_round(topic: str, messages: Any, agents: Any = None, **kwargs: Any) -> list[ChatMessage]:
        ids = [str(a) for a in (agents or [])]
        pr = kwargs.get("parallel_round")
        call_log.append((ids, pr))
        if pr == 2 and ids == ["codex", "claude"]:
            return [_err("codex"), _reply("claude")]
        if pr == 2 and ids == ["codex"]:
            return [_reply("codex", "이의 없습니다 (retry)")]
        return [_reply(a) for a in ids]

    monkeypatch.setattr("agent_lab.room.consensus_rounds.run_parallel_round", _fake_round)

    events: list[tuple[str, dict]] = []
    # A long, discursive topic routes to a "standard"/"deep" category with
    # cap_rounds >= 2, so the debate loop (round 2+) actually runs — a short
    # topic routes "quick" and the loop never fires.
    _replies, result = run_consensus_agent_rounds(
        topic=(
            "이 계획을 자세히 토론하고 검증해서 합의해줘 매우 길고 복잡한 논쟁적인 "
            "주제입니다 반드시 여러 라운드 토론이 필요합니다"
        ),
        messages=[],
        agents=["codex", "claude"],
        on_event=lambda name, payload: events.append((name, payload)),
        run_meta={},
    )

    assert (["codex", "claude"], 2) in call_log
    assert (["codex"], 2) in call_log  # retry happened for round 2, not just round 1
    assert not (
        isinstance(result, dict) and result.get("status") == "failed" and result.get("rounds") == 2
    )
    assert (
        "consensus_retry",
        {"round": 2, "agents": ["codex"], "message": "codex 호출 실패 — 해당 에이전트만 1회 재시도합니다."},
    ) in events


# --- P2-1 investigation: same "agent_error" status also silently starved plan.md ---
#
# ``maybe_auto_scribe_after_consensus`` (room/turn_meta.py) only auto-writes
# plan.md when ``consensus_reached(consensus_meta)`` — i.e. the SAME
# ``consensus_meta`` dict this module returns. Before this fix, a single
# transient round-1 failure produced status "failed"/"agent_error" instead of
# "reached", so plan.md sync was silently skipped for the whole turn — not
# just consensus-agreement recording. This was the exact state found on disk
# in the calc_cli dogfood session (Cursor's "plan.md is unrelated stale
# content" finding): the session's run.json had
# ``consensus: {"status": "failed", "reason": "agent_error"}`` and no plan.md
# was ever written for that topic.
#
# All 5 "agent_error" call sites in consensus_rounds.py (round 1, debate loop,
# recombination round, quality-gate review, anchor/endorse loop) now retry a
# transient failure once before giving up — this test documents the causal
# link to plan.md starvation itself, which stays correct behavior for a
# *genuine* (non-transient, post-retry) agent_error.
def test_agent_error_status_also_skips_plan_md_sync() -> None:
    from agent_lab.room.turn_meta import consensus_reached, maybe_auto_scribe_after_consensus

    agent_error_meta = {"status": "failed", "reason": "agent_error", "rounds": 1, "calls": 2}
    assert consensus_reached(agent_error_meta) is False

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        result = maybe_auto_scribe_after_consensus(
            folder,
            consensus_meta=agent_error_meta,
            synthesize=False,
            cancelled=False,
        )
    assert result is None  # plan.md sync silently skipped — not attempted, not logged
