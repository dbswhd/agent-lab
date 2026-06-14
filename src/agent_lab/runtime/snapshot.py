"""Runtime snapshot — read-path SSOT for Work UI (H1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from agent_lab.consensus_agreements import pending_consensus_agreements
from agent_lab.human_inbox import public_inbox_payload
from agent_lab.mission_loop import get_mission_loop, sync_mission_phase_from_run
from agent_lab.runtime.policy import PolicyEngine
from agent_lab.run_meta import read_run_meta

_PENDING_EXECUTION_STATUS = "pending_approval"
from agent_lab.runtime.boulder import boulder_state, last_failure
from agent_lab.runtime.external_runner import external_runner_enabled, external_tools_allowlist
from agent_lab.external_tools import load_external_tools
from agent_lab.runtime.phases import SessionMode
from agent_lab.evidence_ledger import public_evidence_payload
from agent_lab.merge_checks import public_merge_checks_payload
from agent_lab.mission_board import (
    public_mission_board_payload,
    public_turn_budget_payload,
)
from agent_lab.runtime.work_phase import resolve_work_phase


def _execution_rows(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in (run.get("executions") or []) if isinstance(row, dict)]


def pending_execution(run: dict[str, Any]) -> dict[str, Any] | None:
    for row in reversed(_execution_rows(run)):
        if row.get("status") == _PENDING_EXECUTION_STATUS:
            return row
    return None


def latest_execution(run: dict[str, Any]) -> dict[str, Any] | None:
    rows = _execution_rows(run)
    return rows[-1] if rows else None


def has_dry_run_diff(run: dict[str, Any]) -> bool:
    pending = pending_execution(run)
    if pending and pending.get("diff"):
        return True
    agreements = pending_consensus_agreements(run.get("consensus_agreements"))
    return bool(agreements)


def _next_action(
    *,
    mode: SessionMode,
    mission_phase: str,
    mission_paused: bool,
    work_phase: str,
    block_reason: str | None,
    inbox_pending: bool,
    pending_execution_id: str | None,
) -> str:
    if block_reason:
        return f"Resolve blocker: {block_reason[:120]}"
    if mission_paused:
        return "Resume mission"
    if inbox_pending:
        return "Resolve Human Inbox item"
    if mode == SessionMode.MISSION:
        phase = mission_phase.upper()
        if phase == "MERGE_REVIEW":
            return "Review diff and approve merge"
        if phase == "VERIFY":
            return "Waiting for Oracle verify"
        if phase == "PLAN_GATE":
            return "Plan gate evaluation"
        if phase == "EXECUTE_QUEUE":
            return "Advance execute queue or dry-run"
        if phase == "DRY_RUN":
            return "Dry-run in progress"
        if phase == "REPAIR":
            return "Repair after verify failure"
        if phase == "DISCUSS":
            return "Continue discuss turn"
        if phase == "MISSION_DONE":
            return "Mission complete"
    if work_phase == "merge_verify" and pending_execution_id:
        return "Review diff and approve merge"
    if work_phase == "execute_pending":
        return "Run dry-run or finish pending execution"
    if work_phase == "review_needed":
        return "Review plan or consensus sync"
    if work_phase == "done":
        return "Work complete"
    return "Draft or refine plan"


def build_runtime_snapshot(
    folder: Path,
    *,
    plan_md: str | None = None,
) -> dict[str, Any]:
    """Build unified runtime read model from session folder."""
    run = read_run_meta(folder)
    plan_path = folder / "plan.md"
    if plan_md is None and plan_path.is_file():
        plan_md = plan_path.read_text(encoding="utf-8")
    has_plan = bool((plan_md or "").strip())

    ml = sync_mission_phase_from_run(run)
    mission_enabled = bool(ml.get("enabled"))
    mode: Literal["standalone", "mission"] = (
        SessionMode.MISSION.value if mission_enabled else SessionMode.STANDALONE.value
    )
    mission_phase = str(ml.get("phase") or "MISSION_DEFINE")
    resume_phase = None
    last_partial = ml.get("last_partial")
    if isinstance(last_partial, dict):
        resume_phase = last_partial.get("resume_phase")

    pending_exec = pending_execution(run)
    latest_exec = latest_execution(run)
    pending_agreement = bool(pending_consensus_agreements(run.get("consensus_agreements")))
    inbox = public_inbox_payload(run)
    block_reason = PolicyEngine.execute_block_reason(run)

    from agent_lab.gate_scope import public_gate_scope_payload

    gate_scope = public_gate_scope_payload(run)

    from agent_lab.plan_workflow import get_plan_workflow, is_plan_workflow_active

    pw = get_plan_workflow(run)
    plan_workflow_enabled = is_plan_workflow_active(run)
    plan_workflow_phase = str(pw.get("phase") or "") if plan_workflow_enabled else None

    work_phase = resolve_work_phase(
        mission_enabled=mission_enabled,
        mission_phase=mission_phase,
        resume_phase=str(resume_phase) if resume_phase else None,
        plan_workflow_phase=plan_workflow_phase,
        plan_workflow_enabled=plan_workflow_enabled,
        has_plan=has_plan,
        has_pending_execution=pending_exec is not None,
        has_dry_run_diff=has_dry_run_diff(run),
        pending_agreement=pending_agreement,
        latest_execution=latest_exec,
    )

    mission_paused = mission_phase == "MISSION_PAUSED" or bool(ml.get("circuit_breaker"))
    boulder = boulder_state(run)
    failure = last_failure(run)
    if boulder and boulder.get("resume_phase") and not resume_phase:
        resume_phase = boulder.get("resume_phase")

    return {
        "session_id": folder.name,
        "mode": mode,
        "has_plan": has_plan,
        "work_phase": work_phase,
        "mission": {
            "enabled": mission_enabled,
            "phase": mission_phase,
            "paused": mission_paused,
            "pause_reason": ml.get("pause_reason"),
            "circuit_breaker": bool(ml.get("circuit_breaker")),
            "circuit_breaker_reason": ml.get("circuit_breaker_reason"),
            "resume_phase": resume_phase,
            "plan_gate_status": (ml.get("plan_gate") or {}).get("status")
            if isinstance(ml.get("plan_gate"), dict)
            else None,
            "pending_action_indices": list(ml.get("pending_action_indices") or []),
            "current_action_index": ml.get("current_action_index"),
        },
        "execute": {
            "has_pending": pending_exec is not None,
            "pending_execution_id": pending_exec.get("id") if pending_exec else None,
            "has_dry_run_diff": has_dry_run_diff(run),
            "latest_execution_id": latest_exec.get("id") if latest_exec else None,
            "latest_status": latest_exec.get("status") if latest_exec else None,
            "oracle_verdict": (
                (latest_exec.get("oracle") or {}).get("verdict")
                if latest_exec and isinstance(latest_exec.get("oracle"), dict)
                else None
            ),
        },
        "gates": {
            "block_reason": block_reason,
            "execute_blocked": block_reason is not None,
            "pending_agreement": pending_agreement,
            **gate_scope,
        },
        "inbox": {
            "pending": inbox.get("inbox_pending", False),
            "pending_count": inbox.get("pending_count", 0),
            "pending_questions": inbox.get("pending_questions", 0),
            "pending_builds": inbox.get("pending_builds", 0),
        },
        "next_action": _next_action(
            mode=SessionMode(mode),
            mission_phase=mission_phase,
            mission_paused=mission_paused,
            work_phase=work_phase,
            block_reason=block_reason,
            inbox_pending=bool(inbox.get("inbox_pending")),
            pending_execution_id=(
                str(pending_exec.get("id")) if pending_exec and pending_exec.get("id") else None
            ),
        ),
        "last_failure": failure,
        "boulder": boulder,
        "external": {
            "runner_enabled": external_runner_enabled(),
            "allowlist": external_tools_allowlist(run),
            "registered_count": len(load_external_tools()),
        },
        "mission_board": public_mission_board_payload(run),
        "turn_budget": public_turn_budget_payload(run),
        "merge_checks": public_merge_checks_payload(run, folder=folder),
        "evidence": public_evidence_payload(folder, limit=30),
        "clarifier_interview": _public_clarifier_interview(run),
        "wisdom_index": _public_wisdom_index(folder),
        "codex_proxy": _public_codex_proxy(),
    }


def _public_wisdom_index(folder: Path) -> dict[str, Any]:
    from agent_lab.wisdom_index import public_wisdom_index_status

    return public_wisdom_index_status(folder, run=read_run_meta(folder))


def _public_codex_proxy() -> dict[str, Any]:
    from agent_lab.runtime.adapters.codex import probe_codex_proxy

    return probe_codex_proxy()


def _public_clarifier_interview(run: dict[str, Any]) -> dict[str, Any] | None:
    from agent_lab.session_clarifier import public_clarifier_interview

    return public_clarifier_interview(run)


def public_runtime_payload(folder: Path, *, plan_md: str | None = None) -> dict[str, Any]:
    """API envelope for GET /runtime."""
    snapshot = build_runtime_snapshot(folder, plan_md=plan_md)
    return {"ok": True, **snapshot}
