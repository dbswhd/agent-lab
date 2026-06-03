"""Makefile ops verification target wiring."""

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


def test_verify_ops_dry_run_wires_ci_orphans_and_weekly_report():
    out = _make_dry_run("verify-ops")

    assert "make ci" in out
    assert "scripts/check_worktree_orphans.py" in out
    assert "make score-weekly" in out
    assert "--write-artifacts" in out
    assert "Ops report:" in out


def test_verify_ops_report_zero_skips_weekly_artifact():
    out = _make_dry_run("verify-ops", "REPORT=0")

    assert "make ci" in out
    assert "scripts/check_worktree_orphans.py" in out
    assert "Ops report: skipped (REPORT=0)" in out
    assert "--write-artifacts" not in out


def test_verify_ops_strict_and_fixture_flags_reach_score_weekly():
    out = _make_dry_run("verify-ops", "INCLUDE_FIXTURES=1", "STRICT=1")

    assert "INCLUDE_FIXTURES=1" in out
    assert "STRICT=1" in out
    assert "--include-fixtures" in out
    assert "--strict" in out
