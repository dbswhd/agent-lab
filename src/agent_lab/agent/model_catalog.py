"""Model catalog — bundled JSON + picker logic; refresh via ``make generate-model-catalog``."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_CATALOG_PATH = Path(__file__).with_name("model_catalog.json")

EFFORT_LABELS_KO: dict[str, str] = {
    "minimal": "최소",
    "low": "낮음",
    "medium": "보통",
    "high": "높음",
    "xhigh": "매우 높음",
    "max": "최대",
}


def _version_key(entry: dict[str, Any]) -> tuple[int, ...]:
    raw = entry.get("version")
    if not isinstance(raw, list):
        return (0,)
    out: list[int] = []
    for part in raw:
        try:
            out.append(int(part))
        except (TypeError, ValueError):
            out.append(0)
    return tuple(out)


def _read_bundled_catalog() -> dict[str, Any]:
    try:
        payload = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"providers": {}}
    return payload if isinstance(payload, dict) else {"providers": {}}


def bundled_catalog() -> dict[str, Any]:
    """Committed ``model_catalog.json`` without runtime cache overlay."""
    return _read_bundled_catalog()


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    from agent_lab.agent import catalog_runtime

    bundled = _read_bundled_catalog()
    cache = catalog_runtime.read_cache()
    effective = catalog_runtime.merge_effective_catalog(bundled, cache)
    if catalog_runtime.catalog_refresh_enabled() and catalog_runtime.cache_is_stale(cache):
        catalog_runtime.refresh_catalog_if_stale(background=True)
    return effective


def reload_catalog() -> None:
    load_catalog.cache_clear()


def provider_catalog(provider: str) -> dict[str, Any] | None:
    providers = load_catalog().get("providers")
    if not isinstance(providers, dict):
        return None
    entry = providers.get(provider)
    return entry if isinstance(entry, dict) else None


def _models_for_entry(entry: dict[str, Any]) -> list[dict[str, Any]]:
    raw = entry.get("models")
    if not isinstance(raw, list):
        return []
    return [m for m in raw if isinstance(m, dict) and str(m.get("id") or "").strip()]


def _resolve_latest_versions(models: list[dict[str, Any]], *, count: int) -> list[dict[str, Any]]:
    ranked = sorted(_models_for_entry({"models": models}), key=_version_key, reverse=True)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in ranked:
        mid = str(row.get("id") or "").strip()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        out.append(row)
        if len(out) >= max(1, count):
            break
    return out


def _resolve_latest_per_family(
    models: list[dict[str, Any]],
    *,
    family_order: list[str] | None = None,
) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in models:
        fam = str(row.get("family") or row.get("id") or "").strip().lower()
        if not fam:
            continue
        prev = best.get(fam)
        if prev is None or _version_key(row) > _version_key(prev):
            best[fam] = row
    order = family_order or sorted(best.keys())
    out: list[dict[str, Any]] = []
    for fam in order:
        row = best.get(fam)
        if row is not None:
            out.append(row)
    for fam in sorted(best.keys()):
        if fam not in order:
            out.append(best[fam])
    return out


def visible_models(provider: str) -> list[dict[str, Any]]:
    """Models shown in the side panel for *provider* (catalog-driven)."""
    entry = provider_catalog(provider)
    if entry is None:
        return []
    models = _models_for_entry(entry)
    picker = str(entry.get("picker") or "all").strip().lower()
    if picker == "latest_versions":
        count = int(entry.get("visible_count") or 2)
        return _resolve_latest_versions(models, count=count)
    if picker == "latest_per_family":
        order_raw = entry.get("family_order")
        order = [str(x).strip().lower() for x in order_raw] if isinstance(order_raw, list) else None
        return _resolve_latest_per_family(models, family_order=order)
    return models


def _efforts_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(x).strip().lower() for x in raw if str(x).strip()]


def effort_levels(provider: str, model_id: str | None = None) -> list[str]:
    """Effort tiers for *provider*, or for one *model_id* within it.

    Tier count varies by model (e.g. a smaller/faster model family may not
    expose the top tiers a flagship family does), so a model row's own
    ``efforts`` — when present — overrides the provider-level default rather
    than every model in a provider sharing one fixed list.
    """
    entry = provider_catalog(provider)
    if entry is None:
        return []
    if model_id:
        for row in _models_for_entry(entry):
            if str(row.get("id") or "").strip() == model_id and "efforts" in row:
                return _efforts_list(row.get("efforts"))
    return _efforts_list(entry.get("efforts"))


def model_panel_payload(
    provider: str,
    *,
    active_model: str,
    active_effort: str | None,
) -> dict[str, Any]:
    """Side-panel rows: model list + effort slider metadata."""
    models = visible_models(provider)
    efforts = effort_levels(provider, active_model)
    options: list[dict[str, Any]] = []
    for row in models:
        mid = str(row.get("id") or "").strip()
        label = str(row.get("label") or mid)
        available = row.get("available", True) is not False
        option: dict[str, Any] = {
            "value": mid,
            "label": label,
            "selected": mid == active_model,
            "available": available,
        }
        note = row.get("coming_soon_note")
        if note:
            option["coming_soon_note"] = str(note)
        options.append(option)
    return {
        "options": options,
        "efforts": efforts,
        "selected_model": active_model,
        "selected_effort": active_effort or (efforts[-1] if efforts else None),
    }
