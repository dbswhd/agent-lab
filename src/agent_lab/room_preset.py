"""Room Preset System (P1-5) — named configurations mapping to Harness team patterns.

Six presets cover the spectrum from single-shot to full mission loop, each resolving
to an existing turn_profile without adding new execution infrastructure.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

RoomPreset = Literal["fast", "consensus", "expert_pool", "producer_reviewer", "pipeline", "supervisor"]


@dataclass(frozen=True, slots=True)
class RoomPresetConfig:
    preset: RoomPreset
    turn_profile: str
    description: str
    max_agents: int | None = None  # None = no cap; set for presets with fixed team sizes
    role_policy: str = "auto"  # force | auto | off — when to activate role assignments


_PRESET_CONFIGS: dict[str, RoomPresetConfig] = {
    "fast": RoomPresetConfig(
        preset="fast",
        turn_profile="quick",
        description="Single-agent instant response — no debate, no consensus",
        max_agents=1,
    ),
    "consensus": RoomPresetConfig(
        preset="consensus",
        turn_profile="team",
        description="3-agent consensus — cursor · codex · claude discuss to agreement",
        max_agents=3,
    ),
    "expert_pool": RoomPresetConfig(
        preset="expert_pool",
        turn_profile="team",
        description="Expert-subset routing — task-matched agents selected from the pool",
    ),
    "producer_reviewer": RoomPresetConfig(
        preset="producer_reviewer",
        turn_profile="verified",
        description="Producer 제안 → Reviewer 검증 → 재조합 합성 → Oracle 검증",
        max_agents=2,
        role_policy="force",
    ),
    "pipeline": RoomPresetConfig(
        preset="pipeline",
        turn_profile="specialist",
        description="Sequential specialist pipeline — R1 researcher feeds R2 author",
        max_agents=2,
    ),
    "supervisor": RoomPresetConfig(
        preset="supervisor",
        turn_profile="loop",
        description="Mission Loop with human-gated plan — full autonomous execute cycle",
    ),
}

def resolve_preset(preset: str | None) -> RoomPresetConfig | None:
    """Return the config for a preset name, or None if unknown/unset."""
    if not preset:
        return None
    return _PRESET_CONFIGS.get(preset.strip().lower())


def default_room_preset() -> str | None:
    """Return the session default preset from AGENT_LAB_ROOM_PRESET, or None."""
    raw = (os.getenv("AGENT_LAB_ROOM_PRESET") or "").strip().lower()
    return raw if resolve_preset(raw) is not None else None


def list_presets() -> list[RoomPresetConfig]:
    """Return all available room presets in a stable display order."""
    return list(_PRESET_CONFIGS.values())


def preset_turn_profile(preset: str | None, fallback: str = "discuss") -> str:
    """Resolve a preset to its turn_profile string, falling back to *fallback* if unknown."""
    cfg = resolve_preset(preset)
    return cfg.turn_profile if cfg is not None else fallback


def preset_max_agents(preset: str | None) -> int | None:
    """Return the agent cap for a preset, or None if uncapped."""
    cfg = resolve_preset(preset)
    return cfg.max_agents if cfg is not None else None


def preset_catalog() -> dict[str, Any]:
    """Return preset info for /api/room/presets."""
    return {
        "presets": [
            {
                "id": cfg.preset,
                "turn_profile": cfg.turn_profile,
                "description": cfg.description,
                "max_agents": cfg.max_agents,
                "role_policy": cfg.role_policy,
            }
            for cfg in list_presets()
        ],
        "default": default_room_preset(),
    }
