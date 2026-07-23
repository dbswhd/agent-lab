from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts"))

from dogfood_readiness_manifest import load_manifest
from dogfood_readiness_packet import build_readiness_packet, render_markdown


def _write_run(path: Path, *, repair: bool) -> None:
    oracle = {
        "verdict": "pass",
        "source": "mock",
        "evidence": ["pytest passed"],
        "checked_paths": ["tests/test_example.py"],
        "checked_at": "2026-07-24T00:00:06+00:00",
    }
    execution = {
        "id": "exec-repair" if repair else "exec-success",
        "status": "merged",
        "oracle": oracle,
        "verify_retries": 1 if repair else 0,
        "repair_history": [],
        "verify_history": [{"attempt": 0, "oracle": oracle}],
    }
    if repair:
        execution["repair_history"] = [
            {
                "attempt": 1,
                "oracle_before": {"verdict": "fail"},
                "oracle_after": oracle,
            }
        ]
        execution["verify_history"] = [
            {"attempt": 0, "oracle": {"verdict": "fail"}},
            {"attempt": 1, "oracle": oracle},
        ]
    path.write_text(json.dumps({"executions": [execution]}), encoding="utf-8")


def _write_manifest(tmp_path: Path) -> Path:
    success = tmp_path / "success.json"
    repair = tmp_path / "repair.json"
    browser = tmp_path / "wave-b.txt"
    _write_run(success, repair=False)
    _write_run(repair, repair=True)
    browser.write_text("4 passed", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "owner": "dogfood-owner",
        "commit_sha": "a" * 40,
        "window": {
            "started_at": "2026-07-24T00:00:00+00:00",
            "ended_at": "2026-07-24T01:00:00+00:00",
        },
        "flags": {"AGENT_LAB_MISSION_AUTHORITY": "0"},
        "cohort_ids": ["cohort-a"],
        "evidence": [
            {
                "id": "wave-b",
                "tier": "browser",
                "status": "PASS",
                "sample_size": 4,
                "raw_paths": [str(browser)],
            },
            {
                "id": "live-dogfood",
                "tier": "live",
                "status": "OPEN",
                "sample_size": 0,
                "raw_paths": [],
                "owner": "dogfood-owner",
                "next_gate": "run credentialed supervisor session",
            },
        ],
        "sessions": [
            {"id": "success", "tier": "mock", "kind": "success", "run_path": str(success)},
            {"id": "repair", "tier": "mock", "kind": "repair", "run_path": str(repair)},
        ],
        "gate_events": [
            {
                "id": "plan-approval",
                "opened_at": "2026-07-24T00:00:01+00:00",
                "closed_at": "2026-07-24T00:00:06+00:00",
            }
        ],
        "parity": {
            "cohort": {"sample_size": 2, "successes": 2},
            "noncohort": {"sample_size": 2, "successes": 2},
        },
        "operational_gates": [
            {
                "id": "F7",
                "status": "OPEN",
                "owner": "dogfood-owner",
                "next_gate": "record Human ON/OFF decision",
                "raw_paths": [str(success)],
            },
            {
                "id": "N4-D3",
                "status": "deferred",
                "owner": "dogfood-owner",
                "next_gate": "collect L2 samples",
                "raw_paths": [],
            },
            {
                "id": "HS-M5",
                "status": "OPEN",
                "owner": "dogfood-owner",
                "next_gate": "merge one Human-approved patch",
                "raw_paths": [],
            },
        ],
        "thresholds": {
            "oracle_coverage_min": 1.0,
            "false_success_max": 0,
            "retry_cap": 2,
            "parity_gap_max": 0.05,
        },
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_packet_separates_evidence_tiers_and_preserves_repair_chain(tmp_path: Path) -> None:
    # Given
    manifest = load_manifest(_write_manifest(tmp_path))

    # When
    packet = build_readiness_packet(manifest)

    # Then
    assert packet["evidence_by_tier"]["browser"]["status"] == "PASS"
    assert packet["evidence_by_tier"]["live"]["status"] == "OPEN"
    assert packet["metrics"]["oracle_coverage"] == 1.0
    assert packet["metrics"]["false_success_count"] == 0
    assert packet["metrics"]["repair_attempts"] == 1
    assert packet["metrics"]["retry_plateau_sessions"] == 0
    assert packet["metrics"]["gate_latency_seconds"]["max"] == 5.0
    assert packet["metrics"]["cohort_noncohort_success_gap"] == 0.0
    assert packet["readiness"] == "OPEN"


def test_packet_requires_raw_artifact_for_pass_evidence(tmp_path: Path) -> None:
    # Given
    path = _write_manifest(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["evidence"][0]["raw_paths"] = []
    path.write_text(json.dumps(payload), encoding="utf-8")

    # When / Then
    with pytest.raises(ValueError, match="PASS evidence requires"):
        load_manifest(path)


def test_markdown_names_flags_cohorts_paths_and_open_gate(tmp_path: Path) -> None:
    # Given
    packet = build_readiness_packet(load_manifest(_write_manifest(tmp_path)))

    # When
    markdown = render_markdown(packet)

    # Then
    assert "AGENT_LAB_MISSION_AUTHORITY=0" in markdown
    assert "cohort-a" in markdown
    assert "wave-b.txt" in markdown
    assert "F7 | OPEN" in markdown
    assert "No default change is authorized by this packet." in markdown
