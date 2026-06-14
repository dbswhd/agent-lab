"""Mock room E2E smoke (discoverable pytest wrapper for scripts/smoke_room_e2e.py)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "smoke_room_e2e.py"


def _load_smoke_e2e():
    spec = importlib.util.spec_from_file_location("smoke_room_e2e", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_mock_discuss_turn_e2e(monkeypatch):
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    smoke = _load_smoke_e2e()
    code, errors = smoke.run_mock_discuss_turn()
    assert code == 0, "\n".join(errors)
