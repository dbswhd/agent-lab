"""R1 (05-reliability-evaluation-operations.md) — journey reliability matrix
stays linked to real fixtures.

Guards docs/redesign-2026-07/evidence/r1-journey-reliability-matrix-2026-07-16.md
§1: every sessions/_regression/* fixture named against a journey must still
exist on disk (R1 acceptance criteria: "CI가 matrix의 fixture/test link
존재를 검사한다"), and the one confirmed gap (no cancel fixture) stays
pinned so it can't silently get "fixed" by a stale doc claim.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGRESSION_DIR = ROOT / "sessions" / "_regression"

JOURNEY_FIXTURES = {
    "start": ("discuss", "review-on", "category_escalation_quick_to_deep", "dispatch_parallel_explore"),
    "plan": (
        "plan",
        "plan_workflow_approved",
        "plan_workflow_pw5_latency",
        "objection_blocks_execute",
        "challenge_revises_metric",
        "mission_loop_plan_reject",
        "mission_loop_execute_queue",
    ),
    "execute": (
        "worktree_merge_ok",
        "worktree_reject",
        "worktree_unavailable",
        "worktree_apply",
        "snapshot_override_pending",
        "pre_execute_blocked",
        "adversarial_gate_lgtm",
    ),
    "diff": ("merge_conflict", "ui_pending_diff"),
    "verify": ("execute_verify_loop", "evidence_gates_merged_ok", "evidence_ledger_stream", "mission_loop_verify_repair"),
    "repair": ("execute_verify_loop", "mission_loop_verify_repair"),
    "resume": ("durable_completed_steps", "mission_loop_paused", "mission_loop_circuit_breaker", "mission_loop_discuss_recovery"),
    # cancel: intentionally empty — see §3 of the matrix doc, R2's first slice.
}


def test_all_journey_fixtures_exist_on_disk() -> None:
    missing: list[str] = []
    for journey, fixtures in JOURNEY_FIXTURES.items():
        for fixture in fixtures:
            if not (REGRESSION_DIR / fixture).is_dir():
                missing.append(f"{journey}: {fixture}")
    assert not missing, f"R1 matrix references missing sessions/_regression fixture(s): {missing}"


def test_cancel_journey_still_has_no_regression_fixture() -> None:
    """Pins the R1 finding — fails loudly (telling you to update the matrix doc
    too) once someone adds sessions/_regression/cancel*."""
    cancel_like = [p.name for p in REGRESSION_DIR.iterdir() if p.is_dir() and "cancel" in p.name.lower()]
    assert cancel_like == [], (
        f"found cancel-like regression fixture(s) {cancel_like} — update "
        "r1-journey-reliability-matrix-2026-07-16.md §1/§3, this gap is now closed"
    )
