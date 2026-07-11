"""Merge bundled catalog seed, provider discovery, and manual overrides."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from agent_lab.time_utils import utc_now_iso_seconds as _utc_now_iso
from agent_lab.agent import catalog_discovery

_AGENT_DIR = Path(__file__).resolve().parent
CATALOG_PATH = _AGENT_DIR / "model_catalog.json"
OVERRIDES_PATH = _AGENT_DIR / "model_catalog.overrides.json"
GENERATOR_NAME = "generate_model_catalog.py"

_PROVIDER_POLICY_KEYS = frozenset({"picker", "visible_count", "family_order", "efforts"})
_MODEL_PATCH_KEYS = frozenset(
    {
        "id",
        "label",
        "family",
        "version",
        "efforts",
        "available",
        "coming_soon_note",
        "source",
        "discovered_at",
        "retired",
    }
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _version_key(version: Any) -> tuple[int, ...]:
    if not isinstance(version, list):
        return (0,)
    out: list[int] = []
    for part in version:
        try:
            out.append(int(part))
        except (TypeError, ValueError):
            out.append(0)
    return tuple(out)


def _model_identity(row: dict[str, Any]) -> tuple[str, tuple[int, ...]]:
    model_id = str(row.get("id") or "").strip()
    return model_id, _version_key(row.get("version"))


def _models_list(entry: dict[str, Any]) -> list[dict[str, Any]]:
    raw = entry.get("models")
    if not isinstance(raw, list):
        return []
    return [copy.deepcopy(row) for row in raw if isinstance(row, dict)]


def _merge_model_row(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(existing)
    for key, value in incoming.items():
        if key not in _MODEL_PATCH_KEYS:
            continue
        if value is None:
            merged.pop(key, None)
            continue
        merged[key] = copy.deepcopy(value)
    return merged


def merge_codex_models(
    seed_models: list[dict[str, Any]],
    discovered: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Add/update Codex rows from discovery; never delete bundled rows."""
    by_key: dict[tuple[str, tuple[int, ...]], dict[str, Any]] = {}
    order: list[tuple[str, tuple[int, ...]]] = []
    for row in seed_models:
        key = _model_identity(row)
        by_key[key] = copy.deepcopy(row)
        order.append(key)

    for incoming in discovered:
        model_id = str(incoming.get("id") or "").strip()
        if not model_id:
            continue
        version = incoming.get("version")
        key = (model_id, _version_key(version))
        if key in by_key:
            by_key[key] = _merge_model_row(by_key[key], incoming)
            continue
        # Same id, new version — append a new row.
        same_id_keys = [k for k in order if k[0] == model_id]
        if same_id_keys and version is None:
            key = same_id_keys[0]
            by_key[key] = _merge_model_row(by_key[key], incoming)
            continue
        by_key[key] = copy.deepcopy(incoming)
        order.append(key)

    merged = [by_key[key] for key in order if key in by_key]
    merged.sort(key=lambda row: _version_key(row.get("version")), reverse=True)
    return merged


def _apply_model_patches(models: list[dict[str, Any]], patches: Any) -> list[dict[str, Any]]:
    if not isinstance(patches, list):
        return models
    out = copy.deepcopy(models)
    for item in patches:
        if not isinstance(item, dict):
            continue
        match = item.get("match")
        patch = item.get("patch")
        if not isinstance(match, dict) or not isinstance(patch, dict):
            continue
        match_id = str(match.get("id") or "").strip()
        match_version = match.get("version")
        match_version_key = _version_key(match_version) if match_version is not None else None
        for idx, row in enumerate(out):
            if str(row.get("id") or "").strip() != match_id:
                continue
            if match_version_key is not None and _version_key(row.get("version")) != match_version_key:
                continue
            out[idx] = _merge_model_row(row, patch)
            break
    return out


def apply_provider_overrides(
    catalog: dict[str, Any],
    overrides: dict[str, Any],
) -> dict[str, Any]:
    providers = catalog.setdefault("providers", {})
    if not isinstance(providers, dict):
        providers = {}
        catalog["providers"] = providers

    override_providers = overrides.get("providers")
    if not isinstance(override_providers, dict):
        return catalog

    for provider, override_entry in override_providers.items():
        if not isinstance(override_entry, dict):
            continue
        entry = providers.setdefault(provider, {})
        if not isinstance(entry, dict):
            entry = {}
            providers[provider] = entry
        for key in _PROVIDER_POLICY_KEYS:
            if key in override_entry:
                entry[key] = copy.deepcopy(override_entry[key])
        models = _models_list(entry)
        models = _apply_model_patches(models, override_entry.get("model_patches"))
        if models:
            entry["models"] = models
    return catalog


def generate_catalog(
    *,
    seed: dict[str, Any] | None = None,
    overrides: dict[str, Any] | None = None,
    discover_codex: bool = True,
    codex_models: list[dict[str, Any]] | None = None,
    codex_error: str | None = None,
) -> tuple[dict[str, Any], list[str], str | None]:
    """Build effective catalog.

    Returns ``(catalog, source_labels, codex_discovery_detail)``.
    """
    base = copy.deepcopy(seed if seed is not None else _read_json(CATALOG_PATH))
    base.pop("meta", None)
    sources: list[str] = ["bundled"]

    providers = base.setdefault("providers", {})
    if not isinstance(providers, dict):
        providers = {}
        base["providers"] = providers

    discovered: list[dict[str, Any]] = []
    if codex_models is not None:
        discovered = codex_models
        if discovered:
            sources.append("codex-oauth")
    elif discover_codex:
        discovered, codex_error = catalog_discovery.discover_codex_models()
        if discovered:
            sources.append("codex-oauth")

    codex_entry = providers.get("codex")
    if isinstance(codex_entry, dict):
        seed_models = _models_list(codex_entry)
        if discovered:
            codex_entry["models"] = merge_codex_models(seed_models, discovered)
        elif seed_models:
            codex_entry["models"] = seed_models

    effective = apply_provider_overrides(base, overrides if overrides is not None else _read_json(OVERRIDES_PATH))

    meta: dict[str, Any] = {
        "generated_at": _utc_now_iso(),
        "generator": GENERATOR_NAME,
        "sources": sources,
    }
    if discovered:
        meta["codex_discovery"] = {"ok": True, "count": len(discovered)}

    effective["meta"] = meta
    detail = codex_error if discover_codex and not discovered and codex_models is None else None
    return effective, sources, detail


def catalog_json_text(catalog: dict[str, Any]) -> str:
    return json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"


def write_catalog(catalog: dict[str, Any], path: Path | None = None) -> Path:
    target = path or CATALOG_PATH
    target.write_text(catalog_json_text(catalog), encoding="utf-8")
    return target


def _strip_volatile_fields(catalog: dict[str, Any]) -> None:
    meta = catalog.get("meta")
    if isinstance(meta, dict):
        meta.pop("generated_at", None)
        meta.pop("codex_discovery", None)
        meta.pop("sources", None)
    providers = catalog.get("providers")
    if not isinstance(providers, dict):
        return
    for entry in providers.values():
        if not isinstance(entry, dict):
            continue
        models = entry.get("models")
        if not isinstance(models, list):
            continue
        for row in models:
            if isinstance(row, dict):
                row.pop("discovered_at", None)


def catalogs_equivalent(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Compare catalogs ignoring volatile ``meta``/per-model discovery timestamps.

    ``sources``/``codex_discovery`` record whether *this particular run* did
    live discovery, not a property of the merged model data — a catalog
    regenerated with ``discover_codex=False`` from an already-discovery-merged
    seed has identical models but a shorter ``sources`` list. Likewise each
    discovered model row's ``discovered_at`` is stamped fresh on every run
    (see ``fetch_codex_catalog_models``) even when the model itself is
    unchanged, so it must not affect equivalence either.
    """
    a = copy.deepcopy(left)
    b = copy.deepcopy(right)
    _strip_volatile_fields(a)
    _strip_volatile_fields(b)
    return a == b
