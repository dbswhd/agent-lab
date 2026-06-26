"""Tests for Trust-gated Auto-approval gate."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agent_lab.auto_approve_gate import (
    AutoApproveDecision,
    auto_approve_deadline_passed,
    auto_approve_threshold,
    auto_approve_timeout_sec,
    evaluate_auto_approve,
    mark_auto_approve_eligible,
)


def _pending(diff: str = "+minor fix", touched: list[str] | None = None) -> dict:
    return {
        "status": "pending_approval",
        "diff": diff,
        "touched_paths": touched or ["src/utils.py"],
        "paths_outside_expected": False,
        "needs_artifact_review": False,
        "safety_scan": {"ok": True, "findings": [], "counts": {"blocking": 0}},
    }


def _run_meta(total: int = 0, remaining: int = 0) -> dict:
    return {"trust_budget": {"auto_merge_total": total, "auto_merge_remaining": remaining}}


def test_threshold_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_AUTO_APPROVE_THRESHOLD", raising=False)
    assert auto_approve_threshold() is None


def test_threshold_low(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_AUTO_APPROVE_THRESHOLD", "low")
    assert auto_approve_threshold() == "low"


def test_threshold_medium(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_AUTO_APPROVE_THRESHOLD", "medium")
    assert auto_approve_threshold() == "medium"


def test_threshold_invalid_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_AUTO_APPROVE_THRESHOLD", "ultra")
    assert auto_approve_threshold() is None


def test_timeout_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_AUTO_APPROVE_TIMEOUT_SEC", raising=False)
    assert auto_approve_timeout_sec() == 30


def test_timeout_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_AUTO_APPROVE_TIMEOUT_SEC", "0")
    assert auto_approve_timeout_sec() == 0
    monkeypatch.setenv("AGENT_LAB_AUTO_APPROVE_TIMEOUT_SEC", "60")
    assert auto_approve_timeout_sec() == 60


def test_gate_disabled_when_no_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_AUTO_APPROVE_THRESHOLD", raising=False)
    decision = evaluate_auto_approve(_pending(), None)
    assert not decision.eligible
    assert decision.reason == "auto_approve_disabled"


def test_gate_eligible_low_risk_small_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_AUTO_APPROVE_THRESHOLD", "low")
    monkeypatch.delenv("AGENT_LAB_AUTO_APPROVE_TIMEOUT_SEC", raising=False)
    decision = evaluate_auto_approve(_pending("+minor fix"), None)
    assert decision.eligible
    assert decision.risk_level == "low"
    assert decision.reason == "eligible"


def test_gate_blocks_medium_risk_against_low_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_AUTO_APPROVE_THRESHOLD", "low")
    ex = _pending(touched=["src/auth/login.py"])
    decision = evaluate_auto_approve(ex, None)
    assert not decision.eligible
    assert "risk_exceeds_threshold" in decision.reason


def test_gate_allows_medium_risk_against_medium_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_AUTO_APPROVE_THRESHOLD", "medium")
    ex = _pending(touched=["src/auth/login.py"])
    decision = evaluate_auto_approve(ex, None)
    assert decision.eligible
    assert decision.risk_level == "medium"


def test_gate_blocks_high_risk_against_medium_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_AUTO_APPROVE_THRESHOLD", "medium")
    big_diff = "\n".join(f"+line {i}" for i in range(400))
    ex = _pending(diff=big_diff)
    decision = evaluate_auto_approve(ex, None)
    assert not decision.eligible
    assert decision.risk_level == "high"
    assert "risk_exceeds_threshold" in decision.reason


def test_gate_blocks_when_budget_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_AUTO_APPROVE_THRESHOLD", "low")
    run_meta = _run_meta(total=5, remaining=0)
    decision = evaluate_auto_approve(_pending(), run_meta)
    assert not decision.eligible
    assert decision.reason == "trust_budget_exhausted"


def test_gate_eligible_with_remaining_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_AUTO_APPROVE_THRESHOLD", "low")
    run_meta = _run_meta(total=5, remaining=3)
    decision = evaluate_auto_approve(_pending(), run_meta)
    assert decision.eligible


def test_gate_blocks_non_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_AUTO_APPROVE_THRESHOLD", "low")
    ex = dict(_pending(), status="merged")
    decision = evaluate_auto_approve(ex, None)
    assert not decision.eligible
    assert decision.reason == "not_pending_approval"


def test_mark_auto_approve_eligible_stamps_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_AUTO_APPROVE_TIMEOUT_SEC", "30")
    ex = _pending()
    decision = AutoApproveDecision(
        eligible=True,
        reason="eligible",
        risk_level="low",
        risk_reasons=["small_diff:5_lines"],
        threshold="low",
        timeout_sec=30,
    )
    mark_auto_approve_eligible(ex, decision)
    assert ex["auto_approve_eligible"] is True
    assert ex["auto_approve_threshold"] == "low"
    assert ex["auto_approve_risk_level"] == "low"
    assert ex["auto_approve_at"] is not None
    assert ex["auto_approve_timeout_sec"] == 30


def test_deadline_not_passed_fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    future = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
    ex = {"auto_approve_eligible": True, "auto_approve_at": future}
    assert not auto_approve_deadline_passed(ex)


def test_deadline_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    ex = {"auto_approve_eligible": True, "auto_approve_at": past}
    assert auto_approve_deadline_passed(ex)


def test_deadline_not_eligible(monkeypatch: pytest.MonkeyPatch) -> None:
    past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    ex = {"auto_approve_eligible": False, "auto_approve_at": past}
    assert not auto_approve_deadline_passed(ex)
