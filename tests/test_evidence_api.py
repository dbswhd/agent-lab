"""Tests for Evidence + Verification API (P2-8)."""

from __future__ import annotations

import pytest

from app.server.routers.evidence_api import (
    VerifyRequest,
    _build_execution_dict,
    _run_oracle_mock,
)


def test_build_execution_dict_defaults() -> None:
    req = VerifyRequest(diff="+minor fix", touched_paths=["src/utils.py"])
    ex = _build_execution_dict(req)
    assert ex["status"] == "pending_approval"
    assert ex["diff"] == "+minor fix"
    assert ex["touched_paths"] == ["src/utils.py"]
    assert ex["safety_scan"]["ok"] is True


def test_build_execution_dict_with_safety_scan() -> None:
    req = VerifyRequest(
        diff="+line",
        safety_scan={"ok": False, "findings": [{"severity": "block"}], "counts": {"blocking": 1}},
    )
    ex = _build_execution_dict(req)
    assert ex["safety_scan"]["ok"] is False


def test_mock_oracle_small_diff_passes() -> None:
    result = _run_oracle_mock("+minor fix\n-old line", "Add helper")
    assert result["verdict"] == "pass"


def test_mock_oracle_large_diff_fails() -> None:
    big_diff = "\n".join(f"+line {i}" for i in range(350))
    result = _run_oracle_mock(big_diff, "")
    assert result["verdict"] == "fail"
    assert "large diff" in result["detail"]


def test_mock_oracle_destructive_claim_fails() -> None:
    result = _run_oracle_mock("+fix", "drop table users")
    assert result["verdict"] == "fail"
    assert "destructive" in result["detail"]


def test_mock_oracle_rm_rf_claim_fails() -> None:
    result = _run_oracle_mock("+fix", "rm -rf everything")
    assert result["verdict"] == "fail"


def test_verify_endpoint_low_risk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_AUTO_APPROVE_THRESHOLD", raising=False)
    monkeypatch.delenv("AGENT_LAB_ORACLE_LIVE", raising=False)
    from app.server.routers.evidence_api import verify_diff

    req = VerifyRequest(diff="+minor fix", touched_paths=["src/utils.py"])
    resp = verify_diff(req)
    assert resp.verdict in ("pass", "fail")
    assert resp.risk_level in ("low", "medium", "high")
    assert isinstance(resp.risk_reasons, list)
    assert isinstance(resp.evidence_gates, list)
    assert len(resp.evidence_gates) == 5


def test_verify_endpoint_returns_auto_approve_eligible_when_threshold_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_AUTO_APPROVE_THRESHOLD", "low")
    monkeypatch.delenv("AGENT_LAB_ORACLE_LIVE", raising=False)
    from app.server.routers.evidence_api import verify_diff

    req = VerifyRequest(diff="+minor fix", touched_paths=["src/utils.py"])
    resp = verify_diff(req)
    assert resp.auto_approve_eligible is True
    assert resp.auto_approve_reason == "eligible"


def test_verify_endpoint_high_risk_not_auto_eligible(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_AUTO_APPROVE_THRESHOLD", "low")
    monkeypatch.delenv("AGENT_LAB_ORACLE_LIVE", raising=False)
    from app.server.routers.evidence_api import verify_diff

    big_diff = "\n".join(f"+line {i}" for i in range(350))
    req = VerifyRequest(diff=big_diff)
    resp = verify_diff(req)
    assert resp.risk_level == "high"
    assert resp.auto_approve_eligible is False


def test_verify_status_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_ORACLE_LIVE", raising=False)
    from app.server.routers.evidence_api import verify_status

    status = verify_status()
    assert status["ok"] is True
    assert status["oracle_mode"] in ("live", "mock")
    assert "gates" in status
    assert len(status["gates"]) == 5
