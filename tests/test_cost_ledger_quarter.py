"""F8 quarterly cost ledger."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.cost_ledger_quarter import (
    current_quarter,
    maybe_demote_autonomy_for_quarter_over,
    public_quarter_cost_payload,
    quarter_budget_status,
    read_quarter_ledger,
    record_session_spend,
    session_spent_usd,
    sync_session_to_quarter,
)
from agent_lab.run.meta import patch_run_meta, read_run_meta


def test_current_quarter_format() -> None:
    q = current_quarter()
    assert "-Q" in q
    year, part = q.split("-Q")
    assert year.isdigit()
    assert part in {"1", "2", "3", "4"}


def test_record_session_spend_rollup(tmp_path: Path) -> None:
    root = tmp_path
    record_session_spend("sess-a", 1.5, root=root)
    record_session_spend("sess-b", 2.25, root=root)
    record_session_spend("sess-a", 1.75, root=root)  # upsert
    payload = read_quarter_ledger(root)
    assert payload["by_session"]["sess-a"] == 1.75
    assert payload["by_session"]["sess-b"] == 2.25
    assert payload["spent_usd"] == 4.0


def test_quarter_budget_status_over(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_QUARTER_BUDGET_USD", "3")
    monkeypatch.setenv("AGENT_LAB_QUARTER_BUDGET_WARN_PCT", "50")
    record_session_spend("s1", 2.0, root=tmp_path)
    status = quarter_budget_status(tmp_path)
    assert status["warn"] is True
    assert status["over"] is False
    record_session_spend("s2", 1.5, root=tmp_path)
    status = quarter_budget_status(tmp_path)
    assert status["over"] is True
    assert status["spent_usd"] == 3.5


def test_session_spent_usd() -> None:
    assert session_spent_usd(None) == 0.0
    assert (
        session_spent_usd({"cost_ledger": {"cumulative": {"usd": 1.25}}}) == 1.25
    )


def test_demote_autonomy_on_quarter_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_QUARTER_BUDGET_USD", "1")
    monkeypatch.setenv("AGENT_LAB_QUARTER_BUDGET_DEMOTE", "1")
    folder = tmp_path / "sess-demo"
    folder.mkdir()
    patch_run_meta(
        folder,
        lambda run: {
            **run,
            "autonomy": {"level": "L2"},
            "cost_ledger": {"cumulative": {"usd": 2.0}},
        },
    )
    sync_session_to_quarter(
        folder,
        read_run_meta(folder),
        root=tmp_path,
    )
    run = read_run_meta(folder)
    assert run["autonomy"]["level"] == "L0"
    demotions = [
        t
        for t in (run["autonomy"].get("transitions") or [])
        if t.get("trigger") == "demotion"
    ]
    assert demotions
    assert "quarter_budget_over" in demotions[-1]["reason"]


def test_no_demote_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_QUARTER_BUDGET_USD", "1")
    monkeypatch.setenv("AGENT_LAB_QUARTER_BUDGET_DEMOTE", "0")
    folder = tmp_path / "sess-keep"
    folder.mkdir()
    patch_run_meta(folder, lambda run: {**run, "autonomy": {"level": "L2"}})
    record_session_spend(folder.name, 5.0, root=tmp_path)
    out = maybe_demote_autonomy_for_quarter_over(folder, root=tmp_path)
    assert out is None
    assert read_run_meta(folder)["autonomy"]["level"] == "L2"


def test_public_payload_shape(tmp_path: Path) -> None:
    record_session_spend("x", 0.5, root=tmp_path)
    payload = public_quarter_cost_payload(tmp_path)
    assert payload["spent_usd"] == 0.5
    assert "quarter" in payload
