"""Post-turn auto-scribe tail and SSE complete event."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.room.messages import OnAgentEvent
from agent_lab.room.session_persist import _read_run_meta, _sse_inbox_pending
from agent_lab.room.turn_meta import (
    _verified_loop_complete_payload,
    maybe_auto_scribe_after_consensus,
    maybe_auto_scribe_after_verified_loop,
)


def _verified_loop_scribe_pending(folder: Path, verified_result: dict[str, Any] | None) -> bool:
    if not verified_result:
        return False
    loop = dict(verified_result.get("verified_loop") or {})
    if str(loop.get("status") or "") != "done":
        return False
    verified_at = str(loop.get("verified_at") or "").strip()
    run = _read_run_meta(folder)
    sync = dict(run.get("verified_plan_sync") or {})
    return sync.get("verified_at") != verified_at


def apply_post_turn_auto_scribe(
    folder: Path,
    *,
    verified_result: dict[str, Any] | None,
    consensus_meta: dict[str, Any] | None,
    active_profile: str | None,
    synthesize: bool,
    cancelled: bool,
    on_event: OnAgentEvent | None,
    permissions: dict | None,
    plan_md: str,
) -> str:
    from agent_lab.room.turn_policy import TurnSignals, apply_turn_effects, turn_policy_enabled
    from agent_lab.verified_loop import normalize_verified_profile

    if turn_policy_enabled():
        run_meta = _read_run_meta(folder)
        verified_done = _verified_loop_scribe_pending(folder, verified_result)
        result = apply_turn_effects(
            signals=TurnSignals.from_run_meta(
                run_meta,
                consensus_meta=consensus_meta,
                verified_loop_done=verified_done,
                cancelled=cancelled,
            ),
            folder=folder,
            run_meta=run_meta,
            plan_before=plan_md,
            cancelled=cancelled,
            on_event=on_event,
            permissions=permissions,
            consensus_meta=consensus_meta,
            verified_result=verified_result,
            skip_fsm=True,
            skip_peer_pipeline=True,
        )
        return result.plan_md or plan_md

    auto_plan = maybe_auto_scribe_after_verified_loop(
        folder,
        verified_result=verified_result,
        cancelled=cancelled,
        on_event=on_event,
        permissions=permissions,
    )
    if auto_plan is not None:
        return auto_plan
    if not normalize_verified_profile(active_profile):
        auto_plan = maybe_auto_scribe_after_consensus(
            folder,
            consensus_meta=consensus_meta,
            synthesize=synthesize,
            cancelled=cancelled,
            on_event=on_event,
            permissions=permissions,
        )
        if auto_plan is not None:
            return auto_plan
    return plan_md


def emit_turn_complete_event(
    folder: Path,
    *,
    on_event: OnAgentEvent | None,
    cancelled: bool,
    turn_status: str,
    turn_summary: dict[str, Any],
    send_receipt_val: str | None,
    verified_result: dict[str, Any] | None,
) -> None:
    if not on_event:
        return
    from agent_lab.plan.workflow import plan_workflow_complete_payload

    on_event(
        "complete",
        {
            "session_id": folder.name,
            "path": str(folder),
            "cancelled": cancelled,
            "status": turn_status,
            "failed_agents": turn_summary["failed_agents"],
            "succeeded_agents": turn_summary["succeeded_agents"],
            "send_receipt": send_receipt_val,
            "inbox_pending": _sse_inbox_pending(folder),
            "turn_index": max(
                0,
                len((_read_run_meta(folder).get("turns") or [])) - 1,
            ),
            **_verified_loop_complete_payload(verified_result),
            **plan_workflow_complete_payload(folder),
        },
    )
