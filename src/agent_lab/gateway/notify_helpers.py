"""Mission OS gateway notify helpers — thin wrappers around fan_out_gateway_notify."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.gate_scope import get_gate_profile
from agent_lab.run_meta import read_run_meta


def _safe_fan_out(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        from agent_lab.gateway.adapters import fan_out_gateway_notify

        return fan_out_gateway_notify(event, payload)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "event": event}


def notify_merge_ready(
    folder: Path,
    execution: dict[str, Any],
    *,
    include_eligibility: bool = True,
) -> dict[str, Any]:
    """Dry-run complete — execution awaiting Human merge (or auto-merge)."""
    run = read_run_meta(folder)
    payload: dict[str, Any] = {
        "session_id": folder.name,
        "execution_id": execution.get("id"),
        "gate_profile": get_gate_profile(run),
        "action_index": execution.get("action_index"),
        "status": execution.get("status"),
    }
    if include_eligibility:
        try:
            from agent_lab.auto_merge import evaluate_auto_merge_eligibility

            payload["auto_merge_eligibility"] = evaluate_auto_merge_eligibility(
                folder,
                execution_id=str(execution.get("id") or "") or None,
            )
        except Exception:
            pass
    return _safe_fan_out("merge_ready", payload)


def notify_gate_blocked(
    folder: Path,
    snapshot: dict[str, Any],
    *,
    source: str | None = None,
) -> dict[str, Any]:
    """Policy gate blocked — Human action required."""
    gates = snapshot.get("gates") if isinstance(snapshot.get("gates"), dict) else {}
    gate_profile = gates.get("gate_profile")
    if gate_profile is None:
        gate_profile = get_gate_profile(read_run_meta(folder))
    payload: dict[str, Any] = {
        "session_id": folder.name,
        "block_source": snapshot.get("block_source"),
        "block_reason": snapshot.get("block_reason"),
        "next_allowed_action": snapshot.get("next_allowed_action"),
        "gate_profile": gate_profile,
    }
    if source:
        payload["source"] = source
    return _safe_fan_out("gate_blocked", payload)


def notify_schedule_tick(payload: dict[str, Any]) -> dict[str, Any]:
    """Cron schedule fired."""
    return _safe_fan_out("schedule_tick", payload)


def notify_auto_merge_blocked(
    folder: Path,
    *,
    execution: dict[str, Any],
    eligibility: dict[str, Any],
    source: str = "scheduled_tick",
    dedupe: bool = True,
) -> dict[str, Any]:
    """Scheduled auto-merge skipped — Human merge required."""
    execution_id = str(execution.get("id") or "").strip()
    if dedupe and execution_id:
        run = read_run_meta(folder)
        schedule_meta = run.get("mission_schedule") if isinstance(run.get("mission_schedule"), dict) else {}
        seen = {str(row) for row in (schedule_meta.get("auto_merge_blocked_executions") or []) if str(row).strip()}
        if execution_id in seen:
            return {"ok": True, "skipped": True, "reason": "already_notified", "event": "auto_merge_blocked"}

        def _mark(run_in: dict[str, Any]) -> dict[str, Any]:
            ms = dict(run_in.get("mission_schedule") or {})
            rows = [str(row) for row in (ms.get("auto_merge_blocked_executions") or []) if str(row).strip()]
            if execution_id not in rows:
                rows.append(execution_id)
            ms["auto_merge_blocked_executions"] = rows[-20:]
            run_in["mission_schedule"] = ms
            return run_in

        from agent_lab.run_meta import patch_run_meta

        patch_run_meta(folder, _mark)

    run = read_run_meta(folder)
    reason = str(eligibility.get("reason") or "auto_merge_not_eligible")
    payload: dict[str, Any] = {
        "session_id": folder.name,
        "execution_id": execution_id or None,
        "gate_profile": get_gate_profile(run),
        "action_index": execution.get("action_index"),
        "status": execution.get("status"),
        "reason": reason,
        "auto_merge_eligibility": eligibility,
        "source": source,
        "phase": "MERGE_REVIEW",
    }
    return _safe_fan_out("auto_merge_blocked", payload)
