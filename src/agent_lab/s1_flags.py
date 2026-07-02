"""S1 flag resolution — supervisor preset implicit ON for feedback loop stack."""

from __future__ import annotations

import os
from typing import Any

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})

_SUPERVISOR_S1_FLAGS = frozenset(
    {
        "AGENT_LAB_TURN_METRICS",
        "AGENT_LAB_OUTCOME_LEDGER",
        "AGENT_LAB_FEEDBACK_ADVISOR",
    }
)


def _room_preset(*, room_preset: str = "", run_meta: dict[str, Any] | None = None) -> str:
    preset = (room_preset or "").strip().lower()
    if preset:
        return preset
    if isinstance(run_meta, dict):
        return str(run_meta.get("room_preset") or "").strip().lower()
    return ""


def s1_flag_enabled(
    name: str,
    *,
    room_preset: str = "",
    run_meta: dict[str, Any] | None = None,
) -> bool:
    """Env explicit OFF wins; explicit ON wins; supervisor preset defaults ON for S1 trio."""
    raw = (os.getenv(name) or "").strip().lower()
    if raw in _FALSE:
        return False
    if raw in _TRUE:
        return True
    if name in _SUPERVISOR_S1_FLAGS and _room_preset(room_preset=room_preset, run_meta=run_meta) == "supervisor":
        return True
    return False
