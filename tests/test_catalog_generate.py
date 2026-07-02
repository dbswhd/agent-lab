"""Tests for model catalog generation and Codex discovery."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.agent import catalog_discovery as cd
from agent_lab.agent import catalog_generate as cg


def test_parse_version_from_slug() -> None:
    assert cd.parse_version_from_slug("gpt-5.5") == [5, 5, 0]
    assert cd.parse_version_from_slug("gpt-5") == [5, 0, 0]
    assert cd.parse_version_from_slug("gpt-4.1") == [4, 1, 0]


def test_normalize_codex_entry_maps_efforts() -> None:
    row = cd._normalize_codex_entry(
        {
            "slug": "gpt-5.5",
            "display_name": "GPT-5.5",
            "supported_reasoning_levels": [
                {"effort": "high"},
                {"effort": "medium"},
                {"effort": "none"},
            ],
        }
    )
    assert row is not None
    assert row["id"] == "gpt-5.5"
    assert row["efforts"] == ["medium", "high"]


def test_merge_codex_models_updates_and_appends() -> None:
    seed = [
        {"id": "gpt-5.4", "label": "GPT-5.4", "version": [5, 4, 0]},
        {"id": "gpt-5", "label": "GPT-5", "version": [5, 0, 0]},
    ]
    discovered = [
        {
            "id": "gpt-5.5",
            "label": "GPT-5.5",
            "version": [5, 5, 0],
            "source": "discovered",
        },
        {
            "id": "gpt-5.4",
            "label": "GPT-5.4 refreshed",
            "version": [5, 4, 0],
            "efforts": ["minimal", "low", "medium", "high"],
        },
    ]
    merged = cg.merge_codex_models(seed, discovered)
    assert merged[0]["id"] == "gpt-5.5"
    assert merged[1]["label"] == "GPT-5.4 refreshed"
    assert merged[1]["efforts"] == ["minimal", "low", "medium", "high"]
    assert any(row["id"] == "gpt-5" for row in merged)


def test_apply_provider_overrides_patches_fable() -> None:
    catalog = {
        "providers": {
            "claude": {
                "models": [
                    {
                        "id": "fable",
                        "label": "Fable 5",
                        "family": "fable",
                        "version": [5, 0, 0],
                    }
                ]
            }
        }
    }
    overrides = {
        "providers": {
            "claude": {
                "picker": "latest_per_family",
                "model_patches": [
                    {
                        "match": {"id": "fable", "version": [5, 0, 0]},
                        "patch": {
                            "available": False,
                            "coming_soon_note": "soon",
                        },
                    }
                ],
            }
        }
    }
    out = cg.apply_provider_overrides(catalog, overrides)
    fable = out["providers"]["claude"]["models"][0]
    assert fable["available"] is False
    assert fable["coming_soon_note"] == "soon"


def test_generate_catalog_without_discovery_is_stable(tmp_path: Path) -> None:
    seed = cg._read_json(cg.CATALOG_PATH)
    first, _, _ = cg.generate_catalog(seed=seed, discover_codex=False)
    second, _, _ = cg.generate_catalog(seed=seed, discover_codex=False)
    assert cg.catalogs_equivalent(first, second)


def test_generate_catalog_with_mock_codex_discovery() -> None:
    seed = cg._read_json(cg.CATALOG_PATH)
    discovered = [
        {
            "id": "gpt-5.6",
            "label": "GPT-5.6",
            "version": [5, 6, 0],
            "efforts": ["minimal", "low", "medium", "high"],
            "source": "discovered",
        }
    ]
    catalog, sources, _ = cg.generate_catalog(
        seed=seed,
        discover_codex=False,
        codex_models=discovered,
    )
    assert "codex-oauth" in sources
    codex_models = catalog["providers"]["codex"]["models"]
    assert codex_models[0]["id"] == "gpt-5.6"


def test_fetch_codex_catalog_models_parses_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps(
        {
            "models": [
                {
                    "slug": "gpt-5.5",
                    "display_name": "GPT-5.5",
                    "supported_in_api": True,
                    "supported_reasoning_levels": [{"effort": "high"}],
                }
            ]
        }
    ).encode("utf-8")

    class _Resp:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def read(self) -> bytes:
            return self._body

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: _Resp(payload))
    models, err = cd.fetch_codex_catalog_models(access_token="token", account_id="acct")
    assert err is None
    assert len(models) == 1
    assert models[0]["id"] == "gpt-5.5"


def test_check_script_no_discover_passes() -> None:
    seed = cg._read_json(cg.CATALOG_PATH)
    generated, _, _ = cg.generate_catalog(seed=seed, discover_codex=False)
    assert cg.catalogs_equivalent(generated, seed)
