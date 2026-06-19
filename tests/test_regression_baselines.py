"""Regression baseline contracts under code + stable fixtures."""

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


def test_regression_run_meta_write_import():
    mod = importlib.import_module("agent_lab.run_meta")
    assert hasattr(mod, "write_run_meta")
    assert hasattr(mod, "patch_run_meta")
    assert callable(mod.write_run_meta)
    assert callable(mod.patch_run_meta)


def test_regression_run_schema_validation():
    mod = importlib.import_module("agent_lab.run_schema")
    assert hasattr(mod, "validate_run")
    bad = {"phase": "BAD", "executions": [{"status": "BAD"}], "pending_action_indices": "not-a-list"}
    raised = False
    try:
        mod.validate_run(bad)
    except Exception as exc:
        raised = True
        msg = str(exc)
    assert raised is True
    assert msg != ""
