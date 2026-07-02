"""Runtime model catalog cache + refresh tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_lab.agent import catalog_runtime as cr
from agent_lab.agent import model_catalog as mc


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from app.server.main import app

    return TestClient(app)


@pytest.fixture
def catalog_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cfg = tmp_path / ".agent-lab"
    cfg.mkdir()
    monkeypatch.setattr("agent_lab.app_config.config_dir", lambda: cfg)
    mc.reload_catalog()
    cr.reset_runtime_state_for_tests()
    yield cfg
    mc.reload_catalog()
    cr.reset_runtime_state_for_tests()


def test_merge_effective_catalog_overlays_codex_models() -> None:
    bundled = {
        "providers": {
            "codex": {
                "models": [
                    {"id": "gpt-5.4", "label": "GPT-5.4", "version": [5, 4, 0]},
                ]
            }
        }
    }
    cache = {
        "providers": {
            "codex": {
                "models": [
                    {
                        "id": "gpt-5.6",
                        "label": "GPT-5.6",
                        "version": [5, 6, 0],
                        "source": "discovered",
                    }
                ]
            }
        }
    }
    effective = cr.merge_effective_catalog(bundled, cache)
    models = effective["providers"]["codex"]["models"]
    assert models[0]["id"] == "gpt-5.6"
    assert any(row["id"] == "gpt-5.4" for row in models)


def test_load_catalog_applies_runtime_cache(catalog_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MODEL_CATALOG_REFRESH", "0")
    cr.write_cache(
        codex_models=[
            {"id": "gpt-9.9", "label": "GPT-9.9", "version": [9, 9, 0], "source": "discovered"},
        ]
    )
    mc.reload_catalog()
    rows = mc.visible_models("codex")
    assert rows[0]["id"] == "gpt-9.9"


def test_cache_is_stale_respects_ttl(catalog_home: Path) -> None:
    stale_at = (datetime.now(timezone.utc) - timedelta(hours=30)).replace(microsecond=0).isoformat()
    path = cr.cache_path()
    path.write_text(
        json.dumps(
            {
                "meta": {"fetched_at": stale_at, "ttl_s": 3600, "source": "codex-oauth", "count": 1},
                "providers": {"codex": {"models": []}},
            }
        ),
        encoding="utf-8",
    )
    assert cr.cache_is_stale() is True


def test_refresh_catalog_writes_cache(
    catalog_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_MODEL_CATALOG_REFRESH", "1")
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "0")
    monkeypatch.setattr(
        "agent_lab.agent.catalog_discovery.discover_codex_models",
        lambda timeout_sec=20.0: (
            [{"id": "gpt-5.6", "label": "GPT-5.6", "version": [5, 6, 0]}],
            None,
        ),
    )
    out = cr.refresh_catalog(force=True)
    assert out["ok"] is True
    assert out["count"] == 1
    cache = cr.read_cache()
    assert cache is not None
    assert cache["providers"]["codex"]["models"][0]["id"] == "gpt-5.6"


def test_refresh_skipped_when_disabled(catalog_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MODEL_CATALOG_REFRESH", "0")
    out = cr.refresh_catalog(force=False)
    assert out["skipped"] is True


def test_health_model_catalog_endpoint(client: TestClient) -> None:
    res = client.get("/api/health/model-catalog")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert "cache_present" in body
    assert "bundled_codex_models" in body


def test_health_model_catalog_refresh_endpoint(
    catalog_home: Path,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_MODEL_CATALOG_REFRESH", "1")
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "0")
    monkeypatch.setattr(
        "agent_lab.agent.catalog_discovery.discover_codex_models",
        lambda timeout_sec=20.0: (
            [{"id": "gpt-5.6", "label": "GPT-5.6", "version": [5, 6, 0]}],
            None,
        ),
    )
    res = client.post("/api/health/model-catalog/refresh?force=1")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["count"] == 1
