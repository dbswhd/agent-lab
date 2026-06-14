"""Lane-aware Human gate scope — gate_profile policy (Mission OS Phase 2)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

GateProfile = Literal["dev", "assistant"]
DiscussPolicy = Literal["allow", "pause"]
PlanWorkflowPolicy = Literal["allow", "block_clarify"]
ExecutePolicy = Literal["allow", "block"]


@dataclass(frozen=True)
class GateScope:
    gate_profile: GateProfile
    discuss_rounds: DiscussPolicy
    plan_workflow: PlanWorkflowPolicy
    execute: ExecutePolicy


def get_gate_profile(run_meta: dict[str, Any] | None) -> GateProfile:
    """Read ``gate_profile`` from run.json (not Mission Board orchestration lane)."""
    meta = run_meta or {}
    raw = str(meta.get("gate_profile") or "").strip().lower()
    if raw in ("dev", "assistant"):
        return raw  # type: ignore[return-value]
    # Schedule/template legacy on nested entries only — top-level default dev.
    return "dev"


def _pending_by_kind(run_meta: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    from agent_lab.human_inbox import pending_inbox_items

    grouped: dict[str, list[dict[str, Any]]] = {
        "question": [],
        "build": [],
        "other": [],
    }
    for item in pending_inbox_items(run_meta):
        kind = str(item.get("kind") or "other")
        if kind in grouped:
            grouped[kind].append(item)
        else:
            grouped["other"].append(item)
    return grouped


def compute_gate_scope(run_meta: dict[str, Any] | None) -> GateScope:
    """Policy table: dev=discuss pause on Human-direction inbox; assistant=soft discuss."""
    from agent_lab.inbox_harvest import has_pending_discuss_pause_question

    profile = get_gate_profile(run_meta)
    pending = _pending_by_kind(run_meta or {})
    has_pause_q = has_pending_discuss_pause_question(run_meta or {})
    has_build = bool(pending["build"])

    if profile == "assistant":
        discuss: DiscussPolicy = "allow"
    else:
        discuss = "pause" if has_pause_q else "allow"

    plan_workflow: PlanWorkflowPolicy = "block_clarify" if has_pause_q else "allow"
    execute: ExecutePolicy = "block" if has_build else "allow"

    return GateScope(
        gate_profile=profile,
        discuss_rounds=discuss,
        plan_workflow=plan_workflow,
        execute=execute,
    )


def should_pause_discuss_for_profile(run_meta: dict[str, Any]) -> bool:
    """Replace env-only pause when ``AGENT_LAB_GATE_SCOPE=1`` (default on)."""
    import os

    if os.getenv("AGENT_LAB_GATE_SCOPE", "1").strip().lower() in ("0", "false", "no"):
        from agent_lab.inbox_harvest import should_pause_discuss

        return should_pause_discuss(run_meta)
    scope = compute_gate_scope(run_meta)
    return scope.discuss_rounds == "pause"


def plan_clarify_blocked(run_meta: dict[str, Any]) -> bool:
    return compute_gate_scope(run_meta).plan_workflow == "block_clarify"


def execute_scope_blocked(run_meta: dict[str, Any]) -> bool:
    return compute_gate_scope(run_meta).execute == "block"


def public_gate_scope_payload(run_meta: dict[str, Any] | None) -> dict[str, Any]:
    scope = compute_gate_scope(run_meta)
    pending = _pending_by_kind(run_meta or {})
    return {
        "gate_profile": scope.gate_profile,
        "discuss": {
            "open": scope.discuss_rounds == "allow",
            "reason": ("pending_question" if scope.discuss_rounds == "pause" else None),
        },
        "plan_clarify": {
            "open": scope.plan_workflow == "allow",
            "reason": ("pending_inbox_question" if scope.plan_workflow == "block_clarify" else None),
        },
        "execute": {
            "open": scope.execute == "allow",
            "reason": "pending_build" if scope.execute == "block" else None,
        },
        "inbox": {
            "pending_questions": len(pending["question"]),
            "pending_builds": len(pending["build"]),
            "kinds": [k for k, rows in pending.items() if rows and k != "other"],
        },
    }


def set_gate_profile(folder: Path, profile: GateProfile) -> dict[str, Any]:
    from agent_lab.run_meta import patch_run_meta

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        run["gate_profile"] = profile
        return run

    return patch_run_meta(folder, _patch)
