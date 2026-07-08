"""HS4 — scripts/regress_harness.py CLI smoke tests (mock-only, subprocess)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "regress_harness.py"


def _run(args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    full_env = {**os.environ, "AGENT_LAB_RUN_PROFILE": "balanced"}
    full_env.pop("AGENT_LAB_MOCK_AGENTS", None)
    full_env.pop("AGENT_LAB_REGRESSION_GATE", None)
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        cwd=_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=full_env,
    )


def test_flag_off_exits_2(tmp_path):
    proc = _run(["--candidate-id", "x", "--diff-path", "y.patch"])
    assert proc.returncode == 2
    assert "AGENT_LAB_REGRESSION_GATE=0" in proc.stderr


def test_missing_candidate_reports_failure(tmp_path):
    proc = _run(
        ["--candidate-id", "nonexistent", "--diff-path", str(tmp_path / "x.patch"), "--root", str(tmp_path)],
        env={"AGENT_LAB_REGRESSION_GATE": "1"},
    )
    # load_candidate() raises FileNotFoundError — CLI should exit nonzero, not crash silently.
    assert proc.returncode != 0


def test_end_to_end_via_propose_then_regress(tmp_path):
    """propose_harness.py --mode propose, then regress_harness.py against it."""
    # A prior test elsewhere in this worker may have leaked AGENT_LAB_MOCK_AGENTS=1
    # via raw os.environ (run_dogfood_suite.run_mock() sets it without monkeypatch,
    # never unset) — clear it so this subprocess isn't blocked by the STOP guard.
    propose_env = {**os.environ, "AGENT_LAB_RUN_PROFILE": "balanced"}
    propose_env.pop("AGENT_LAB_MOCK_AGENTS", None)
    propose_proc = subprocess.run(
        [
            sys.executable,
            str(_ROOT / "scripts" / "propose_harness.py"),
            "--mode",
            "propose",
            "--root",
            str(tmp_path),
            "--pattern-id",
            "fp:weak_taste:standard",
            "--axis",
            "profile",
            "--files",
            "src/agent_lab/run/profile.py",
            "--diff-ref",
            "x.patch",
            "--assertions",
            "tests/test_x.py::test_x",
        ],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        env=propose_env,
    )
    assert propose_proc.returncode == 0, propose_proc.stderr
    candidate_id = propose_proc.stdout.split("proposed: ")[1].split(" ")[0]

    # No real diff file at diff_ref -> regress must reject cleanly, not crash.
    regress_proc = _run(
        ["--candidate-id", candidate_id, "--diff-path", str(tmp_path / "x.patch"), "--root", str(tmp_path)],
        env={"AGENT_LAB_REGRESSION_GATE": "1"},
    )
    assert regress_proc.returncode == 1
    assert "verdict: fail" in regress_proc.stdout
    assert "diff file not found" in regress_proc.stdout
