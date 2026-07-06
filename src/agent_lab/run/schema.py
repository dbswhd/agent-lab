"""Runtime schema validation for run.json state."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_lab.run.state import (
    RuntimeValidationError,
    validate_run_data,
    _VALID_EXECUTION_STATUSES,
    _VALID_MISSION_PHASES,
)

__all__ = [
    "RuntimeValidationError",
    "validate_run",
    "_VALID_EXECUTION_STATUSES",
    "_VALID_MISSION_PHASES",
]


def validate_run(run: Mapping[str, Any]) -> None:
    validate_run_data(run)
