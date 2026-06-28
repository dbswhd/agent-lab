"""Per-provider model presets for the /model slash picker."""

from __future__ import annotations

import os
from pathlib import Path

from agent_lab.agent import models as agent_models
from agent_lab.agent.auth_bootstrap import _append_dotenv_line
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

_PRESETS: dict[str, list[ModelPreset]] = {
    "claude": [
        {"value": "opus|high", "label": "Opus 4.6 · high", "model": "opus", "effort": "high"},
        {"value": "opus|medium", "label": "Opus 4.6 · medium", "model": "opus", "effort": "medium"},
        {"value": "opus|low", "label": "Opus 4.6 · low", "model": "opus", "effort": "low"},
        {"value": "sonnet|high", "label": "Sonnet 4.6 · high", "model": "sonnet", "effort": "high"},
        {"value": "sonnet|medium", "label": "Sonnet 4.6 · medium", "model": "sonnet", "effort": "medium"},
        {"value": "haiku|high", "label": "Haiku 4.5 · high", "model": "haiku", "effort": "high"},
    ],
    "codex": [
        {"value": "gpt-5.5|high", "label": "GPT-5.5 · high", "model": "gpt-5.5", "effort": "high"},
        {"value": "gpt-5.5|medium", "label": "GPT-5.5 · medium", "model": "gpt-5.5", "effort": "medium"},
        {"value": "gpt-5.5|low", "label": "GPT-5.5 · low", "model": "gpt-5.5", "effort": "low"},
        {"value": "gpt-5|high", "label": "GPT-5 · high", "model": "gpt-5", "effort": "high"},
        {"value": "gpt-5|medium", "label": "GPT-5 · medium", "model": "gpt-5", "effort": "medium"},
    ],
    "cursor": [
        {"value": "default", "label": "기본 (default)", "model": "default", "effort": None},
    ],
    "kimi": [
        {"value": "kimi-k2", "label": "Kimi K2", "model": "kimi-k2", "effort": None},
    ],
}


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
    return provider in _PRESETS


def provider_label(provider: str) -> str:
    spec = provider_registry.get_provider(provider)
    return spec.label if spec else provider


def provider_display_label(provider: str) -> str:
    return _PROVIDER_DISPLAY.get(provider) or provider_label(provider)


def provider_picker_order() -> tuple[str, ...]:
    return _PROVIDER_PICKER_ORDER


def current_preset_value(provider: str) -> str | None:
    keys = _PROVIDER_ENV.get(provider)
    if not keys:
        return None
    model = os.getenv(keys["model"], "").strip()
    effort = os.getenv(keys.get("effort", ""), "").strip() if "effort" in keys else ""
    if provider == "claude":
        model = model or agent_models.DEFAULT_CLAUDE_MODEL
        effort = effort or agent_models.DEFAULT_CLAUDE_REASONING_EFFORT
        return f"{model}|{effort}"
    if provider == "codex":
        model = model or agent_models.DEFAULT_CODEX_MODEL
        effort = effort or agent_models.DEFAULT_CODEX_REASONING_EFFORT
        return f"{model}|{effort}"
    if provider == "cursor":
        return model or agent_models.DEFAULT_CURSOR_MODEL
    if provider == "kimi":
        return model or "kimi-k2"
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
    active = current_preset_value(provider)
    rows: list[dict[str, str | bool]] = []
    for preset in _PRESETS.get(provider, []):
        value = str(preset["value"])
        rows.append(
            {
                "value": value,
                "label": str(preset["label"]),
                "selected": value == active,
            }
        )
    return rows


def _preset_map(provider: str) -> dict[str, ModelPreset]:
    return {str(p["value"]): p for p in _PRESETS.get(provider, [])}


def apply_preset(provider: str, preset_value: str) -> str:
    preset = _preset_map(provider).get(preset_value)
    if preset is None:
        raise ValueError(f"unknown model preset: {preset_value}")
    keys = _PROVIDER_ENV.get(provider)
    if not keys:
        raise ValueError(f"provider {provider} has no model settings")
    model = str(preset.get("model") or "").strip()
    effort = preset.get("effort")
    if model:
        env_key = keys["model"]
        os.environ[env_key] = model
        _append_dotenv_line(env_key, model)
    if effort and "effort" in keys:
        env_key = keys["effort"]
        os.environ[env_key] = str(effort)
        _append_dotenv_line(env_key, str(effort))
        if provider == "codex" and "room_effort" in keys:
            room_key = keys["room_effort"]
            os.environ[room_key] = str(effort)
            _append_dotenv_line(room_key, str(effort))
    return str(preset["label"])


def default_model_summary(provider: str) -> str:
    keys = _PROVIDER_ENV.get(provider)
    if not keys:
        return ""
    model = os.getenv(keys["model"], "")
    if provider == "claude":
        model = model or agent_models.DEFAULT_CLAUDE_MODEL
        effort = os.getenv(keys.get("effort", ""), agent_models.DEFAULT_CLAUDE_REASONING_EFFORT)
        return f"{model} · {effort}"
    if provider == "codex":
        model = model or agent_models.DEFAULT_CODEX_MODEL
        effort = os.getenv(keys.get("effort", ""), agent_models.DEFAULT_CODEX_REASONING_EFFORT)
        return f"{model} · {effort}"
    if provider == "cursor":
        return model or agent_models.DEFAULT_CURSOR_MODEL
    if provider == "kimi":
        return model or "kimi-k2"
    return model
