"""Shared orchestration exceptions — no room/runtime imports."""

from __future__ import annotations

from typing import Any


class PreExecuteBlocked(Exception):
    """pre_execute hook blocked dry-run."""

    def __init__(self, message: str, *, pre_verify: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.pre_verify = pre_verify or {}


class ObjectionBlocksExecute(Exception):
    """Open BLOCK targets this plan action — dry-run / execute must not proceed."""

    def __init__(self, message: str, *, objections: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.objections = objections or []
