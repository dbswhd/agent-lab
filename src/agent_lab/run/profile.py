"""Run Profile System (P1-6) — four named flag presets that simplify 108 flags.

Four profiles cover the main operational modes. Individual AGENT_LAB_* overrides
always take precedence over profile defaults (profiles only fill in unset flags).

Profiles:
  fast        — single agent, auto-approve low-risk, Oracle mock
  balanced    — supervisor preset, human gate, Oracle live (default)
  thorough    — supervisor + adversarial + live judge, human gate, Oracle live
  autonomous  — mission loop + auto-approve medium-risk, Oracle live
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal

RunProfile = Literal["fast", "balanced", "thorough", "autonomous"]


@dataclass(frozen=True, slots=True)
class RunProfileConfig:
    profile: RunProfile
    description: str
    flags: dict[str, str] = field(default_factory=dict)


_PROFILE_CONFIGS: dict[str, RunProfileConfig] = {
    "fast": RunProfileConfig(
        profile="fast",
        description="Single-agent, auto-approve low-risk changes, Oracle mock — fastest throughput",
        flags={
            "AGENT_LAB_ROOM_PRESET": "fast",
            "AGENT_LAB_AUTO_APPROVE_THRESHOLD": "low",
            "AGENT_LAB_AUTO_APPROVE_TIMEOUT_SEC": "0",
            "AGENT_LAB_ORACLE_LIVE": "",
            "AGENT_LAB_ADVERSARIAL_LIVE": "",
            "AGENT_LAB_JUDGE_LIVE": "",
        },
    ),
    "balanced": RunProfileConfig(
        profile="balanced",
        description="Supervisor preset, human gate on every change, Oracle live — safe default",
        flags={
            "AGENT_LAB_ROOM_PRESET": "supervisor",
            "AGENT_LAB_ORACLE_LIVE": "1",
            "AGENT_LAB_ADVERSARIAL_LIVE": "",
            "AGENT_LAB_JUDGE_LIVE": "",
        },
    ),
    "thorough": RunProfileConfig(
        profile="thorough",
        description="Supervisor + adversarial gate + live judge — maximum verification",
        flags={
            "AGENT_LAB_ROOM_PRESET": "supervisor",
            "AGENT_LAB_ORACLE_LIVE": "1",
            "AGENT_LAB_ADVERSARIAL_LIVE": "1",
            "AGENT_LAB_JUDGE_LIVE": "1",
        },
    ),
    "autonomous": RunProfileConfig(
        profile="autonomous",
        description="Mission loop + auto-approve medium-risk, Oracle live — trusted autonomous mode",
        flags={
            "AGENT_LAB_ROOM_PRESET": "supervisor",
            "AGENT_LAB_AUTO_APPROVE_THRESHOLD": "medium",
            "AGENT_LAB_AUTO_APPROVE_TIMEOUT_SEC": "30",
            "AGENT_LAB_MISSION_LOOP": "1",
            "AGENT_LAB_ORACLE_LIVE": "1",
            "AGENT_LAB_ADVERSARIAL_LIVE": "",
            "AGENT_LAB_JUDGE_LIVE": "",
        },
    ),
}

def resolve_profile(profile: str | None) -> RunProfileConfig | None:
    """Return the config for a profile name, or None if unknown/unset."""
    if not profile:
        return None
    return _PROFILE_CONFIGS.get(profile.strip().lower())


def default_run_profile() -> str | None:
    """Return the profile name from AGENT_LAB_RUN_PROFILE env var, or None."""
    raw = (os.getenv("AGENT_LAB_RUN_PROFILE") or "").strip().lower()
    return raw if resolve_profile(raw) is not None else None


def apply_run_profile(profile: str | None, *, overwrite: bool = False) -> dict[str, str]:
    """Apply profile flag defaults to os.environ.

    Only sets flags that are not already set in the environment unless
    *overwrite=True* is passed. Returns the dict of flags that were applied.
    """
    cfg = resolve_profile(profile)
    if cfg is None:
        return {}
    applied: dict[str, str] = {}
    for name, value in cfg.flags.items():
        if overwrite or os.getenv(name) is None:
            if value:
                os.environ[name] = value
            elif name in os.environ:
                del os.environ[name]
            applied[name] = value
    return applied


def list_profiles() -> list[RunProfileConfig]:
    """Return all available run profiles in display order."""
    return list(_PROFILE_CONFIGS.values())


def profile_catalog() -> dict[str, Any]:
    """Return profile info for /api/profiles."""
    active = default_run_profile()
    return {
        "profiles": [
            {
                "id": cfg.profile,
                "description": cfg.description,
                "flags": cfg.flags,
            }
            for cfg in list_profiles()
        ],
        "default": active,
        "active": active,
    }
