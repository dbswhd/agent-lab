"""Read-only execute benchmark cross-references (H-P2)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGRESSION = ROOT / "sessions" / "_regression"


def _run(name: str) -> dict:
    return json.loads((REGRESSION / name / "run.json").read_text(encoding="utf-8"))


def test_e5_snapshot_override_pending_fixture():
    run = _run("snapshot_override_pending")
    rows = run["executions"]

    assert any(
        row.get("status") == "pending_approval"
        and row.get("isolation_effective") == "snapshot_override"
        and row.get("isolation_override_by") == "human"
        for row in rows
    )


def test_e8_pre_execute_blocked_fixture():
    run = _run("pre_execute_blocked")
    rows = run["executions"]

    assert any(
        row.get("status") == "blocked_isolation"
        and isinstance(row.get("pre_verify"), dict)
        and row["pre_verify"].get("blocked") is True
        for row in rows
    )
