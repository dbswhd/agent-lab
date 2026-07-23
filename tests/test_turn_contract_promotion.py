from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent_lab.room.turn_contract_evidence import build_turn_contract_evidence
from agent_lab.room.turn_contract_promotion import build_promotion_report


def test_shadow_evidence_records_candidate_and_observed_route() -> None:
    evidence = build_turn_contract_evidence(
        {
            "contract_id": "critical_review",
            "safety_floor": "critical_review",
            "risk": "high",
            "rollout_mode": "shadow",
            "applied": False,
        },
        agents=["cursor", "codex", "claude"],
        rounds_used=2,
        consensus=True,
        latency_ms=120,
        cost_usd=0.25,
        route_regrets=("over_routed_candidate",),
    )

    assert evidence == {
        "candidate_contract_id": "critical_review",
        "applied_contract_id": "critical_review",
        "safety_floor_satisfied": True,
        "roster": ["cursor", "codex", "claude"],
        "rounds_used": 2,
        "consensus": True,
        "latency_ms": 120,
        "cost_usd": 0.25,
        "route_regret_signals": ["over_routed_candidate"],
        "shadow_applied_parity": True,
        "rollout_mode": "shadow",
    }


def test_shadow_evidence_records_unsafe_under_route_without_hiding_it() -> None:
    evidence = build_turn_contract_evidence(
        {
            "contract_id": "critical_review",
            "safety_floor": "critical_review",
            "risk": "high",
            "rollout_mode": "shadow",
            "applied": False,
        },
        agents=["cursor"],
        rounds_used=1,
        consensus=False,
        latency_ms=20,
        cost_usd=0.01,
    )

    assert evidence["applied_contract_id"] == "quick_read"
    assert evidence["safety_floor_satisfied"] is False
    assert evidence["shadow_applied_parity"] is False


def _promotion_rows(stage: str, *, count: int, parity: bool = True) -> list[dict[str, object]]:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    rows: list[dict[str, object]] = []
    for index in range(count):
        rows.append(
            {
                "phase": "turn",
                "session_id": f"{stage}-{index}",
                "ts": (start + timedelta(hours=(8 * 24 * index / max(count - 1, 1)))).isoformat(),
                "rollout_mode": stage,
                "candidate_contract_id": "critical_review",
                "applied_contract_id": "critical_review" if parity else "quick_read",
                "safety_floor_satisfied": parity,
                "risk": "high",
                "shadow_applied_parity": parity,
                "latency_ms": 105,
            },
        )
    return rows


def test_promotion_report_requires_history_and_human_go() -> None:
    shadow = _promotion_rows("shadow", count=10)
    stage = _promotion_rows("roles", count=10)

    insufficient = build_promotion_report(shadow + stage[:9], stage="roles")
    ready = build_promotion_report(shadow + stage, stage="roles")

    assert insufficient["decision"] == "BLOCK"
    assert "eligible_sessions<10" in insufficient["blocking_reasons"]
    assert ready["metrics_green"] is True
    assert ready["decision"] == "HUMAN_GO_REQUIRED"
    assert ready["human_checkpoint"] == "GO roles before evaluating adaptive"


def test_promotion_report_rejects_malformed_and_unsafe_rows() -> None:
    shadow = _promotion_rows("shadow", count=10)
    stage = _promotion_rows("adaptive", count=10)
    stage[0]["safety_floor_satisfied"] = False
    stage[0]["applied_contract_id"] = "quick_read"
    rows: list[dict[str, object]] = shadow + stage + [{"session_id": "stale"}, {"ts": "not-a-date"}]

    report = build_promotion_report(rows, stage="adaptive")

    assert report["decision"] == "BLOCK"
    assert report["safety_floor_violations"] == 1
    assert report["critical_under_routing"] == 1
    assert report["malformed_rows"] == 2


def test_promotion_cli_emits_machine_readable_gate(tmp_path: Path) -> None:
    ledger = tmp_path / "outcomes.jsonl"
    rows = _promotion_rows("shadow", count=10) + _promotion_rows("roles", count=9)
    ledger.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/turn_contract_promotion_report.py",
            "--ledger",
            str(ledger),
            "--stage",
            "roles",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert json.loads(completed.stdout)["decision"] == "BLOCK"
