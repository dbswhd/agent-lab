"""Regression baseline fixtures under sessions/_regression/."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "smoke_room.py"


def _load_smoke_room():
    spec = importlib.util.spec_from_file_location("smoke_room", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_regression_baselines_pass():
    smoke = _load_smoke_room()
    code, errors = smoke.validate_regression_fixtures()
    assert code == 0, "\n".join(errors)
