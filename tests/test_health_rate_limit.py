"""Burst rate limit on bare GET /api/health."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def health_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_HEALTH_RATE_LIMIT_MAX", "5")
    monkeypatch.setenv("AGENT_LAB_HEALTH_RATE_LIMIT_WINDOW_SEC", "60")

    from app.server.health_rate_limit import reset_health_rate_limit_for_tests

    reset_health_rate_limit_for_tests()
    from app.server.main import app

    return TestClient(app)


def test_health_burst_returns_429(health_client: TestClient) -> None:
    from app.server.health_rate_limit import reset_health_rate_limit_for_tests

    reset_health_rate_limit_for_tests()
    codes = [health_client.get("/api/health").status_code for _ in range(6)]
    assert 200 in codes
    assert 429 in codes


def test_health_probe_query_bypasses_rate_limit(health_client: TestClient) -> None:
    from app.server.health_rate_limit import reset_health_rate_limit_for_tests

    reset_health_rate_limit_for_tests()
    codes = [health_client.get("/api/health?probe_bridge=true&probe_preflight=true").status_code for _ in range(10)]
    assert all(code == 200 for code in codes)
