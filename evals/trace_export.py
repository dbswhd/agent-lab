"""session folder → EvalTrace (v1 schema, docs/EVAL-SURFACE-V1-PLAN.md).

Reads ``run.json`` (+ ``chat.jsonl`` / ``plan.md`` when present) and synthesizes
the v1 fixed spans from structural evidence already in ``run.json`` — most
``sessions/_regression`` fixtures predate ``trace.jsonl`` (AGENT_LAB_TRACE),
so this is a **best-effort reconstruction**, not a literal span replay.
Fail-open: missing/malformed artifacts simply lower ``trace_completeness``
instead of raising (see EVAL-SURFACE-V1-PLAN.md §2).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# v1 fixed span names (EVAL-SURFACE-V1-PLAN.md).
FIXED_SPAN_NAMES = (
    "route",
    "role_plan",
    "room_round",
    "objection",
    "plan_update",
    "human_gate",
    "execute",
    "oracle_verify",
    "feedback_advisor",
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return obj if isinstance(obj, dict) else {}


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_int(value: object) -> int:
    return value if isinstance(value, int) else 0


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            obj = json.loads(text)
            if isinstance(obj, dict):
                rows.append(obj)
    except (OSError, json.JSONDecodeError):
        return []
    return rows


def export_session_trace(session_dir: Path, *, case_id: str = "") -> dict[str, Any]:
    """Export a session folder into an EvalTrace dict. Never raises."""
    run = _load_json(session_dir / "run.json")
    chat_rows = _load_jsonl(session_dir / "chat.jsonl")
    trace_rows = _load_jsonl(session_dir / "trace.jsonl")
    evidence_rows = _load_jsonl(session_dir / "evidence.jsonl")

    turns = _as_list(run.get("turns"))
    last_turn = turns[-1] if turns and isinstance(turns[-1], dict) else {}
    category = _as_dict(last_turn.get("category"))
    communicate_meta = _as_dict(last_turn.get("communicate_meta"))
    act_counts = _as_dict(communicate_meta.get("act_counts"))

    objections = _as_list(run.get("objections"))
    actions = _as_list(run.get("actions"))
    approvals = _as_list(run.get("approvals"))
    executions = _as_list(run.get("executions"))
    agents = _as_list(run.get("agents"))
    mission_loop = _as_dict(run.get("mission_loop"))
    plan_workflow = _as_dict(run.get("plan_workflow"))
    turn_policy = _as_dict(run.get("turn_policy"))
    verified_loop = _as_dict(run.get("verified_loop"))
    goal_loop = _as_dict(run.get("goal_loop"))
    succeeded_agents = _as_list(last_turn.get("succeeded_agents"))
    reply_meta = _as_dict(communicate_meta.get("reply_policy"))
    message_count = _as_int(run.get("message_count"))
    agent_parallel_rounds = _as_int(run.get("agent_parallel_rounds"))
    agent_reply_count = _as_int(communicate_meta.get("agent_reply_count"))
    envelope_parse_error_count = _as_int(communicate_meta.get("envelope_parse_error_count"))
    last_plan_update = run.get("last_plan_update")
    workflow_id = run.get("workflow_id")

    chat_message_count = len(chat_rows)
    trace_names = {
        str(row.get("name"))
        for row in trace_rows
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    }
    evidence_phases = {
        str(row.get("phase"))
        for row in evidence_rows
        if isinstance(row, dict) and isinstance(row.get("phase"), str)
    }
    evidence_kinds = {
        str(row.get("kind"))
        for row in evidence_rows
        if isinstance(row, dict) and isinstance(row.get("kind"), str)
    }

    unresolved_block = any(
        isinstance(o, dict) and str(o.get("act")) == "BLOCK" and not str(o.get("status") or "").startswith("resolved")
        for o in objections
    )
    has_oracle = any(
        isinstance(e, dict) and (e.get("oracle") or e.get("oracle_verdict") or e.get("verify_after_merge")) for e in executions
    )
    has_execute_signal = bool(executions) or bool(evidence_phases & {"DRY_RUN", "EXECUTE", "MERGE", "VERIFY"})
    has_oracle = has_oracle or bool(evidence_phases & {"VERIFY"}) or bool(
        evidence_kinds & {"oracle_verify", "verify", "verify_pass", "verify_fail"}
    )
    has_feedback_signal = bool(reply_meta) or bool(run.get("feedback_advisor")) or "feedback_advisor" in trace_names
    has_plan_signal = (
        bool(actions)
        or bool(plan_workflow)
        or bool(last_plan_update)
        or (session_dir / "plan.md").is_file()
        or any(isinstance(o, dict) and (o.get("target_ref") or o.get("plan_action_index")) for o in objections)
    )
    has_human_gate_signal = (
        bool(approvals)
        or unresolved_block
        or bool(plan_workflow.get("approved_at"))
        or bool(verified_loop.get("loop_goal"))
        or any(isinstance(e, dict) and "pending_approval" in str(e.get("status") or "") for e in executions)
        or bool(evidence_kinds & {"merge_approve", "approval", "human_approve"})
    )
    has_room_round_signal = bool(
        message_count or agent_parallel_rounds or agent_reply_count or chat_message_count or trace_rows or turns
    )
    route_data = category or {
        key: value
        for key, value in {
            "workflow_id": workflow_id if isinstance(workflow_id, str) else "",
            "turn_profile": run.get("turn_profile") or last_turn.get("turn_profile") or last_turn.get("mode") or "",
            "mode": last_turn.get("mode") if isinstance(last_turn.get("mode"), str) else "",
        }.items()
        if value
    }
    role_plan_data = {
        "agents": agents,
        "turn_agents": _as_list(last_turn.get("agents")),
        "succeeded_agents": succeeded_agents,
        "objection_authors": sorted(
            {
                str(o.get("from"))
                for o in objections
                if isinstance(o, dict) and isinstance(o.get("from"), str) and str(o.get("from")).strip()
            }
        ),
    }
    role_plan_present = any(role_plan_data.values()) or "role_plan" in trace_names

    spans: list[dict[str, Any]] = []

    def _span(name: str, present: bool, data: dict[str, Any] | None = None) -> None:
        if present:
            spans.append({"name": name, "data": data or {}})

    _span("route", bool(route_data) or "route" in trace_names, route_data)
    _span("role_plan", role_plan_present, role_plan_data)
    _span(
        "room_round",
        has_room_round_signal or "room_round" in trace_names,
        {
            "message_count": message_count,
            "chat_message_count": chat_message_count,
            "agent_parallel_rounds": agent_parallel_rounds,
            "agent_reply_count": agent_reply_count,
        },
    )
    _span("objection", bool(objections) or bool(act_counts), {"act_counts": act_counts, "objection_count": len(objections)})
    _span(
        "plan_update",
        has_plan_signal or "plan_update" in trace_names,
        {
            "action_count": len(actions),
            "plan_workflow_phase": plan_workflow.get("phase"),
            "last_plan_update": last_plan_update if isinstance(last_plan_update, str) else "",
            "plan_md_present": (session_dir / "plan.md").is_file(),
        },
    )
    _span(
        "human_gate",
        has_human_gate_signal or "human_gate" in trace_names,
        {
            "approval_count": len(approvals),
            "unresolved_block": unresolved_block,
            "plan_approved_at": plan_workflow.get("approved_at"),
            "has_verified_loop_goal": bool(verified_loop.get("loop_goal")),
            "evidence_kinds": sorted(evidence_kinds),
        },
    )
    _span(
        "execute",
        has_execute_signal or "execute" in trace_names,
        {
            "execution_count": len(executions),
            "statuses": [str(e.get("status") or "") for e in executions if isinstance(e, dict)],
            "isolation_effective": [str(e.get("isolation_effective") or "") for e in executions if isinstance(e, dict)],
            "evidence_phases": sorted(evidence_phases),
        },
    )
    _span(
        "oracle_verify",
        has_oracle or "oracle_verify" in trace_names,
        {
            "mission_phase": mission_loop.get("phase"),
            "last_verify": _as_dict(mission_loop.get("last_verify")),
        },
    )
    _span(
        "feedback_advisor",
        has_feedback_signal,
        {
            "reply_policy": reply_meta,
            "feedback_advisor": _as_dict(run.get("feedback_advisor")),
        },
    )

    final_oracle_verdict = None
    if executions and isinstance(executions[-1], dict):
        last_execution = executions[-1]
        oracle = last_execution.get("oracle")
        if isinstance(oracle, dict):
            final_oracle_verdict = oracle.get("verdict")
        elif isinstance(last_execution.get("oracle_verdict"), str):
            final_oracle_verdict = last_execution.get("oracle_verdict")
        else:
            verify_after_merge = _as_dict(last_execution.get("verify_after_merge"))
            verify_oracle = _as_dict(verify_after_merge.get("oracle"))
            if isinstance(verify_oracle.get("verdict"), str):
                final_oracle_verdict = verify_oracle.get("verdict")

    return {
        "case_id": case_id,
        "session_id": session_dir.name,
        "topic": run.get("topic") or "",
        "room_preset": run.get("workflow_id") or "",
        "turn_profile": run.get("turn_profile") or last_turn.get("turn_profile") or last_turn.get("mode") or "",
        "spans": spans,
        "artifacts": {
            "category": category,
            "act_counts": act_counts,
            "objections": objections,
            "actions": actions,
            "approvals": approvals,
            "executions": executions,
            "agents": agents,
            "succeeded_agents": succeeded_agents,
            "message_count": message_count,
            "agent_parallel_rounds": agent_parallel_rounds,
            "agent_reply_count": agent_reply_count,
            "envelope_parse_error_count": envelope_parse_error_count,
            "reply_policy": reply_meta,
            "session_status": run.get("status") if isinstance(run.get("status"), str) else "",
            "synthesize": run.get("synthesize") if isinstance(run.get("synthesize"), bool) else False,
            "plan_md_present": (session_dir / "plan.md").is_file(),
            "chat_message_count": chat_message_count,
            "trace_message_count": len(trace_rows),
            "plan_workflow": plan_workflow,
            "turn_policy": turn_policy,
            "verified_loop": verified_loop,
            "goal_loop": goal_loop,
            "evidence_ledger": _as_dict(run.get("evidence_ledger")),
            "evidence_phases": sorted(evidence_phases),
            "evidence_kinds": sorted(evidence_kinds),
        },
        "outcome": {
            "final_oracle_verdict": final_oracle_verdict,
            "mission_loop_phase": mission_loop.get("phase"),
        },
    }
