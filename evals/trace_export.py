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


def export_session_trace(session_dir: Path, *, case_id: str = "") -> dict[str, Any]:
    """Export a session folder into an EvalTrace dict. Never raises."""
    run = _load_json(session_dir / "run.json")

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
    succeeded_agents = _as_list(last_turn.get("succeeded_agents"))
    reply_meta = _as_dict(communicate_meta.get("reply_policy"))
    message_count = _as_int(run.get("message_count"))
    agent_parallel_rounds = _as_int(run.get("agent_parallel_rounds"))
    agent_reply_count = _as_int(communicate_meta.get("agent_reply_count"))
    envelope_parse_error_count = _as_int(communicate_meta.get("envelope_parse_error_count"))

    unresolved_block = any(
        isinstance(o, dict) and str(o.get("act")) == "BLOCK" and not str(o.get("status") or "").startswith("resolved")
        for o in objections
    )
    has_oracle = any(isinstance(e, dict) and e.get("oracle") for e in executions)

    spans: list[dict[str, Any]] = []

    def _span(name: str, present: bool, data: dict[str, Any] | None = None) -> None:
        if present:
            spans.append({"name": name, "data": data or {}})

    _span("route", bool(category), category)
    _span("role_plan", bool(agents), {"agents": agents})
    _span("room_round", bool(message_count or agent_parallel_rounds))
    _span("objection", bool(objections) or bool(act_counts), {"act_counts": act_counts, "objection_count": len(objections)})
    _span("plan_update", bool(actions), {"action_count": len(actions)})
    _span("human_gate", bool(approvals) or unresolved_block, {"approval_count": len(approvals)})
    _span("execute", bool(executions), {"execution_count": len(executions)})
    _span("oracle_verify", has_oracle)
    # v1 limitation: feedback_advisor span requires joining .agent-lab/outcomes.jsonl
    # by session_id, which fixture sessions don't carry — always absent for now
    # (lowers trace_completeness rather than failing; see EVAL-SURFACE-V1-PLAN.md §2).

    final_oracle_verdict = None
    if executions and isinstance(executions[-1], dict):
        oracle = executions[-1].get("oracle")
        if isinstance(oracle, dict):
            final_oracle_verdict = oracle.get("verdict")

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
        },
        "outcome": {
            "final_oracle_verdict": final_oracle_verdict,
            "mission_loop_phase": mission_loop.get("phase"),
        },
    }
