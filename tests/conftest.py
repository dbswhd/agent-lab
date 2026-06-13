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

for _qat_src in (
    Path.home() / "Projects" / "quant-agentic-trading" / "src",
    Path.home() / "Documents" / "New project" / "src",
):
    if _qat_src.is_dir() and str(_qat_src) not in sys.path:
        sys.path.insert(0, str(_qat_src.resolve()))
        break


@pytest.fixture(autouse=True)
def _mock_goal_oracle_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep goal Oracle mock-first even when .env sets AGENT_LAB_GOAL_ORACLE_LIVE=1."""
    monkeypatch.delenv("AGENT_LAB_GOAL_ORACLE_LIVE", raising=False)


@pytest.fixture(autouse=True)
def _reset_run_control_cancel() -> None:
    """Prevent cancel flag / child registry leaking across tests."""
    from agent_lab.run_control import clear_cancel, terminate_active_children

    clear_cancel()
    terminate_active_children()
    yield
    clear_cancel()
    terminate_active_children()
