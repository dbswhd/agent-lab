from __future__ import annotations

from pathlib import Path

from scripts.mission_dual_write_evidence import run_cohort


def test_dual_write_cohort_covers_ten_sessions_and_recovery_contracts(tmp_path: Path) -> None:
    report = run_cohort(tmp_path / "sessions")

    assert report["session_count"] == 10
    assert report["scenario_counts"] == {
        "plan_reject_revisit": 2,
        "execute_success_merge_oracle_pass": 2,
        "oracle_fail_repair": 2,
        "human_inbox_pause_resume": 2,
        "daemon_crash_recovery": 2,
    }
    assert report["parity_pass"] is True
    assert report["side_effect_single_execution"] is True
    assert report["restart_replay_pass"] is True
    assert report["reconnect_pass"] is True
    assert report["human_inbox_resume_pass"] is True
    assert all(row["same_session_identity"] for row in report["sessions"])
