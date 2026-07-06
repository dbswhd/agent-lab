"""N4 Layer 2 — autonomy promotion triggers."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.autonomy_ladder import public_autonomy_payload, stored_autonomy_level
from agent_lab.autonomy_promotion import (
    L0_TO_L1_STREAK,
    L1_TO_L2_MISSIONS,
    evaluate_l0_to_l1,
    evaluate_l1_to_l2,
    evaluate_l2_to_l3,
    oracle_confidence,
    record_l0_to_l1_sample,
    record_mission_completion,
)
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.trust_budget import set_trust_budget


@pytest.fixture
def session_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "sess-promo"
    folder.mkdir()
    patch_run_meta(folder, lambda run: {**run, "status": "active"})
    return folder


def test_oracle_confidence_from_verdict() -> None:
    assert oracle_confidence({"verdict": "pass"}) == 1.0
    assert oracle_confidence({"verdict": "fail"}) == 0.0
    assert oracle_confidence({"confidence": 0.9}) == 0.9


def test_l0_to_l1_auto_promote_after_streak(session_folder: Path) -> None:
    execution = {
        "oracle": {"verdict": "pass"},
        "auto_approve_risk_level": "low",
        "diff": "+line\n",
        "touched_paths": ["docs/readme.md"],
    }
    for _ in range(L0_TO_L1_STREAK):
        record_l0_to_l1_sample(session_folder, execution)

    run = read_run_meta(session_folder)
    assert stored_autonomy_level(run) == "L1"
    payload = public_autonomy_payload(run)
    assert payload["promotion"]["l0_to_l1"]["eligible"] is False
    human = [t for t in payload["transitions"] if t.get("trigger") == "auto"]
    assert any(t.get("to") == "L1" for t in human)


def test_l0_to_l1_streak_resets_on_fail(session_folder: Path) -> None:
    good = {
        "oracle": {"verdict": "pass"},
        "auto_approve_risk_level": "low",
        "diff": "",
        "touched_paths": ["docs/a.md"],
    }
    bad = {
        "oracle": {"verdict": "fail"},
        "auto_approve_risk_level": "low",
        "diff": "",
        "touched_paths": ["docs/a.md"],
    }
    for _ in range(L0_TO_L1_STREAK - 1):
        record_l0_to_l1_sample(session_folder, good)
    record_l0_to_l1_sample(session_folder, bad)
    run = read_run_meta(session_folder)
    assert evaluate_l0_to_l1(run)["streak"] == 0
    assert stored_autonomy_level(run) is None


def test_l1_to_l2_eligible_with_missions_and_budget(session_folder: Path) -> None:
    set_trust_budget(session_folder, {"auto_merge_remaining": 3, "auto_merge_total": 5})
    patch_run_meta(
        session_folder,
        lambda run: {
            **run,
            "autonomy": {"level": "L1", "promotion": {"l1_to_l2": {"missions_completed": L1_TO_L2_MISSIONS}}},
        },
    )
    run = read_run_meta(session_folder)
    status = evaluate_l1_to_l2(run)
    assert status["eligible"] is True
    assert status["requires_human"] is True


def test_l2_to_l3_eligible_when_rates_ok(session_folder: Path) -> None:
    patch_run_meta(
        session_folder,
        lambda run: {
            **run,
            "autonomy": {
                "level": "L2",
                "promotion": {
                    "l2_to_l3": {
                        "missions_total": 10,
                        "missions_done": 10,
                        "inbox_escalations": 0,
                    }
                },
            },
        },
    )
    run = read_run_meta(session_folder)
    status = evaluate_l2_to_l3(run)
    assert status["eligible"] is True
    assert status["completion_rate"] == 1.0
    assert status["escalation_rate"] == 0.0


def test_record_mission_completion_increments_counters(session_folder: Path) -> None:
    record_mission_completion(session_folder, completed=True, inbox_escalated=False)
    run = read_run_meta(session_folder)
    promo = run["autonomy"]["promotion"]
    assert promo["l1_to_l2"]["missions_completed"] == 1
    assert promo["l2_to_l3"]["missions_total"] == 1
    assert promo["l2_to_l3"]["missions_done"] == 1
