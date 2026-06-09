"""Result envelope for ``AgentLabRuntime.dispatch``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DispatchResult:
    handled: bool
    skipped: bool = False
    reason: str | None = None
    result: Any = None
    phase: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
