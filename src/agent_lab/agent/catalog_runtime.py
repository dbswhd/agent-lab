"""Runtime model catalog cache, refresh, and health metadata."""

from __future__ import annotations

import copy
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.time_utils import utc_now_iso_seconds as _utc_now_iso, utc_now
from agent_lab.agent import catalog_discovery
from agent_lab.agent.catalog_generate import merge_codex_models

_CACHE_BASENAME = "model_catalog.cache.json"
_DEFAULT_TTL_S = 86_400.0
_refresh_lock = threading.Lock()
_refresh_inflight = False


def _true_env(name: str, *, default: str = "0") -> bool:
    raw = (os.getenv(name) or default).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def catalog_refresh_enabled() -> bool:
    return _true_env("AGENT_LAB_MODEL_CATALOG_REFRESH", default="0")


def catalog_refresh_codex_enabled() -> bool:
    if not catalog_refresh_enabled():
        return False
    return _true_env("AGENT_LAB_MODEL_CATALOG_REFRESH_CODEX", default="1")


def catalog_ttl_sec() -> float:
    raw = (os.getenv("AGENT_LAB_MODEL_CATALOG_TTL_S") or "").strip()
    try:
        value = float(raw)
    except ValueError:
        value = _DEFAULT_TTL_S
    return max(60.0, value)


def _mock_mode() -> bool:
    return _true_env("AGENT_LAB_MOCK_AGENTS", default="0")


def cache_path() -> Path:
    from agent_lab.app_config import config_dir

    return config_dir() / _CACHE_BASENAME


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_cache() -> dict[str, Any] | None:
    path = cache_path()
    if not path.is_file():
        return None
    payload = _read_json(path)
    return payload if payload else None


def write_cache(*, codex_models: list[dict[str, Any]], source: str = "codex-oauth") -> Path:
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "fetched_at": _utc_now_iso(),
            "source": source,
            "ttl_s": catalog_ttl_sec(),
            "count": len(codex_models),
        },
        "providers": {
            "codex": {
                "models": copy.deepcopy(codex_models),
            }
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def clear_cache() -> None:
    path = cache_path()
    if path.is_file():
        path.unlink()


def cache_fetched_at(cache: dict[str, Any] | None = None) -> datetime | None:
    payload = cache if cache is not None else read_cache()
    if not payload:
        return None
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return None
    raw = meta.get("fetched_at")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def cache_age_sec(cache: dict[str, Any] | None = None) -> float | None:
    fetched = cache_fetched_at(cache)
    if fetched is None:
        return None
    return max(0.0, (utc_now() - fetched).total_seconds())


def cache_is_stale(cache: dict[str, Any] | None = None) -> bool:
    payload = cache if cache is not None else read_cache()
    if payload is None:
        return True
    meta = payload.get("meta")
    ttl = catalog_ttl_sec()
    if isinstance(meta, dict) and meta.get("ttl_s") is not None:
        try:
            ttl = max(60.0, float(meta["ttl_s"]))
        except (TypeError, ValueError):
            pass
    age = cache_age_sec(payload)
    if age is None:
        return True
    return age >= ttl


def merge_effective_catalog(bundled: dict[str, Any], cache: dict[str, Any] | None) -> dict[str, Any]:
    """Overlay cached Codex discovery rows onto the bundled catalog."""
    effective = copy.deepcopy(bundled)
    if not cache:
        return effective
    cache_providers = cache.get("providers")
    if not isinstance(cache_providers, dict):
        return effective
    cache_codex = cache_providers.get("codex")
    if not isinstance(cache_codex, dict):
        return effective
    cache_models = cache_codex.get("models")
    if not isinstance(cache_models, list) or not cache_models:
        return effective

    providers = effective.setdefault("providers", {})
    if not isinstance(providers, dict):
        return effective
    codex_entry = providers.get("codex")
    if not isinstance(codex_entry, dict):
        codex_entry = {}
        providers["codex"] = codex_entry
    seed_models = codex_entry.get("models")
    seed_list = [row for row in seed_models if isinstance(row, dict)] if isinstance(seed_models, list) else []
    codex_entry["models"] = merge_codex_models(seed_list, [row for row in cache_models if isinstance(row, dict)])

    runtime_meta = effective.setdefault("meta", {})
    if isinstance(runtime_meta, dict):
        runtime_meta["runtime_cache"] = {
            "applied": True,
            "source": (cache.get("meta") or {}).get("source") if isinstance(cache.get("meta"), dict) else "cache",
            "fetched_at": (cache.get("meta") or {}).get("fetched_at") if isinstance(cache.get("meta"), dict) else None,
        }
    return effective


def refresh_catalog(*, force: bool = False) -> dict[str, Any]:
    """Refresh Codex runtime cache from OAuth backend discovery."""
    global _refresh_inflight
    if not catalog_refresh_codex_enabled() and not force:
        return {"ok": False, "skipped": True, "detail": "AGENT_LAB_MODEL_CATALOG_REFRESH not enabled"}
    if _mock_mode():
        return {"ok": False, "skipped": True, "detail": "mock agents enabled"}

    with _refresh_lock:
        if _refresh_inflight:
            return {"ok": True, "skipped": True, "detail": "refresh already in flight"}
        cache = read_cache()
        if not force and cache is not None and not cache_is_stale(cache):
            return {
                "ok": True,
                "skipped": True,
                "detail": "cache fresh",
                "age_s": cache_age_sec(cache),
            }
        _refresh_inflight = True

    try:
        discovered, detail = catalog_discovery.discover_codex_models()
        if not discovered:
            return {"ok": False, "detail": detail or "no models discovered"}
        write_cache(codex_models=discovered)
        from agent_lab.agent import model_catalog

        model_catalog.reload_catalog()
        return {
            "ok": True,
            "count": len(discovered),
            "path": str(cache_path()),
            "age_s": 0.0,
        }
    finally:
        with _refresh_lock:
            _refresh_inflight = False


def refresh_catalog_if_stale(*, force: bool = False, background: bool = False) -> None:
    if not catalog_refresh_codex_enabled() and not force:
        return
    if _mock_mode():
        return

    def _run() -> None:
        try:
            refresh_catalog(force=force)
        except Exception:
            pass

    if background:
        threading.Thread(target=_run, daemon=True, name="model-catalog-refresh").start()
        return
    _run()


def warm_catalog_on_startup(*, background: bool = True) -> None:
    """Non-blocking startup hook — stale-while-revalidate when refresh flag is on."""
    if not catalog_refresh_enabled():
        return
    refresh_catalog_if_stale(force=False, background=background)


def build_model_catalog_health() -> dict[str, Any]:
    from agent_lab.agent.catalog_generate import CATALOG_PATH
    from agent_lab.agent.model_catalog import bundled_catalog

    bundled = bundled_catalog()
    cache = read_cache()
    age = cache_age_sec(cache)
    stale = cache_is_stale(cache) if cache is not None else True
    sources = ["bundled"]
    if cache is not None:
        sources.append("runtime-cache")
    bundled_meta_raw = bundled.get("meta")
    bundled_meta: dict[str, Any] = bundled_meta_raw if isinstance(bundled_meta_raw, dict) else {}
    cache_meta: dict[str, Any] = {}
    if isinstance(cache, dict):
        cache_meta_raw = cache.get("meta")
        if isinstance(cache_meta_raw, dict):
            cache_meta = cache_meta_raw
    codex_models = 0
    providers = bundled.get("providers")
    if isinstance(providers, dict):
        codex = providers.get("codex")
        if isinstance(codex, dict):
            models_list = codex.get("models")
            if isinstance(models_list, list):
                codex_models = len(models_list)
    return {
        "ok": True,
        "refresh_enabled": catalog_refresh_enabled(),
        "codex_refresh_enabled": catalog_refresh_codex_enabled(),
        "ttl_s": catalog_ttl_sec(),
        "bundled_path": str(CATALOG_PATH),
        "cache_path": str(cache_path()),
        "cache_present": cache is not None,
        "cache_age_s": age,
        "cache_stale": stale,
        "cache_fetched_at": cache_meta.get("fetched_at"),
        "cache_count": cache_meta.get("count"),
        "bundled_generated_at": bundled_meta.get("generated_at"),
        "bundled_codex_models": codex_models,
        "sources": sources,
        "refreshing": _refresh_inflight,
    }


def reset_runtime_state_for_tests() -> None:
    global _refresh_inflight
    with _refresh_lock:
        _refresh_inflight = False
