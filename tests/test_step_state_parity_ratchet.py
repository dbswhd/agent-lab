"""Characterization ratchet: mission_loop.phase vs execution-row step-state parity.

Read-only audit (scripts/step_state_parity_audit.py) over sessions/_regression/*.
Does not assert the two signals must agree -- only that no *new* disagreement
appears beyond the recorded baseline (tests/fixtures/step-state-parity-baseline.json).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "tests" / "fixtures" / "step-state-parity-baseline.json"


def test_step_state_parity_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/step_state_parity_audit.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_step_state_parity_baseline_documents_known_gaps() -> None:
    """The two known repair-count drifts stay pinned and named, not silently dropped."""
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    fixtures_with_drift = {row["fixture"] for row in baseline["repair_mismatches"]}
    assert fixtures_with_drift == {"mission_loop_discuss_recovery", "mission_loop_verify_repair"}
    assert baseline["phase_mismatches"] == []
    assert baseline["unmapped_statuses"] == []
