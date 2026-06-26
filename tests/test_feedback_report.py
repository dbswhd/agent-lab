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


def _row(source: str | None, *, verdict: str = "pass", repair: int = 0, blocks: int = 0) -> dict:
    row = {
        "category": "standard",
        "final_verdict": verdict,
        "repair_attempts": repair,
        "objection_summary": {"BLOCK": blocks} if blocks else {},
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
            _row("history", verdict="pass", repair=0),  # exploit clean
            _row("history", verdict="pass", repair=0),
            _row("explore", verdict="pass", repair=0),
        ],
    )
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger)

    rep = build_feedback_report(tmp_path)
    assert rep["total"] == 5
    assert rep["by_source"]["default"]["n"] == 2
    assert rep["by_source"]["default"]["clean_pass_rate"] == 0.0
    assert rep["by_source"]["history"]["clean_pass_rate"] == 1.0
    # history clean-pass beats default baseline
    assert rep["advisor_lift"]["history_vs_default"] == 1.0


def test_legacy_rows_without_source_fold_into_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = tmp_path / ".agent-lab" / "outcomes.jsonl"
    # No advisor_source key (pre-S1.5 rows) → counted as default baseline.
    _write_ledger(ledger, [_row(None, verdict="pass"), _row(None, verdict="fail")])
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger)

    rep = build_feedback_report(tmp_path)
    assert rep["by_source"]["default"]["n"] == 2
    assert rep["by_source"]["history"]["n"] == 0
