from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TypeAlias

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts"))

from dogfood_readiness_manifest import ReadinessManifest, load_manifest
from dogfood_readiness_packet import build_readiness_packet

JsonValue: TypeAlias = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)


def _write_mock_run(path: Path, *, repair: bool) -> None:
    oracle = {
        "verdict": "pass",
        "source": "mock",
        "evidence": ["pytest passed"],
        "checked_paths": ["tests/test_example.py"],
    }
    execution = {
        "id": "exec-repair" if repair else "exec-success",
        "status": "merged",
        "oracle": oracle,
        "repair_history": [
            {"attempt": 1, "oracle_before": {"verdict": "fail"}, "oracle_after": oracle}
        ]
        if repair
        else [],
    }
    path.write_text(json.dumps({"executions": [execution]}), encoding="utf-8")


def _write_base_manifest(tmp_path: Path) -> dict[str, JsonValue]:
    success = tmp_path / "success.json"
    repair = tmp_path / "repair.json"
    browser = tmp_path / "wave-b.txt"
    _write_mock_run(success, repair=False)
    _write_mock_run(repair, repair=True)
    browser.write_text("4 passed", encoding="utf-8")
    return {
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
            {"id": "wave-b", "tier": "browser", "status": "PASS", "sample_size": 4, "raw_paths": [str(browser)]},
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
            {"id": gate_id, "status": "PASS", "owner": "dogfood-owner", "next_gate": "complete", "raw_paths": [str(success)]}
            for gate_id in ("F7", "N4-D3", "HS-M5")
        ],
        "thresholds": {
            "oracle_coverage_min": 1.0,
            "false_success_max": 0,
            "retry_cap": 2,
            "parity_gap_max": 0.05,
        },
    }


def _live_pass_payload(
    tmp_path: Path,
    *,
    evidence: list[str],
    checked_paths: list[str],
    sample_size: int,
    session_id: str | None = None,
    commit_sha: str | None = None,
) -> tuple[dict[str, JsonValue], Path]:
    payload = _write_base_manifest(tmp_path)
    run_path = tmp_path / "live-session" / "run.json"
    run_path.parent.mkdir()
    run: dict[str, JsonValue] = {
        "executions": [
            {
                "id": "exec-live",
                "status": "merged",
                "oracle": {
                    "verdict": "pass",
                    "source": "real-oracle",
                    "evidence": evidence,
                    "checked_paths": checked_paths,
                },
            }
        ]
    }
    if session_id is not None:
        run["session_id"] = session_id
    if commit_sha is not None:
        run["commit_sha"] = commit_sha
    run_path.write_text(json.dumps(run), encoding="utf-8")
    payload["evidence"][1] = {
        "id": "credentialed-live-dogfood",
        "tier": "live",
        "status": "PASS",
        "sample_size": sample_size,
        "raw_paths": [str(run_path)],
    }
    payload["sessions"].append(
        {"id": "live-session", "tier": "live", "kind": "success", "run_path": str(run_path)}
    )
    return payload, run_path


def test_live_pass_rejects_forged_real_oracle_without_evidence_even_when_threshold_allows_it(
    tmp_path: Path,
) -> None:
    # Given
    payload, path = _live_pass_payload(tmp_path, evidence=[], checked_paths=[], sample_size=10)
    payload["thresholds"]["false_success_max"] = 1
    manifest_path = tmp_path / "forged-manifest.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    # When / Then
    with pytest.raises(ValueError, match="live PASS requires non-empty Oracle evidence"):
        load_manifest(manifest_path)


def test_packet_keeps_false_success_open_when_manifest_threshold_is_raised(tmp_path: Path) -> None:
    # Given
    payload, _path = _live_pass_payload(tmp_path, evidence=[], checked_paths=[], sample_size=10)
    payload["thresholds"]["false_success_max"] = 1
    manifest = ReadinessManifest.model_validate(payload)

    # When
    packet = build_readiness_packet(manifest)

    # Then
    assert packet["metrics"]["false_success_count"] == 1
    assert packet["readiness"] == "OPEN"


def test_live_pass_requires_run_session_and_commit_provenance_binding(tmp_path: Path) -> None:
    # Given
    payload, _path = _live_pass_payload(
        tmp_path,
        evidence=["oracle transcript"],
        checked_paths=["tests/test_example.py"],
        sample_size=1,
    )
    manifest_path = tmp_path / "forged-manifest.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    # When / Then
    with pytest.raises(ValueError, match="live PASS run provenance must bind session and commit"):
        load_manifest(manifest_path)


def test_live_pass_rejects_inflated_sample_size_after_validating_run_provenance(tmp_path: Path) -> None:
    # Given
    payload, _path = _live_pass_payload(
        tmp_path,
        evidence=["oracle transcript"],
        checked_paths=["tests/test_example.py"],
        sample_size=10,
        session_id="live-session",
        commit_sha="a" * 40,
    )
    manifest_path = tmp_path / "forged-manifest.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    # When / Then
    with pytest.raises(ValueError, match="live PASS sample_size must match validated live session runs"):
        load_manifest(manifest_path)
