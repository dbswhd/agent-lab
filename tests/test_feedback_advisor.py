"""S1 Phase B — feedback_advisor unit tests (mock-only, no I/O to real project)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.feedback_advisor import (
    _DEFAULT_HINT,
    _combo_key,
    _explore_decision,
    _mutate_combo,
    _score_outcome,
    advise_setup,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_ledger(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _row(
    category: str = "standard",
    topic_terms: list[str] | None = None,
    roles: dict | None = None,
    verdict: str = "pass",
    repair: int = 0,
    blocks: int = 0,
    accepted_challenges: int = 0,
    challenge_resolution: dict | None = None,
    consensus: bool = True,
) -> dict:
    row = {
        "v": 1,
        "category": category,
        "topic_terms": topic_terms or ["pipeline", "verify"],
        "roles": roles or {"cursor": "proposer", "codex": "executor", "claude": "critic"},
        "agents": list((roles or {}).keys()) or ["cursor", "codex", "claude"],
        "final_verdict": verdict,
        "repair_attempts": repair,
        "objection_summary": {"BLOCK": blocks},
        "consensus_reached": consensus,
        "latency_ms": 10000,
    }
    if challenge_resolution is not None:
        row["objection_resolution"] = {"CHALLENGE": challenge_resolution}
    elif accepted_challenges:
        row["objection_resolution"] = {
            "CHALLENGE": {"accepted": accepted_challenges, "wontfix": 0, "open": 0},
        }
    return row


# ---------------------------------------------------------------------------
# _score_outcome
# ---------------------------------------------------------------------------


def test_score_clean_pass() -> None:
    assert _score_outcome(_row(verdict="pass", repair=0)) == 2.5  # +2 pass+0repair, +0.5 consensus


def test_score_pass_with_repair() -> None:
    assert _score_outcome(_row(verdict="pass", repair=2)) == 1.5  # +1 pass, +0.5 consensus


def test_score_fail() -> None:
    assert _score_outcome(_row(verdict="fail", consensus=False)) == -1.0


def test_score_block_penalty() -> None:
    assert _score_outcome(_row(verdict="pass", repair=0, blocks=2)) == 0.5  # 2.5 - 2×1.0


def test_score_accepted_challenge_bonus() -> None:
    assert _score_outcome(_row(verdict="pass", repair=0, accepted_challenges=2)) == 3.5  # 2.5 + 2×0.5


def test_score_low_pure_yield_penalizes_missing_critic() -> None:
    no_critic = {"cursor": "proposer", "codex": "executor", "claude": "proposer"}
    base = _score_outcome(
        _row(
            roles=no_critic,
            verdict="pass",
            repair=0,
            challenge_resolution={"accepted": 0, "wontfix": 0, "open": 2},
        )
    )
    with_critic = _score_outcome(
        _row(
            verdict="pass",
            repair=0,
            challenge_resolution={"accepted": 0, "wontfix": 0, "open": 2},
        )
    )
    assert with_critic > base


def test_advise_setup_prefers_critic_when_history_low_pure_yield(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_ADVISOR", "1")
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_MIN_SAMPLE", "2")
    ledger = tmp_path / ".agent-lab" / "outcomes.jsonl"

    combo_no_critic = {"cursor": "proposer", "codex": "executor", "claude": "proposer"}
    combo_with_critic = {"cursor": "proposer", "codex": "executor", "claude": "critic"}
    low_yield = {"accepted": 0, "wontfix": 0, "open": 2}

    rows = [
        _row(roles=combo_no_critic, verdict="pass", challenge_resolution=low_yield),
        _row(roles=combo_no_critic, verdict="pass", challenge_resolution=low_yield),
        _row(roles=combo_with_critic, verdict="pass", challenge_resolution=low_yield),
        _row(roles=combo_with_critic, verdict="pass", challenge_resolution=low_yield),
    ]
    _write_ledger(ledger, rows)
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger)

    hint = advise_setup("pipeline verify", "standard", ["cursor", "codex", "claude"])
    assert hint.source == "history"
    assert hint.role_overrides.get("claude") == "critic"


# ---------------------------------------------------------------------------
# advise_setup — flag off → default hint
# ---------------------------------------------------------------------------


def test_advise_setup_flag_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_FEEDBACK_ADVISOR", raising=False)
    hint = advise_setup(
        "pipeline verify",
        "standard",
        ["cursor", "codex", "claude"],
        room_preset="fast",
    )
    assert hint is _DEFAULT_HINT


def test_supervisor_preset_enables_advisor_without_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_FEEDBACK_ADVISOR", raising=False)
    monkeypatch.setattr(
        "agent_lab.outcome_harvester.outcomes_path",
        lambda root=None: tmp_path / "missing.jsonl",
    )
    # Isolate from real .claude/skills/* on disk (S3a-0 tool-card suggestions
    # are covered separately in the dedicated tests below).
    monkeypatch.setattr(
        "agent_lab.tool_cards.tool_card_note", lambda category, run_meta, workspace=None, **kw: ("", ())
    )
    hint = advise_setup(
        "pipeline verify",
        "standard",
        ["cursor", "codex", "claude"],
        room_preset="supervisor",
    )
    assert hint.source == "default"
    assert hint.rationale == "no_history"
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_ADVISOR", "0")
    hint_off = advise_setup(
        "pipeline verify",
        "standard",
        ["cursor", "codex", "claude"],
        room_preset="supervisor",
    )
    assert hint_off is _DEFAULT_HINT


# ---------------------------------------------------------------------------
# advise_setup — insufficient history → default hint
# ---------------------------------------------------------------------------


def test_advise_setup_no_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_ADVISOR", "1")
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: tmp_path / "missing.jsonl")
    hint = advise_setup("pipeline verify", "standard", ["cursor", "codex", "claude"])
    assert hint.source == "default"
    assert hint.role_overrides == {}


def test_advise_setup_below_min_sample(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_ADVISOR", "1")
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_MIN_SAMPLE", "3")
    ledger = tmp_path / ".agent-lab" / "outcomes.jsonl"
    _write_ledger(ledger, [_row(), _row()])  # only 2 rows, min=3
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger)
    hint = advise_setup("pipeline verify", "standard", ["cursor", "codex", "claude"])
    assert hint.source == "default"
    assert "insufficient_history" in hint.rationale


# ---------------------------------------------------------------------------
# advise_setup — category mismatch filtered out
# ---------------------------------------------------------------------------


def test_advise_setup_category_filter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_ADVISOR", "1")
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_MIN_SAMPLE", "1")
    ledger = tmp_path / ".agent-lab" / "outcomes.jsonl"
    _write_ledger(ledger, [_row(category="deep")] * 5)  # wrong category
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger)
    hint = advise_setup("pipeline verify", "standard", ["cursor", "codex", "claude"])
    assert hint.source == "default"


# ---------------------------------------------------------------------------
# advise_setup — happy path: history override
# ---------------------------------------------------------------------------


def test_advise_setup_returns_best_combo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_ADVISOR", "1")
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_MIN_SAMPLE", "2")
    ledger = tmp_path / ".agent-lab" / "outcomes.jsonl"

    # Combo A (cursor=proposer, claude=critic) — good scores
    combo_a = {"cursor": "proposer", "codex": "executor", "claude": "critic"}
    # Combo B (cursor=critic) — bad scores
    combo_b = {"cursor": "critic", "codex": "executor", "claude": "proposer"}

    rows = [
        _row(roles=combo_a, verdict="pass", repair=0),
        _row(roles=combo_a, verdict="pass", repair=0),
        _row(roles=combo_b, verdict="fail", repair=2, blocks=1),
        _row(roles=combo_b, verdict="fail", repair=1),
    ]
    _write_ledger(ledger, rows)
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger)

    hint = advise_setup("pipeline verify", "standard", ["cursor", "codex", "claude"])
    assert hint.source == "history"
    assert hint.sample_size == 4
    assert hint.role_overrides["cursor"] == "proposer"
    assert hint.role_overrides["claude"] == "critic"
    assert "best_combo" in hint.rationale


def test_advise_setup_prefers_execute_evidence_over_turn_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When enough phase=execute rows exist, turn-only rows for a different
    combo must not sway the pick — even though they'd win if mixed in raw."""
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_ADVISOR", "1")
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_MIN_SAMPLE", "3")
    ledger = tmp_path / ".agent-lab" / "outcomes.jsonl"

    combo_execute = {"cursor": "proposer", "codex": "executor", "claude": "critic"}
    combo_turn_only = {"cursor": "critic", "codex": "executor", "claude": "proposer"}

    rows = [
        # turn-phase rows: no real verdict, but would look "clean" if counted
        {**_row(roles=combo_turn_only, verdict="", repair=0), "phase": "turn"},
        {**_row(roles=combo_turn_only, verdict="", repair=0), "phase": "turn"},
        {**_row(roles=combo_turn_only, verdict="", repair=0), "phase": "turn"},
        # execute-phase rows: meets MIN_SAMPLE on its own
        {**_row(roles=combo_execute, verdict="pass", repair=0), "phase": "execute"},
        {**_row(roles=combo_execute, verdict="pass", repair=0), "phase": "execute"},
        {**_row(roles=combo_execute, verdict="pass", repair=0), "phase": "execute"},
    ]
    _write_ledger(ledger, rows)
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger)

    hint = advise_setup("pipeline verify", "standard", ["cursor", "codex", "claude"])
    assert hint.source == "history"
    assert hint.sample_size == 3  # only the execute-phase rows counted
    assert hint.role_overrides["cursor"] == "proposer"
    assert "evidence=execute" in hint.rationale


def test_advise_setup_falls_back_to_turn_rows_below_min_sample(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cold-start: execute-phase rows alone are below MIN_SAMPLE, so the
    advisor still falls back to the full pool (turn rows included)."""
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_ADVISOR", "1")
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_MIN_SAMPLE", "3")
    ledger = tmp_path / ".agent-lab" / "outcomes.jsonl"

    rows = [
        {**_row(verdict="pass", repair=0), "phase": "execute"},  # only 1 execute row
        {**_row(verdict="", repair=0), "phase": "turn"},
        {**_row(verdict="", repair=0), "phase": "turn"},
    ]
    _write_ledger(ledger, rows)
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger)

    hint = advise_setup("pipeline verify", "standard", ["cursor", "codex", "claude"])
    assert hint.source == "history"
    assert hint.sample_size == 3  # fell back to full pool
    assert "evidence=turn_fallback" in hint.rationale


def test_advise_setup_filters_unavailable_agents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_ADVISOR", "1")
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_MIN_SAMPLE", "1")
    ledger = tmp_path / ".agent-lab" / "outcomes.jsonl"
    # history has kimi_work but current available doesn't
    rows = [_row(roles={"cursor": "proposer", "kimi_work": "critic"})] * 3
    _write_ledger(ledger, rows)
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger)

    hint = advise_setup("pipeline verify", "standard", ["cursor", "codex"])
    # kimi_work not in available → filtered from role_overrides
    assert "kimi_work" not in (hint.role_overrides or {})


# ---------------------------------------------------------------------------
# Phase C: wisdom cross-session note injected into rationale
# ---------------------------------------------------------------------------


def test_wisdom_note_appended_when_hits_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.feedback_advisor import _wisdom_note

    fake_hits = [
        {"snippet": "캐시 무효화 전략은 TTL 기반이 더 안정적", "title": "learning-1"},
        {"snippet": "Oracle pass 후 repair_history 확인 필수", "title": "learning-2"},
    ]
    monkeypatch.setattr("agent_lab.wisdom.index.search_wisdom_cross_sessions", lambda q, limit=3: fake_hits)
    note = _wisdom_note("pipeline verify")
    assert "캐시 무효화" in note
    assert "Oracle pass" in note


def test_wisdom_note_empty_when_no_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.feedback_advisor import _wisdom_note

    monkeypatch.setattr("agent_lab.wisdom.index.search_wisdom_cross_sessions", lambda q, limit=3: [])
    assert _wisdom_note("pipeline verify") == ""


def test_wisdom_note_in_rationale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_ADVISOR", "1")
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_MIN_SAMPLE", "2")
    ledger = tmp_path / ".agent-lab" / "outcomes.jsonl"
    _write_ledger(ledger, [_row()] * 4)
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger)
    monkeypatch.setattr(
        "agent_lab.wisdom.index.search_wisdom_cross_sessions",
        lambda q, limit=3: [{"snippet": "학습내용: 병렬 에이전트 순서 고정 필요"}],
    )

    hint = advise_setup("pipeline verify", "standard", ["cursor", "codex", "claude"])
    if hint.source == "history":
        assert "wisdom:" in hint.rationale
        assert "병렬 에이전트" in hint.rationale


# ---------------------------------------------------------------------------
# S1.5: ε-greedy exploration
# ---------------------------------------------------------------------------


def test_explore_decision_deterministic_and_bounds() -> None:
    # ε=0 never explores; ε>=1 always explores; same inputs → same output.
    assert _explore_decision("topic", 5, 0.0) is False
    assert _explore_decision("topic", 5, 1.0) is True
    a = _explore_decision("topic", 5, 0.5)
    b = _explore_decision("topic", 5, 0.5)
    assert a == b  # reproducible (no global RNG)
    assert any(_explore_decision("topic", n, 0.1) for n in range(1, 21))


def test_mutate_combo_changes_one_role_to_valid() -> None:
    from agent_lab.role_plan import _ROLES

    base = {"cursor": "proposer", "codex": "executor", "claude": "critic"}
    mutated = _mutate_combo(base)
    assert mutated != base  # something changed
    assert set(mutated) == set(base)  # same agents
    assert all(r in _ROLES for r in mutated.values())  # only valid roles


def test_explore_off_parity_matches_exploit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # ε unset (default 0) → advise_setup returns the exploit (history) combo, not explore.
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_ADVISOR", "1")
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_MIN_SAMPLE", "2")
    monkeypatch.delenv("AGENT_LAB_FEEDBACK_EXPLORE_RATE", raising=False)
    ledger = tmp_path / ".agent-lab" / "outcomes.jsonl"
    _write_ledger(ledger, [_row()] * 4)
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger)

    hint = advise_setup("pipeline verify", "standard", ["cursor", "codex", "claude"])
    assert hint.source == "history"
    assert hint.combo_id  # exploit combo carries its id


def test_explore_rate_one_forces_explore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_ADVISOR", "1")
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_MIN_SAMPLE", "2")
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_EXPLORE_RATE", "1.0")
    ledger = tmp_path / ".agent-lab" / "outcomes.jsonl"
    # Two distinct combos so explore can pick the least-sampled one.
    combo_a = {"cursor": "proposer", "codex": "executor", "claude": "critic"}
    combo_b = {"cursor": "critic", "codex": "executor", "claude": "proposer"}
    _write_ledger(ledger, [_row(roles=combo_a)] * 3 + [_row(roles=combo_b)])
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger)

    hint = advise_setup("pipeline verify", "standard", ["cursor", "codex", "claude"])
    assert hint.source == "explore"
    assert hint.combo_id
    assert hint.role_overrides
    # least-sampled combo is combo_b (n=1)
    assert hint.combo_id == _combo_key(combo_b)


# ---------------------------------------------------------------------------
# S3a-0 — tool card suggestions (RECALL input, no new loop)
# ---------------------------------------------------------------------------


def test_tool_card_note_attached_on_cold_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_ADVISOR", "1")
    monkeypatch.setattr(
        "agent_lab.outcome_harvester.outcomes_path",
        lambda root=None: tmp_path / "missing.jsonl",
    )
    monkeypatch.setattr(
        "agent_lab.tool_cards.tool_card_note",
        lambda category, run_meta, workspace=None, **kw: ("impeccable", ("claude:skill:impeccable",)),
    )
    hint = advise_setup("polish the UI", "deep", ["cursor", "codex", "claude"], run_meta={"topic": "x"})
    assert hint.source == "default"  # role decision unaffected
    assert hint.tool_card_suggestions == ("claude:skill:impeccable",)
    assert "tool_cards:impeccable" in hint.rationale


def test_tool_card_note_noop_when_nothing_suggested(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_FEEDBACK_ADVISOR", "1")
    monkeypatch.setattr(
        "agent_lab.outcome_harvester.outcomes_path",
        lambda root=None: tmp_path / "missing.jsonl",
    )
    monkeypatch.setattr(
        "agent_lab.tool_cards.tool_card_note", lambda category, run_meta, workspace=None, **kw: ("", ())
    )
    hint = advise_setup("pipeline verify", "standard", ["cursor", "codex", "claude"], run_meta={})
    assert hint.tool_card_suggestions == ()
    assert "tool_cards" not in hint.rationale


def test_tool_card_note_skipped_when_advisor_flag_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_FEEDBACK_ADVISOR", raising=False)
    called = []
    monkeypatch.setattr(
        "agent_lab.tool_cards.tool_card_note",
        lambda category, run_meta, workspace=None, **kw: called.append(1) or ("x", ("y",)),
    )
    hint = advise_setup("polish the UI", "deep", ["cursor", "codex", "claude"], room_preset="fast", run_meta={})
    assert hint is _DEFAULT_HINT
    assert not called  # advisor channel reused, not a separate always-on gate
