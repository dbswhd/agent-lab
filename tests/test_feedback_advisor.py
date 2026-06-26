"""S1 Phase B — feedback_advisor unit tests (mock-only, no I/O to real project)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.feedback_advisor import (
    _DEFAULT_HINT,
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
    consensus: bool = True,
) -> dict:
    return {
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


# ---------------------------------------------------------------------------
# advise_setup — flag off → default hint
# ---------------------------------------------------------------------------

def test_advise_setup_flag_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_FEEDBACK_ADVISOR", raising=False)
    hint = advise_setup("pipeline verify", "standard", ["cursor", "codex", "claude"])
    assert hint is _DEFAULT_HINT


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
