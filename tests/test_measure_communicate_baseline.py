"""Smoke tests for communicate baseline measurement script."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "communicate-baseline-benchmark.json"


def test_communicate_baseline_fixture_exists():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert data["session_count"] >= 1
    assert "avg_agent_chars" in data
    assert data["total_parse_errors"] == 0


def test_measure_communicate_baseline_script_runs(tmp_path: Path):
    out = tmp_path / "baseline.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "measure_communicate_baseline.py"),
            "--sessions",
            str(ROOT / "sessions" / "_benchmark"),
            "--out",
            str(out),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert out.is_file()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["session_count"] >= 1
