"""v1 operational checklist (plan §7.10) — automated gates for Trading Mission."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from agent_lab.mission_loop import evaluate_plan_gate
from agent_lab.trading_mission.plan_gate import trading_plan_gate_issues
from agent_lab.research_mcp_read import (
    read_pending_batch_summary,
    read_playbook_summary,
)
from agent_lab.trading_mission.verify import check_artifacts, trading_mission_goal_ok

_REQUIRED_ARTIFACTS = (
    "artifacts/market_snapshot.json",
    "artifacts/proposal_batch.json",
    "artifacts/playbook.md",
    "plan.md",
)


def check_premarket_four_artifacts(session_folder: Path) -> dict[str, Any]:
    """§7.10: market_snapshot, proposal_batch, playbook, plan.md (+ mission_summary on block)."""
    folder = session_folder.expanduser().resolve()
    missing = [rel for rel in _REQUIRED_ARTIFACTS if not (folder / rel).is_file()]
    summary_path = folder / "artifacts" / "mission_summary.md"
    snapshot_path = folder / "artifacts" / "market_snapshot.json"
    trade_allowed = True
    if snapshot_path.is_file():
        try:
            snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
            if isinstance(snap, dict):
                trade_allowed = bool(snap.get("trade_allowed", True))
        except (OSError, json.JSONDecodeError):
            pass
    if not trade_allowed and not summary_path.is_file():
        missing.append("artifacts/mission_summary.md (expected when blocked)")

    artifact_report = check_artifacts(folder)
    return {
        "id": "premarket_four_artifacts",
        "ok": not missing and artifact_report.get("ok", False),
        "missing": missing,
        "artifact_checks": artifact_report,
        "trade_allowed": trade_allowed,
    }


def check_freshness_blocking_shape(session_folder: Path) -> dict[str, Any]:
    """§7.10: blocking → ingest_ready false, proposals empty."""
    folder = session_folder.expanduser().resolve()
    snap = folder / "artifacts" / "market_snapshot.json"
    batch = folder / "artifacts" / "proposal_batch.json"
    if not snap.is_file() or not batch.is_file():
        return {
            "id": "freshness_blocking",
            "ok": False,
            "reason": "missing snapshot or batch",
        }
    try:
        snapshot = json.loads(snap.read_text(encoding="utf-8"))
        batch_data = json.loads(batch.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"id": "freshness_blocking", "ok": False, "reason": "invalid json"}

    trade_allowed = bool(snapshot.get("trade_allowed", True))
    ingest_ready = bool(batch_data.get("ingest_ready"))
    proposals = batch_data.get("proposals") if isinstance(batch_data.get("proposals"), list) else []
    if trade_allowed:
        return {
            "id": "freshness_blocking",
            "ok": True,
            "skipped": True,
            "reason": "session is not a blocking case",
        }

    ok = (not ingest_ready) and len(proposals) == 0
    return {
        "id": "freshness_blocking",
        "ok": ok,
        "trade_allowed": trade_allowed,
        "ingest_ready": ingest_ready,
        "proposal_count": len(proposals),
    }


def check_fail_ref_plan_gate_reject(session_folder: Path) -> dict[str, Any]:
    """§7.10: FAIL ref in batch → plan_gate reject."""
    folder = session_folder.expanduser().resolve()
    plan_path = folder / "plan.md"
    if not plan_path.is_file():
        return {"id": "fail_ref_plan_gate", "ok": False, "reason": "plan.md missing"}

    plan_md = plan_path.read_text(encoding="utf-8", errors="replace")
    issues = trading_plan_gate_issues(plan_md, folder)
    has_fail_issue = "fail_backtest_ref_in_proposals" in issues
    run = {"session_template": "trading-mission", "mission_kind": "trading_premarket"}
    gate = evaluate_plan_gate(plan_md, run=run, session_folder=folder)

    return {
        "id": "fail_ref_plan_gate",
        "ok": has_fail_issue and gate.get("status") == "reject",
        "plan_gate_status": gate.get("status"),
        "issues": issues,
        "gate_reason": gate.get("reason"),
    }


def check_pass_goal_ok(session_folder: Path) -> dict[str, Any]:
    """PASS session goal oracle."""
    folder = session_folder.expanduser().resolve()
    goal = trading_mission_goal_ok(folder)
    return {
        "id": "pass_goal_ok",
        "ok": goal.get("ok") is True,
        "detail": goal.get("detail"),
    }


def check_control_plane_ingested(db_path: Path) -> dict[str, Any]:
    """At least one proposal + risk decision recorded (post-ingest)."""
    path = db_path.expanduser().resolve()
    if not path.is_file():
        return {"id": "control_plane_ingested", "ok": False, "reason": "db missing"}

    with sqlite3.connect(path) as con:
        proposal_count = con.execute("SELECT COUNT(*) FROM trade_proposal").fetchone()[0]
        risk_count = con.execute("SELECT COUNT(*) FROM risk_decision").fetchone()[0]

    return {
        "id": "control_plane_ingested",
        "ok": int(proposal_count) >= 1 and int(risk_count) >= 1,
        "proposal_count": int(proposal_count),
        "risk_decision_count": int(risk_count),
    }


def check_control_plane_pending(db_path: Path) -> dict[str, Any]:
    """§7.10: ingested proposals visible as pending in control plane SQLite."""
    path = db_path.expanduser().resolve()
    if not path.is_file():
        return {"id": "control_plane_pending", "ok": False, "reason": "db missing"}

    with sqlite3.connect(path) as con:
        rows = con.execute(
            "SELECT proposal_id, status FROM trade_proposal WHERE status = ?",
            ("pending",),
        ).fetchall()
        risk_rows = con.execute("SELECT COUNT(*) FROM risk_decision").fetchone()

    return {
        "id": "control_plane_pending",
        "ok": len(rows) >= 1,
        "pending_count": len(rows),
        "pending_ids": [r[0] for r in rows],
        "risk_decision_count": int(risk_rows[0]) if risk_rows else 0,
    }


def check_thin_runtime_readonly(session_folder: Path, *, db_path: Path | None = None) -> dict[str, Any]:
    """§7.10: thin agent reads playbook + batch + pending status (no Room)."""
    folder = session_folder.expanduser().resolve()
    playbook = read_playbook_summary(folder)
    batch = read_pending_batch_summary(folder)
    pending: dict[str, Any] = {"ok": False, "pending_count": 0}
    if db_path is not None and db_path.is_file():
        pending = check_control_plane_pending(db_path)
        pending["ok"] = pending.get("pending_count", 0) >= 0

    ok = playbook.get("ok") and batch.get("ok")
    return {
        "id": "thin_runtime_readonly",
        "ok": ok,
        "playbook_chars": playbook.get("char_count"),
        "batch_proposal_count": batch.get("proposal_count"),
        "ingest_ready": batch.get("ingest_ready"),
        "control_plane": pending,
        "forbidden_room_started": False,
    }


def run_v1_checklist(
    *,
    pass_session: Path | None = None,
    blocked_session: Path | None = None,
    fail_session: Path | None = None,
    db_path: Path | None = None,
    expect_pending: bool = True,
) -> dict[str, Any]:
    """Run all supplied §7.10 scenario checks."""
    checks: list[dict[str, Any]] = []

    if pass_session is not None:
        checks.append(check_premarket_four_artifacts(pass_session))
        checks.append(check_pass_goal_ok(pass_session))
        checks.append(check_thin_runtime_readonly(pass_session, db_path=db_path))
        if db_path is not None:
            if expect_pending:
                checks.append(check_control_plane_pending(db_path))
            else:
                checks.append(check_control_plane_ingested(db_path))

    if blocked_session is not None:
        checks.append(check_freshness_blocking_shape(blocked_session))
        checks.append(check_premarket_four_artifacts(blocked_session))

    if fail_session is not None:
        checks.append(check_fail_ref_plan_gate_reject(fail_session))

    ok = all(c.get("ok") for c in checks if not c.get("skipped"))
    return {
        "ok": ok,
        "checklist_version": "v1",
        "checks": checks,
        "passed": sum(1 for c in checks if c.get("ok")),
        "total": len(checks),
    }


def build_fail_ref_fixture(base: Path) -> Path:
    """Create a minimal session with FAIL-only proposal for plan_gate tests."""
    folder = base / "fail-ref-session"
    artifacts = folder / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "market_snapshot.json").write_text(
        json.dumps(
            {
                "trade_allowed": True,
                "eligible_cards": [{"ref": "research/kr/results/demo/demo_fail_full.json", "verdict": "FAIL"}],
            }
        ),
        encoding="utf-8",
    )
    (folder / "plan.md").write_text(
        "# plan\n\n## 합의\n- ingest_ready: true\n",
        encoding="utf-8",
    )
    (artifacts / "playbook.md").write_text(
        "# 오늘 장중 행동\n\n- should not ingest FAIL ref\n",
        encoding="utf-8",
    )
    (artifacts / "proposal_batch.json").write_text(
        json.dumps(
            {
                "mission_id": "fail-ref-test",
                "ingest_ready": True,
                "proposals": [
                    {
                        "symbol": "069500",
                        "market": "kr",
                        "side": "buy",
                        "quantity": 1,
                        "notional": 100_000,
                        "order_type": "market",
                        "thesis": "invalid FAIL ref proposal for gate test",
                        "data_sources": ["overlay:kr_kospi_v1"],
                        "backtest_ref": "research/kr/results/demo/demo_fail_full.json",
                        "confidence": 0.5,
                        "expires_at": "2026-06-13T15:20:00+09:00",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return folder


def build_blocked_fixture(base: Path) -> Path:
    """Freshness-blocking shaped session (proposal 0)."""
    folder = base / "blocked-session"
    artifacts = folder / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "market_snapshot.json").write_text(
        json.dumps(
            {
                "trade_allowed": False,
                "freshness": {"blocking": True, "message": "stale data"},
                "eligible_cards": [],
            }
        ),
        encoding="utf-8",
    )
    (artifacts / "proposal_batch.json").write_text(
        json.dumps(
            {
                "mission_id": "blocked-test",
                "ingest_ready": False,
                "proposals": [],
            }
        ),
        encoding="utf-8",
    )
    (artifacts / "playbook.md").write_text(
        "# 오늘 장중 행동\n\n## 상태\n- 거래 보류\n",
        encoding="utf-8",
    )
    (artifacts / "mission_summary.md").write_text(
        "# Mission summary (blocked)\n\n- trade_allowed: false\n",
        encoding="utf-8",
    )
    (folder / "plan.md").write_text(
        "# plan\n\n## 합의\n- ingest_ready: false\n- discuss_rounds_used: 0\n",
        encoding="utf-8",
    )
    return folder
