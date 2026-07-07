"""S1.5 — feedback_report unit tests (synthetic ledger, no real I/O)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.feedback_report import build_feedback_report


def _write_ledger(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _row(
    source: str | None,
    *,
    verdict: str = "pass",
    repair: int = 0,
    blocks: int = 0,
    accepted_challenges: int = 0,
    phase: str = "execute",
) -> dict:
    row = {
        "phase": phase,
        "category": "standard",
        "final_verdict": verdict,
        "repair_attempts": repair,
        "objection_summary": {"BLOCK": blocks} if blocks else {},
    }
    if accepted_challenges:
        row["objection_resolution"] = {
            "CHALLENGE": {"accepted": accepted_challenges, "wontfix": 0, "open": 0},
        }
    if source is not None:
        row["advisor_source"] = source
    return row


def test_empty_ledger_is_safe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: tmp_path / "missing.jsonl")
    rep = build_feedback_report(tmp_path)
    assert rep["total"] == 0
    assert rep["by_source"]["history"]["n"] == 0


def test_buckets_by_source_and_clean_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = tmp_path / ".agent-lab" / "outcomes.jsonl"
    _write_ledger(
        ledger,
        [
            _row("default", verdict="fail"),  # baseline poor
            _row("default", verdict="pass", repair=2),
            _row("history", verdict="pass", repair=0),  # exploit clean, >= MIN_SAMPLE
            _row("history", verdict="pass", repair=0),
            _row("history", verdict="pass", repair=0),
            _row("explore", verdict="pass", repair=0),
        ],
    )
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger)

    rep = build_feedback_report(tmp_path)
    assert rep["total"] == 6
    assert rep["by_source"]["default"]["n"] == 2
    assert rep["by_source"]["default"]["clean_pass_rate"] == 0.0
    assert rep["by_source"]["history"]["clean_pass_rate"] == 1.0
    # history clean-pass beats default baseline (n=3 meets MIN_SAMPLE)
    assert rep["advisor_lift"]["history_vs_default"] == 1.0
    # explore has only 1 sample — below MIN_SAMPLE, not a real signal yet
    assert rep["advisor_lift"]["explore_vs_default"] is None


def test_legacy_rows_without_source_fold_into_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = tmp_path / ".agent-lab" / "outcomes.jsonl"
    # No advisor_source key (pre-S1.5 rows) → counted as default baseline.
    _write_ledger(ledger, [_row(None, verdict="pass"), _row(None, verdict="fail")])
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger)

    rep = build_feedback_report(tmp_path)
    assert rep["by_source"]["default"]["n"] == 2
    assert rep["by_source"]["history"]["n"] == 0


def test_turn_and_legacy_rows_excluded_from_clean_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """turn-phase and legacy (no phase field) rows never carry a real verdict —
    they must count toward ``total`` but not dilute clean_pass_rate/by_source."""
    ledger = tmp_path / ".agent-lab" / "outcomes.jsonl"
    legacy_row = _row("history", verdict="")
    del legacy_row["phase"]  # pre-phase-field ledger rows never have this key
    _write_ledger(
        ledger,
        [
            _row("history", verdict="pass"),  # the one real execute-phase sample
            _row("history", verdict="", phase="turn"),
            legacy_row,
        ],
    )
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger)

    rep = build_feedback_report(tmp_path)
    assert rep["total"] == 3
    assert rep["verdict_eligible_total"] == 1
    assert rep["turn_signal_total"] == 2
    assert rep["oracle_verdict_coverage"] == pytest.approx(1 / 3, abs=1e-4)
    assert rep["by_source"]["history"]["n"] == 1
    assert rep["by_source"]["history"]["clean_pass_rate"] == 1.0


def test_turn_source_counts_track_advisor_sources_outside_quality_denominator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = tmp_path / ".agent-lab" / "outcomes.jsonl"
    _write_ledger(
        ledger,
        [
            _row("history", verdict="", phase="turn"),
            _row("history", verdict="", phase="turn"),
            _row("explore", verdict="", phase="turn"),
            _row("default", verdict="pass", phase="execute"),
        ],
    )
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger)

    rep = build_feedback_report(tmp_path)
    assert rep["by_source"]["history"]["n"] == 0
    assert rep["turn_source_counts"] == {"default": 1, "history": 2, "explore": 1}


def test_oracle_verdict_coverage_empty_ledger_is_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: tmp_path / "missing.jsonl")
    rep = build_feedback_report(tmp_path)
    assert rep["turn_signal_total"] == 0
    assert rep["oracle_verdict_coverage"] == 0.0


def test_escalation_rate_by_level(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = tmp_path / ".agent-lab" / "outcomes.jsonl"
    _write_ledger(
        ledger,
        [
            {**_row("default"), "autonomy_level": "L0", "human_inbox_escalation": True},
            {**_row("default"), "autonomy_level": "L0", "human_inbox_escalation": False},
            {**_row("history"), "autonomy_level": "L2", "human_inbox_escalation": False},
            {**_row("history"), "autonomy_level": "L2", "human_inbox_escalation": True},
        ],
    )
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger)

    rep = build_feedback_report(tmp_path)
    rates = rep["escalation_rate_by_level"]
    assert rates["L0"] == 0.5
    assert rates["L2"] == 0.5
    assert rates["L1"] is None


def test_accepted_challenge_rate_bucket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = tmp_path / ".agent-lab" / "outcomes.jsonl"
    _write_ledger(
        ledger,
        [
            _row("history", accepted_challenges=1),
            _row("history"),
            _row("default", accepted_challenges=2),
        ],
    )
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger)

    rep = build_feedback_report(tmp_path)
    assert rep["by_source"]["history"]["accepted_challenge_rate"] == 0.5
    assert rep["by_source"]["default"]["accepted_challenge_rate"] == 1.0


# ---------------------------------------------------------------------------
# S3a-0 — tool_card_hit_rate
# ---------------------------------------------------------------------------


def test_tool_card_hit_rate_absent_without_suggestions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = tmp_path / ".agent-lab" / "outcomes.jsonl"
    _write_ledger(ledger, [_row("default", verdict="pass")])
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger)

    rep = build_feedback_report(tmp_path)
    assert rep["tool_cards"] == {"n": 0, "tool_card_hit_rate": None}


def test_tool_card_hit_rate_computed_over_suggested_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = tmp_path / ".agent-lab" / "outcomes.jsonl"
    suggested_pass = {**_row("default", verdict="pass"), "tool_card_suggestions": ["claude:skill:impeccable"]}
    suggested_fail = {**_row("default", verdict="fail"), "tool_card_suggestions": ["claude:skill:impeccable"]}
    unsuggested_pass = _row("default", verdict="pass")
    _write_ledger(ledger, [suggested_pass, suggested_fail, unsuggested_pass])
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger)

    rep = build_feedback_report(tmp_path)
    # only the 2 suggested rows count toward n/hit_rate; the unsuggested pass is excluded
    assert rep["tool_cards"] == {"n": 2, "tool_card_hit_rate": 0.5}
