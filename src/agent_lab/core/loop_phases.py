"""Turn loop phases — §2.3 mission lifecycle slices (loop-as-data)."""

from __future__ import annotations

from enum import StrEnum


class TurnLoopPhase(StrEnum):
    """Room turn_flow phase boundaries (F9 decomposition target)."""

    ROUTING = "routing"
    CONSENSUS = "consensus"
    HARVEST = "harvest"
