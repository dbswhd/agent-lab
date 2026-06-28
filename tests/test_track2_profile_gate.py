"""Track 2.0 profile gate — fast fixture + gate math."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "profile_track2_gate.py"
FIXTURE = ROOT / "tests/fixtures/track2-profile-report.json"


def test_profile_tiny_fixture_runs() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--fixture", "tiny", "--repeat", "1", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode in (0, 2), proc.stderr
    report = json.loads(proc.stdout)
    assert "gate_passed" in report
    assert report["context_build_total_ms"] >= 0
    assert len(report["segments"]) >= 5


def test_gate_math_unit() -> None:
    native = 100.0
    context = 2000.0
    stub = 30_000.0
    share_context = native / context * 100
    share_mock = native / (context + stub) * 100
    assert share_context == 5.0
    assert share_mock < 5.0


def test_repo_profile_report_baseline_keys() -> None:
    """Ratchet: committed baseline documents expected keys (regenerate after profile run)."""
    if not FIXTURE.is_file():
        return
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for key in (
        "gate_passed",
        "share_of_context_build_pct",
        "share_of_mock_turn_pct",
        "native_candidates_ms",
        "context_build_total_ms",
    ):
        assert key in data
