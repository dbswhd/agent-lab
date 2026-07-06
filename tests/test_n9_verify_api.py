"""N9 — Verify API HTTP integration (audit headers + reference consumer contract)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def verify_client() -> TestClient:
    from app.server.main import app

    return TestClient(app)


def test_verify_endpoint_audit_headers(verify_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_ORACLE_LIVE", raising=False)
    resp = verify_client.post(
        "/v1/verify",
        json={
            "diff": "+minor fix\n",
            "touched_paths": ["src/utils.py"],
            "claim": "Small fix",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] in ("pass", "fail")
    assert body["agentlab"]["service"] == "verify"
    assert body["agentlab"]["request_id"].startswith("verify-")
    assert resp.headers["X-AgentLab-Service"] == "verify"
    assert resp.headers["X-AgentLab-Oracle-Verdict"] == body["verdict"]
    assert resp.headers["X-AgentLab-Request-Id"] == body["agentlab"]["request_id"]
    assert resp.headers["X-AgentLab-Oracle-Mode"] in ("mock", "live")


def test_verify_endpoint_gjc_handoff(verify_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_ORACLE_LIVE", raising=False)
    handoff = {
        "stopped_cleanly": True,
        "changed_files": ["src/foo.py"],
        "checks": [{"cmd": "make test", "exit": 0}],
        "evidence_summary": "ralplan approved",
        "risks": [],
    }
    resp = verify_client.post(
        "/v1/verify",
        json={
            "diff": "+line\n",
            "external_handoff": handoff,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["agentlab"].get("consumer") == "external"
    assert resp.headers["X-AgentLab-Oracle-Verdict"] == body["verdict"]


def test_verify_status_endpoint(verify_client: TestClient) -> None:
    resp = verify_client.get("/v1/verify/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["oracle_mode"] in ("mock", "live")


def test_verify_audit_module_roundtrip() -> None:
    from app.server.verify_audit import agentlab_extension, new_request_id, oracle_audit_headers

    rid = new_request_id("verify")
    headers = oracle_audit_headers(
        service="verify",
        request_id=rid,
        verdict="pass",
        risk_level="low",
        oracle_mode="mock",
    )
    ext = agentlab_extension(service="verify", request_id=rid, oracle_mode="mock")
    assert headers["X-AgentLab-Request-Id"] == rid
    assert ext["request_id"] == rid
