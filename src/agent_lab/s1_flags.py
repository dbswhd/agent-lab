"""S1 flag resolution — supervisor preset implicit ON for feedback loop stack."""

from __future__ import annotations

from agent_lab.env_flags import is_falsy, is_truthy
from agent_lab.run.state import RunStateLike
import os

_SUPERVISOR_S1_FLAGS = frozenset(
    {
        "AGENT_LAB_TURN_METRICS",
        "AGENT_LAB_OUTCOME_LEDGER",
        "AGENT_LAB_FEEDBACK_ADVISOR",
    }
)


def _room_preset(*, room_preset: str = "", run_meta: RunStateLike | None = None) -> str:
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
    run_meta: RunStateLike | None = None,
) -> bool:
    """Env explicit OFF wins; explicit ON wins; supervisor preset defaults ON for S1 trio."""
    raw = os.getenv(name)
    if is_falsy(raw):
        return False
    if is_truthy(raw):
        return True
    if name in _SUPERVISOR_S1_FLAGS and _room_preset(room_preset=room_preset, run_meta=run_meta) == "supervisor":
        return True
    return False
