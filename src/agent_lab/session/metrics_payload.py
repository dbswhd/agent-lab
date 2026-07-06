"""Read-only session metrics payloads for Room agents (S1)."""

from __future__ import annotations

from agent_lab.run.state import RunStateLike
from pathlib import Path
from typing import Any

from agent_lab.emergence_kpis import emergence_kpis
from agent_lab.session.chat_io import load_chat_dicts
from agent_lab.run.meta import read_run_meta


def build_turn_policy_snapshot(run_meta: RunStateLike | None) -> dict[str, Any]:
    run = run_meta or {}
    tp = run.get("turn_policy")
    snapshot = dict(tp) if isinstance(tp, dict) else {}
    return {
        "turn_policy": snapshot,
        "turn_kind": str(run.get("turn_kind") or ""),
        "room_preset": str(run.get("room_preset") or ""),
        "plan_workflow_phase": _plan_phase(run),
    }


def _plan_phase(run: dict[str, Any]) -> str:
    from agent_lab.plan.workflow import is_plan_workflow_active, plan_workflow_phase

    if not is_plan_workflow_active(run):
        return ""
    return plan_workflow_phase(run)


def build_emergence_kpis_payload(folder: Path) -> dict[str, Any]:
    folder = folder.expanduser().resolve()
    run_meta = read_run_meta(folder)
    messages = load_chat_dicts(folder)
    scores, counts = emergence_kpis(folder, run_meta, messages)
    return {
        "session_id": folder.name,
        "scores": scores,
        "counts": counts,
    }


def build_session_metrics_payload(folder: Path, *, include_judge: bool = False) -> dict[str, Any]:
    """Compact score_session view — read-only, safe for in-turn agent self-observation."""
    from agent_lab.session.score import score_session

    folder = folder.expanduser().resolve()
    report = score_session(folder)
    scores = dict(report.get("scores") or {})
    counts = dict(report.get("counts") or {})
    emergence = counts.get("emergence")
    if not isinstance(emergence, dict):
        emergence = {}
    payload: dict[str, Any] = {
        "session_id": report.get("session_id") or folder.name,
        "scores": {
            k: scores[k]
            for k in (
                "hybrid_action_rate",
                "challenge_yield",
                "recombination_validity_rate",
                "objection_resolution_rate",
                "partial_turn_rate",
                "duplicate_speech_rate",
            )
            if k in scores
        },
        "emergence_counts": emergence,
        "summary_lines": (report.get("summary_lines") or [])[:8],
        "turn_policy": build_turn_policy_snapshot(read_run_meta(folder)),
    }
    if include_judge:
        judge = report.get("judge")
        if isinstance(judge, dict) and judge.get("enabled"):
            payload["judge"] = {
                "overall": judge.get("overall"),
                "verdict": judge.get("verdict"),
                "source": judge.get("source"),
            }
    return payload
