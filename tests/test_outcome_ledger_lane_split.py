"""Guard: mock/CI turns must not write into the live outcome ledger.

The live ledger is the evidence base for D3 promotion gates (dogfood_track,
feedback_report). ``make ci-full`` runs the mock dogfood suite, so a shared
file lets every CI run inflate the numbers those gates are judged on. The
2026-08-25 audit found 95.5% of 6,606 ledger rows were mock/fixture rows.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.outcome_harvester import outcomes_path, outcomes_relpath


def test_live_lane_uses_the_live_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    assert outcomes_relpath().name == "outcomes.jsonl"


@pytest.mark.parametrize("truthy", ["1", "true", "yes"])
def test_mock_lane_uses_a_separate_ledger(monkeypatch: pytest.MonkeyPatch, truthy: str) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", truthy)
    assert outcomes_relpath().name == "outcomes-mock.jsonl"


def test_lanes_never_resolve_to_the_same_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    live = outcomes_path(tmp_path)
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    mock = outcomes_path(tmp_path)
    assert live != mock
    assert live.parent == mock.parent, "both lanes stay under the same .agent-lab/ dir"


def test_repo_root_derivation_survives_the_split(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Callers derive the repo root via ``outcomes_path().parent.parent``.

    correction_harvester and cost_ledger_quarter both rely on that depth, so a
    lane change must not move the ledger to a different nesting level.
    """
    for value in (None, "1"):
        if value is None:
            monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
        else:
            monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", value)
        assert outcomes_path(tmp_path).parent.parent == tmp_path
