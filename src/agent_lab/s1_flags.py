"""S1 flag resolution — supervisor preset implicit ON for feedback loop stack."""

from __future__ import annotations

from agent_lab.env_flags import is_falsy, is_truthy
from agent_lab.run.state import RunStateLike
import os

# Post-turn, write-only observability (outcome_harvester.record_turn_outcome, called
# from _finalize_durable_turn after the round is done) — doesn't sit in the fast-turn
# latency path, so the raw (now effectively always-"supervisor") preset default-on is
# fine here; broader coverage across all real traffic is the point of S1 observability.
_SUPERVISOR_S1_FLAGS = frozenset(
    {
        "AGENT_LAB_TURN_METRICS",
        "AGENT_LAB_OUTCOME_LEDGER",
    }
)

# Pre-turn, latency-sensitive work (feedback_advisor.advise_setup reads outcomes.jsonl
# and runs history-based role-combo exploration before the agent round starts) — this
# must respect the real per-turn fast/supervisor classification, not the constant
# implicit preset, or every fast/quick turn pays for it too (TurnContract §8.2 P2).
_TURN_SIGNAL_S1_FLAGS = frozenset({"AGENT_LAB_FEEDBACK_ADVISOR"})


def _room_preset(*, room_preset: str = "", run_meta: RunStateLike | None = None) -> str:
    preset = (room_preset or "").strip().lower()
    if preset:
        return preset
    if isinstance(run_meta, dict):
        return str(run_meta.get("room_preset") or "").strip().lower()
    return ""


def _is_supervisor_turn(*, room_preset: str = "", run_meta: RunStateLike | None = None) -> bool:
    from agent_lab.room.turn_policy import is_supervisor_turn_with_preset_fallback

    preset = _room_preset(room_preset=room_preset, run_meta=run_meta)
    return is_supervisor_turn_with_preset_fallback(run_meta, room_preset=preset)


def s1_flag_enabled(
    name: str,
    *,
    room_preset: str = "",
    run_meta: RunStateLike | None = None,
) -> bool:
    """Env explicit OFF wins; explicit ON wins; supervisor preset/turn defaults ON for S1 trio."""
    raw = os.getenv(name)
    if is_falsy(raw):
        return False
    if is_truthy(raw):
        return True
    if name in _SUPERVISOR_S1_FLAGS and _room_preset(room_preset=room_preset, run_meta=run_meta) == "supervisor":
        return True
    if name in _TURN_SIGNAL_S1_FLAGS and _is_supervisor_turn(room_preset=room_preset, run_meta=run_meta):
        return True
    return False
