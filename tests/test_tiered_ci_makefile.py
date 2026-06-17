"""Tiered CI Makefile targets (M4)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _make_dry_run(*args: str) -> str:
    env = os.environ.copy()
    for key in ("REPORT", "STRICT", "INCLUDE_FIXTURES", "DAYS", "MAKEFLAGS", "MFLAGS", "MAKELEVEL"):
        env.pop(key, None)
    result = subprocess.run(
        ["make", "-n", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_test_fast_excludes_integration_marker():
    out = _make_dry_run("test-fast")
    assert "not live and not integration and not bridge" in out


def test_test_fast_uses_parallel_pytest_when_xdist_installed():
    out = _make_dry_run("test-fast")
    assert "not live and not integration and not bridge" in out
    assert "import xdist" in out or "-n" in out


def test_ci_uses_test_fast():
    out = _make_dry_run("ci")
    assert "not live and not integration and not bridge" in out
    assert "smoke" in out


def test_ci_full_runs_split_verification_lanes():
    out = _make_dry_run("ci-full")
    assert "run_verification_lane.py --lane ci_full" in out
    assert "test-fast test-integration test-bridge" in out


def test_verify_ops_wires_bridge_check():
    out = _make_dry_run("verify-ops", "REPORT=0")
    assert "check_bridge_processes.py" in out
    assert "ci-full" in out
