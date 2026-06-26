"""Persist default Room model composition (~/.agent-lab/room_models)."""

from __future__ import annotations

from pathlib import Path


def default_room_models_path() -> Path:
    from agent_lab.app_config import config_dir

    return config_dir() / "room_models"


def load_default_room_models() -> list[str] | None:
    path = default_room_models_path()
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    ids = [tok.strip() for tok in raw.split(",") if tok.strip()]
    return ids or None


def persist_default_room_models(composition: list[str]) -> Path:
    path = default_room_models_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(",".join(composition) + "\n", encoding="utf-8")
    return path


def apply_default_room_models_to_env() -> list[str] | None:
    models = load_default_room_models()
    if not models:
        return None
    import os

    os.environ["AGENT_LAB_ROOM_MODELS"] = ",".join(models)
    return models
