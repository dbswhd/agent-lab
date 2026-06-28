"""Five evidence gates on executions — OmO $start-work pattern (MB-3)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from agent_lab.adversarial_gate import LGTM_TOKEN, badge_tone

GateStatus = Literal["pass", "fail", "pending", "skip"]

GATE_IDS: tuple[str, ...] = (
    "plan_reread",
    "automated",
    "manual_merge",
    "adversarial",
    "cleanup",
)

PENDING_STATUSES = frozenset({"pending_approval", "review_required", "pending"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gate(
    gate: str,
    *,
    status: GateStatus,
    detail: str | None = None,
    ssot: str | None = None,
) -> dict[str, Any]:
    return {
        "gate": gate,
        "status": status,
        "detail": detail,
        "ssot": ssot,
        "at": _now_iso(),
    }


def _plan_reread_gate(run: dict[str, Any]) -> dict[str, Any]:
    from agent_lab.mission.loop import get_mission_loop

    ml = get_mission_loop(run)
    if not ml.get("enabled"):
        return _gate("plan_reread", status="skip", detail="mission loop off", ssot="mission_loop")
    gate = ml.get("plan_gate") if isinstance(ml.get("plan_gate"), dict) else {}
    status = str(gate.get("status") or "pending")
    if status == "ok":
        return _gate("plan_reread", status="pass", ssot="plan_gate.status")
    if status in {"reject", "failed", "fail"}:
        return _gate(
            "plan_reread",
            status="fail",
            detail=str(gate.get("last_reject_reason") or status),
            ssot="plan_gate.status",
        )
    return _gate("plan_reread", status="pending", detail=status, ssot="plan_gate.status")


def _adversarial_gate(execution: dict[str, Any]) -> dict[str, Any]:
    note = str(execution.get("adversarial_note") or "").strip()
    if not note:
        return _gate("adversarial", status="pending", ssot="adversarial_note")
    tone = badge_tone(note)
    if tone == "lgtm" or note.upper() == LGTM_TOKEN:
        return _gate("adversarial", status="pass", detail=note, ssot="adversarial_note")
    return _gate("adversarial", status="fail", detail=note, ssot="adversarial_note")


def _manual_merge_gate(execution: dict[str, Any]) -> dict[str, Any]:
    status = str(execution.get("status") or "")
    merge = execution.get("merge") if isinstance(execution.get("merge"), dict) else {}
    if status == "merged" or merge.get("status") == "merged":
        return _gate("manual_merge", status="pass", ssot="merge approve event")
    if status in {"rejected", "merge_conflict"}:
        return _gate("manual_merge", status="fail", detail=status, ssot="merge approve event")
    if status in PENDING_STATUSES:
        return _gate("manual_merge", status="pending", ssot="merge approve event")
    return _gate("manual_merge", status="pending", detail=status or "unknown", ssot="merge approve event")


def _automated_gate(execution: dict[str, Any]) -> dict[str, Any]:
    verify = execution.get("verify_after_merge")
    if isinstance(verify, dict):
        oracle = verify.get("oracle") if isinstance(verify.get("oracle"), dict) else {}
        verdict = str(oracle.get("verdict") or verify.get("status") or "").lower()
        if verdict in {"pass", "passed"}:
            return _gate(
                "automated",
                status="pass",
                detail=str(execution.get("action_verify") or "")[:200] or None,
                ssot="action.verify",
            )
        if verdict in {"fail", "failed"}:
            return _gate(
                "automated",
                status="fail",
                detail=str(oracle.get("detail") or oracle.get("reason") or verdict),
                ssot="action.verify",
            )
        if verdict == "skipped":
            return _gate("automated", status="skip", detail="verify skipped", ssot="action.verify")
    status = str(execution.get("status") or "")
    if status in PENDING_STATUSES:
        return _gate("automated", status="pending", ssot="action.verify")
    oracle_only = execution.get("oracle")
    if isinstance(oracle_only, dict):
        verdict = str(oracle_only.get("verdict") or "").lower()
        if verdict == "pass":
            return _gate("automated", status="pass", ssot="oracle")
        if verdict == "fail":
            return _gate(
                "automated",
                status="fail",
                detail=str(oracle_only.get("detail") or "oracle fail"),
                ssot="oracle",
            )
    return _gate("automated", status="pending", ssot="action.verify")


def _cleanup_gate(execution: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    status = str(execution.get("status") or "")
    if status != "merged":
        return _gate("cleanup", status="pending", ssot="post-merge lint hook")
    hooks = run.get("hook_runs") or []
    if isinstance(hooks, list):
        for row in reversed(hooks):
            if not isinstance(row, dict):
                continue
            if row.get("phase") == "post_merge" or row.get("hook") == "cleanup":
                blocked = bool(row.get("blocked"))
                return _gate(
                    "cleanup",
                    status="fail" if blocked else "pass",
                    detail=str(row.get("reason") or row.get("summary") or "")[:200] or None,
                    ssot="post-merge lint hook",
                )
    return _gate("cleanup", status="skip", detail="optional", ssot="post-merge lint hook")


def build_evidence_gates(
    run: dict[str, Any],
    execution: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        _plan_reread_gate(run),
        _adversarial_gate(execution),
        _manual_merge_gate(execution),
        _automated_gate(execution),
        _cleanup_gate(execution, run),
    ]


def attach_evidence_gates(
    run: dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any]:
    updated = dict(execution)
    updated["evidence_gates"] = build_evidence_gates(run, execution)
    oracle = updated.get("oracle")
    if not isinstance(oracle, dict):
        verify_after = updated.get("verify_after_merge")
        if isinstance(verify_after, dict):
            oracle = verify_after.get("oracle")
    if isinstance(oracle, dict):
        updated["oracle_verdict"] = oracle.get("verdict")
    return updated


def patch_execution_gates(
    folder,
    execution_id: str,
) -> dict[str, Any] | None:
    from pathlib import Path

    from agent_lab.run.meta import patch_run_meta, read_run_meta

    path = Path(folder)

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        rows = list(run.get("executions") or [])
        for i, row in enumerate(rows):
            if not isinstance(row, dict) or row.get("id") != execution_id:
                continue
            rows[i] = attach_evidence_gates(run, row)
            run["executions"] = rows
            return run
        return run

    patch_run_meta(path, _patch)
    run = read_run_meta(path)
    for row in run.get("executions") or []:
        if isinstance(row, dict) and row.get("id") == execution_id:
            return row
    return None
