"""External refs plan traceability — doc and evidence paths stay aligned."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACEABILITY = ROOT / "docs" / "EXTERNAL-REFS-TRACEABILITY.md"
PLAN = ROOT / "docs" / "EXTERNAL-REFS-PLAN.md"

# Minimum shipped rows: ID substring in traceability doc + at least one evidence path exists.
SHIPPED_ROWS: list[tuple[str, list[str]]] = [
    ("L1", ["src/agent_lab/cli_retry.py"]),
    ("L2", ["src/agent_lab/room_consensus.py"]),
    ("PI", ["src/agent_lab/plan_execute_worktree.py", "sessions/_regression/worktree_merge_ok"]),
    ("PI-ops", ["scripts/live_cursor_worktree_dry_run.py", "docs/OPS-RUNBOOK.md"]),
    ("PI-ops-C", ["scripts/live_cursor_worktree_merge_run.py", "docs/LIVE-MERGE-OPERATOR.md"]),
    ("E-smoke", ["scripts/smoke_room.py", "sessions/_regression/objection_blocks_execute"]),
    ("F-R3", ["sessions/_benchmark/specialist_asymmetric_cwd"]),
    ("H-P1", ["tests/test_session_score_ci.py"]),
    ("H4-weekly", ["scripts/score_sessions_weekly.py"]),
    ("H4-ops-live", ["tests/test_weekly_live_ops_summary.py"]),
    ("ops-P2", ["app/server/routers/health.py"]),
    ("ops-verify", ["Makefile", "docs/OPS-RUNBOOK.md"]),
    (
        "LC-L4",
        [
            "src/agent_lab/adversarial_gate.py",
            "sessions/_regression/adversarial_gate_lgtm",
        ],
    ),
]

FUTURE_TICKETS = (
    "execute_verify_loop",
    "durable_completed_steps",
)

LAYER_FUTURE_MARKERS = (
    "Layer 3: Execute Verify Loop",
    "Layer 4: Adversarial Gate",
)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing doc: {path}"
    return path.read_text(encoding="utf-8")


def test_traceability_doc_exists_and_links_plan():
    text = _read(TRACEABILITY)
    assert "EXTERNAL-REFS-PLAN.md" in text
    assert "Status legend" in text or "✅ shipped" in text


def test_shipped_rows_have_existing_evidence():
    text = _read(TRACEABILITY)
    for row_id, paths in SHIPPED_ROWS:
        assert row_id in text, f"traceability missing row id {row_id}"
        found = any((ROOT / p).exists() for p in paths)
        assert found, f"{row_id}: none of {paths} exist"


def test_future_fixture_tickets_documented():
    text = _read(TRACEABILITY)
    for ticket in FUTURE_TICKETS:
        assert ticket in text


def test_plan_has_stale_banner_and_traceability_link():
    text = _read(PLAN)
    assert "EXTERNAL-REFS-TRACEABILITY.md" in text
    assert "Stale notice" in text or "shipped" in text.lower()


def test_plan_layer_three_four_still_marked_unimplemented():
    text = _read(PLAN)
    for marker in LAYER_FUTURE_MARKERS:
        assert marker in text
    # End table should still show Layer 3/4 as not implemented
    assert "Layer 3: Execute Verify Loop | ❌" in text or "❌ 미구현" in text


def test_plan_phase_three_ops_marked_shipped_in_traceability():
    text = _read(TRACEABILITY)
    assert "ops-P2" in text
    assert "ops-P0" in text
    assert "H-P1" in text


def test_traceability_future_tickets_not_in_regression_yet():
    regression = ROOT / "sessions" / "_regression"
    for ticket in FUTURE_TICKETS:
        assert not (regression / ticket).is_dir(), f"{ticket} should not exist yet"


def test_adversarial_gate_lgtm_fixture_exists():
    fixture = ROOT / "sessions" / "_regression" / "adversarial_gate_lgtm"
    assert fixture.is_dir()
    assert (fixture / "run.json").is_file()
    assert (fixture / "expected_badges.json").is_file()
