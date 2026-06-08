"""Pytest path: repo root so `app.server` imports work in CI and local venv."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_TESTS = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))


@pytest.fixture(autouse=True)
def _mock_goal_oracle_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep goal Oracle mock-first even when .env sets AGENT_LAB_GOAL_ORACLE_LIVE=1."""
    monkeypatch.delenv("AGENT_LAB_GOAL_ORACLE_LIVE", raising=False)
