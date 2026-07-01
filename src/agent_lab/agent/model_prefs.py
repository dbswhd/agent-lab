"""Per-provider model presets for the /model slash picker."""

from __future__ import annotations

import os
from pathlib import Path

from agent_lab.agent import model_catalog
from agent_lab.agent import models as agent_models
from agent_lab import provider_registry

ModelPreset = dict[str, str | None]

_PROVIDER_ENV: dict[str, dict[str, str]] = {
    "claude": {
        "model": "CLAUDE_MODEL",
        "effort": "CLAUDE_REASONING_EFFORT",
    },
    "codex": {
        "model": "CODEX_MODEL",
        "effort": "CODEX_REASONING_EFFORT",
        "room_effort": "CODEX_ROOM_REASONING_EFFORT",
    },
    "cursor": {"model": "CURSOR_MODEL"},
    "kimi": {"model": "AGENT_LAB_KIMI_MODEL"},
}

_PROVIDER_DISPLAY: dict[str, str] = {
    "codex": "OpenAI",
    "claude": "Anthropic",
    "cursor": "Cursor",
    "kimi": "Kimi",
}

_PROVIDER_PICKER_ORDER: tuple[str, ...] = ("codex", "claude", "cursor", "kimi")


def _auto_pref_path() -> Path:
    from agent_lab.app_config import config_dir

    return config_dir() / "model_auto"


def load_auto_multi_model() -> bool:
    path = _auto_pref_path()
    if not path.is_file():
        return False
    try:
        return path.read_text(encoding="utf-8").strip().lower() in {"1", "true", "yes", "on"}
    except OSError:
        return False


def persist_auto_multi_model(enabled: bool) -> None:
    path = _auto_pref_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("1\n" if enabled else "0\n", encoding="utf-8")


def provider_has_model_picker(provider: str) -> bool:
    return model_catalog.provider_catalog(provider) is not None


def provider_label(provider: str) -> str:
    spec = provider_registry.get_provider(provider)
    return spec.label if spec else provider


def provider_display_label(provider: str) -> str:
    return _PROVIDER_DISPLAY.get(provider) or provider_label(provider)


def provider_picker_order() -> tuple[str, ...]:
    return _PROVIDER_PICKER_ORDER


def current_model_id(provider: str) -> str:
    keys = _PROVIDER_ENV.get(provider)
    if not keys:
        return ""
    model = os.getenv(keys["model"], "").strip()
    if provider == "claude":
        return model or agent_models.DEFAULT_CLAUDE_MODEL
    if provider == "codex":
        return model or agent_models.DEFAULT_CODEX_MODEL
    if provider == "cursor":
        return model or agent_models.DEFAULT_CURSOR_MODEL
    if provider == "kimi":
        return model or "kimi-k2"
    return model


def current_effort(provider: str) -> str | None:
    keys = _PROVIDER_ENV.get(provider)
    if not keys or "effort" not in keys:
        return None
    effort = os.getenv(keys["effort"], "").strip()
    if provider == "claude":
        return effort or agent_models.DEFAULT_CLAUDE_REASONING_EFFORT
    if provider == "codex":
        return effort or agent_models.DEFAULT_CODEX_REASONING_EFFORT
    return effort or None


def current_preset_value(provider: str) -> str | None:
    model = current_model_id(provider)
    effort = current_effort(provider)
    if effort:
        return f"{model}|{effort}"
    return model or None


def provider_picker_options() -> list[dict[str, str | bool]]:
    rows: list[dict[str, str | bool]] = []
    for pid in _PROVIDER_PICKER_ORDER:
        if not provider_has_model_picker(pid):
            continue
        rows.append(
            {
                "value": pid,
                "label": provider_display_label(pid),
                "sublabel": default_model_summary(pid),
                "ready": True,
            }
        )
    return rows


def preset_picker_options(provider: str) -> list[dict[str, str | bool]]:
    """Legacy flat list (model · effort) — kept for API compatibility."""
    panel = model_panel_options(provider)
    active = current_preset_value(provider)
    rows: list[dict[str, str | bool]] = []
    efforts = panel.get("efforts") or []
    for opt in panel.get("options") or []:
        mid = str(opt.get("value") or "")
        label = str(opt.get("label") or mid)
        if efforts:
            for effort in efforts:
                value = f"{mid}|{effort}"
                rows.append(
                    {
                        "value": value,
                        "label": f"{label} · {effort}",
                        "selected": value == active,
                    }
                )
        else:
            rows.append(
                {
                    "value": mid,
                    "label": label,
                    "selected": mid == active,
                    "available": opt.get("available", True),
                }
            )
    return rows


def model_panel_options(provider: str) -> dict[str, object]:
    """Model list + effort slider for the composer side panel."""
    return model_catalog.model_panel_payload(
        provider,
        active_model=current_model_id(provider),
        active_effort=current_effort(provider),
    )


def _write_env(key: str, value: str) -> None:
    from agent_lab.agent.auth_bootstrap import _append_dotenv_line

    os.environ[key] = value
    _append_dotenv_line(key, value)
    try:
        from agent_lab.workspace.roots import project_root

        repo_env = project_root() / ".env"
        if repo_env.is_file():
            _append_dotenv_line(key, value, path=repo_env)
    except OSError:
        pass


def apply_model_only(provider: str, model_id: str) -> str:
    keys = _PROVIDER_ENV.get(provider)
    if not keys:
        raise ValueError(f"provider {provider} has no model settings")
    model = str(model_id or "").strip()
    if not model:
        raise ValueError("model id required")
    visible = {str(m.get("id")) for m in model_catalog.visible_models(provider)}
    if visible and model not in visible:
        raise ValueError(f"unknown model for {provider}: {model}")
    for row in model_catalog.visible_models(provider):
        if str(row.get("id")) == model and row.get("available") is False:
            note = row.get("coming_soon_note") or "not available yet"
            raise ValueError(f"model unavailable: {model} ({note})")
    _write_env(keys["model"], model)
    label = model
    for row in model_catalog.visible_models(provider):
        if str(row.get("id")) == model:
            label = str(row.get("label") or model)
            break
    effort = current_effort(provider)
    if effort:
        return f"{label} · {effort}"
    return label


def apply_effort_only(provider: str, effort: str) -> str:
    keys = _PROVIDER_ENV.get(provider)
    if not keys or "effort" not in keys:
        raise ValueError(f"provider {provider} has no effort setting")
    level = str(effort or "").strip().lower()
    allowed = model_catalog.effort_levels(provider)
    if allowed and level not in allowed:
        raise ValueError(f"unknown effort: {effort}")
    _write_env(keys["effort"], level)
    if provider == "codex" and "room_effort" in keys:
        _write_env(keys["room_effort"], level)
    model = current_model_id(provider)
    return f"{model} · {level}"


def apply_preset(provider: str, preset_value: str) -> str:
    """Apply model, effort, or ``model|effort`` preset."""
    raw = str(preset_value or "").strip()
    if not raw:
        raise ValueError("preset value required")
    if raw.startswith("effort:"):
        return apply_effort_only(provider, raw.split(":", 1)[1])
    if "|" in raw:
        model_id, effort = raw.split("|", 1)
        apply_model_only(provider, model_id)
        return apply_effort_only(provider, effort)
    efforts = model_catalog.effort_levels(provider)
    if efforts and raw in efforts:
        return apply_effort_only(provider, raw)
    return apply_model_only(provider, raw)


def default_model_summary(provider: str) -> str:
    model = current_model_id(provider)
    effort = current_effort(provider)
    if effort:
        return f"{model} · {effort}"
    return model
