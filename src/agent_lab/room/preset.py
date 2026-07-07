"""Room Preset System (P1-5) — named configurations mapping to Harness team patterns.

Two presets: fast (single-agent Q&A) and supervisor (multi-agent consensus + mission loop).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

from agent_lab.run.state import RunStateLike

RoomPreset = Literal["fast", "supervisor"]
RolePolicy = Literal["auto", "force", "off"]

_VALID_ROLE_POLICIES = frozenset({"auto", "force", "off"})


@dataclass(frozen=True, slots=True)
class RoomPresetConfig:
    preset: RoomPreset
    turn_profile: str
    description: str
    label: str
    max_agents: int | None = None  # None = no cap; set for presets with fixed team sizes
    role_policy: RolePolicy = "auto"  # force | auto | off — role assignment policy


_PRESET_CONFIGS: dict[str, RoomPresetConfig] = {
    "fast": RoomPresetConfig(
        preset="fast",
        turn_profile="quick",
        label="Fast",
        description="Single-agent instant response — no debate, no consensus",
        max_agents=1,
        role_policy="off",
    ),
    "supervisor": RoomPresetConfig(
        preset="supervisor",
        turn_profile="loop",
        label="Supervisor",
        description="Multi-agent consensus, plan, verify, and mission loop execute",
        role_policy="auto",
    ),
}


def normalize_role_policy(raw: str | None) -> RolePolicy:
    policy = (raw or "auto").strip().lower()
    if policy in _VALID_ROLE_POLICIES:
        return policy  # type: ignore[return-value]
    return "auto"


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


def resolve_preset_for_roster(
    preset: str | None,
    roster_size: int,
) -> tuple[str | None, str | None]:
    """§3.2.1: when roster exceeds preset max_agents, promote instead of silent truncate.

    Returns ``(effective_preset, promoted_from)``. ``promoted_from`` is set when
    fast (max_agents=1) is upgraded to supervisor because the user selected 2+ agents.
    """
    cfg = resolve_preset(preset)
    if cfg is None:
        return (preset.strip().lower() if preset else None), None
    cap = cfg.max_agents
    if cap is None or roster_size <= cap:
        return cfg.preset, None
    if cfg.preset == "fast":
        return "supervisor", "fast"
    return cfg.preset, None


def resolve_implicit_room_preset(
    topic: str,
    roster_size: int,
    *,
    run_meta: RunStateLike | None = None,
) -> str:
    """P2 TurnContract: derive room_preset when Composer sends no preset.

    Multi-agent rosters always use supervisor. Single-agent quick / anchored
    factual lookups map to fast; default dogfood path is supervisor.
    """
    if roster_size > 1:
        return "supervisor"
    text = (topic or "").strip()
    if roster_size == 1 and text:
        from agent_lab.clarity import clarity_short_circuit

        if clarity_short_circuit(text):
            return "fast"
        from agent_lab.topic_router import resolve_topic_route

        run = run_meta or {}
        route = resolve_topic_route(
            text,
            turn_profile=str(run.get("turn_profile") or ""),
            session_template=str(run.get("session_template") or ""),
        )
        if route.category == "quick":
            return "fast"
    return "supervisor"


def preset_role_policy(preset: str | None) -> RolePolicy:
    """Return role_policy for a preset name, defaulting to auto when unknown."""
    cfg = resolve_preset(preset)
    return cfg.role_policy if cfg is not None else "auto"


def resolve_role_policy(run_meta: RunStateLike | None) -> RolePolicy:
    """Session role policy: explicit run_meta.role_policy wins, else room_preset default."""
    if isinstance(run_meta, dict):
        raw = str(run_meta.get("role_policy") or "").strip().lower()
        if raw in _VALID_ROLE_POLICIES:
            return raw  # type: ignore[return-value]
        preset = str(run_meta.get("room_preset") or "").strip().lower()
        if preset:
            return preset_role_policy(preset)
    return "auto"


def is_fast_room_session(run_meta: RunStateLike | None) -> bool:
    """True for Fast preset / quick user_mode without loop plan intent.

    Orchestrator inbox harvest stays off on Fast; discuss-lane ``ask_human`` /
    ``propose_build`` MCP is allowed for the team lead. Execute lane inbox MCP unchanged.

    Product assumption (2026-06-26): Fast does not use clarify→plan→execute orchestration
    on the discuss lane. Plan-workflow CLARIFY inbox remains skipped.

    Docs: docs/05-room-agent-roles.md §Fast preset — orchestrator Inbox skip
    """
    if not isinstance(run_meta, dict):
        return False
    preset = str(run_meta.get("room_preset") or "").strip().lower()
    if preset == "fast":
        return True
    user_mode = str(run_meta.get("user_mode") or "").strip().lower()
    if user_mode != "quick":
        return False
    plan_intent = str(run_meta.get("plan_intent") or "none").strip().lower()
    return plan_intent in ("", "none")


def preset_catalog() -> dict[str, Any]:
    """Return preset info for /api/room/presets."""
    return {
        "presets": [
            {
                "id": cfg.preset,
                "label": cfg.label,
                "turn_profile": cfg.turn_profile,
                "description": cfg.description,
                "max_agents": cfg.max_agents,
                "role_policy": cfg.role_policy,
            }
            for cfg in list_presets()
        ],
        "default": default_room_preset(),
    }
