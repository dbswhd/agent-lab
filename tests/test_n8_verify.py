"""N8 Layer 3 — quickstart verify + emergence bench reference reproducibility."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_verify_emergence():
    spec = importlib.util.spec_from_file_location(
        "verify_emergence_bench_reference",
        ROOT / "scripts" / "verify_emergence_bench_reference.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_compare_by_category_matches_reference():
    mod = _load_verify_emergence()
    ref_path = ROOT / "sessions" / "_benchmark" / "reports" / "emergence-bench-reference-mock-20260706.json"
    ref = json.loads(ref_path.read_text(encoding="utf-8"))
    assert mod.compare_by_category(ref, ref) == []


def test_compare_by_category_detects_drift():
    mod = _load_verify_emergence()
    ref = {"by_category": {"quick": {"topics": 1, "delta_mean": -0.125, "delta_positive": 0}}}
    got = {"by_category": {"quick": {"topics": 1, "delta_mean": 0.5, "delta_positive": 1}}}
    assert mod.compare_by_category(got, ref)


@pytest.mark.integration
def test_emergence_bench_reference_check():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_emergence_bench_reference.py"), "--check"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]


def test_quickstart_verify_smoke_only():
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "verify_quickstart.py"),
            "--skip-mission",
            "--json",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    report = json.loads(proc.stdout)
    assert report["ok"] is True
    assert report["fork_time_seconds"] >= 0
