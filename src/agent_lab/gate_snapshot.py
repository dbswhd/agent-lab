"""Pure gate snapshot from run.json state (Hook · Communicate reform)."""

from __future__ import annotations

from typing import Any, Literal

NextAction = Literal[
    "discuss",
    "plan",
    "dry_run",
    "merge",
    "wait_human",
    "blocked",
]

BlockSource = Literal[
    "inbox_pending",
    "open_objection",
    "pre_execute",
    "consensus_incomplete",
    "task_blocked",
    "executor_unavailable",
]


def compute_gate_snapshot(run_meta: dict[str, Any] | None) -> dict[str, Any]:
    """Derive orchestration gates from run_meta (no side effects)."""
    meta = run_meta or {}
    gates: dict[str, Any] = {
        "execute": {"open": True, "reason": None},
        "consensus": {"open": True, "reason": None},
        "inbox": {"pending": 0},
    }
    block_source: str | None = None
    block_reason: str | None = None

    from agent_lab.human_inbox import compute_inbox_pending, pending_inbox_items

    if compute_inbox_pending(meta):
        pending = pending_inbox_items(meta)
        gates["inbox"]["pending"] = len(pending)
        block_source = "inbox_pending"
        block_reason = pending[0].get("prompt") or pending[0].get("id") or "Human Inbox pending"

    try:
        from agent_lab.gate_scope import public_gate_scope_payload

        scope = public_gate_scope_payload(meta)
        gates["gate_profile"] = scope.get("gate_profile")
        gates["discuss"] = scope.get("discuss")
        gates["plan_clarify"] = scope.get("plan_clarify")
        gates["execute_gate"] = scope.get("execute")
        inbox_scope = scope.get("inbox")
        if isinstance(inbox_scope, dict):
            gates["inbox"].update(inbox_scope)
    except Exception:
        pass

    from agent_lab.room.objections import open_objections

    open_objs = open_objections(meta)
    block_objs = [o for o in open_objs if o.get("act") == "BLOCK"]
    if block_objs and block_source is None:
        block_source = "open_objection"
        block_reason = (block_objs[0].get("body") or "")[:200] or block_objs[0].get("id")
        gates["execute"]["open"] = False
        gates["execute"]["reason"] = block_reason

    for ex in reversed(meta.get("executions") or []):
        if not isinstance(ex, dict):
            continue
        pre = ex.get("pre_verify") or {}
        if isinstance(pre, dict) and pre.get("blocked"):
            if block_source is None:
                block_source = "pre_execute"
                block_reason = str(pre.get("feedback") or "pre_execute hook blocked")
            gates["execute"]["open"] = False
            gates["execute"]["reason"] = block_reason
            break

    consensus = meta.get("_last_consensus") or meta.get("consensus") or {}
    if isinstance(consensus, dict) and consensus.get("status") not in (None, "reached"):
        pending = consensus.get("pending_agents") or []
        if pending:
            gates["consensus"]["open"] = False
            gates["consensus"]["reason"] = f"pending: {', '.join(str(a) for a in pending[:5])}"
            if block_source is None and open_objs:
                block_source = "consensus_incomplete"
                block_reason = gates["consensus"]["reason"]

    for o in open_objs:
        if o.get("act") == "CHALLENGE" and o.get("task_id"):
            if block_source is None:
                block_source = "task_blocked"
                block_reason = f"CHALLENGE on {o.get('task_id')}"
            break

    if meta.get("cursor_bridge_degraded"):
        if block_source is None:
            block_source = "executor_unavailable"
            block_reason = str(meta.get("cursor_bridge_reason") or "Cursor bridge degraded")

    next_action: NextAction = "discuss"
    if block_source == "inbox_pending":
        next_action = "wait_human"
    elif not gates["execute"]["open"]:
        next_action = "blocked"
    elif meta.get("inbox_pending") is False and not compute_inbox_pending(meta):
        next_action = "discuss"

    return {
        "next_allowed_action": next_action,
        "block_source": block_source,
        "block_reason": block_reason,
        "gates": gates,
        "open_objection_count": len(open_objs),
    }


def format_gate_snapshot_block(snapshot: dict[str, Any]) -> str:
    if not snapshot:
        return ""
    src = snapshot.get("block_source")
    if not src:
        return ""
    reason = snapshot.get("block_reason") or ""
    nxt = snapshot.get("next_allowed_action") or "discuss"
    inbox_n = (snapshot.get("gates") or {}).get("inbox", {}).get("pending", 0)
    lines = [
        "[Gate snapshot]",
        f"- next_allowed_action: {nxt}",
        f"- block_source: {src}",
    ]
    if reason:
        lines.append(f"- block_reason: {reason[:240]}")
    if inbox_n:
        lines.append(f"- inbox_pending: {inbox_n}")
    return "\n".join(lines)
