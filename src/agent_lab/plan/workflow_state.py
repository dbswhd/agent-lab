from __future__ import annotations

"""Plan workflow FSM — state, phases, init, public snapshots."""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from agent_lab.plan.actions import parse_plan_actions
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.run.state import RunState, RunStateLike
from agent_lab.verified_loop import DEFAULT_COMPLETION_PROMISE

PlanWorkflowPhase = Literal[
    "INTAKE",
    "CLARIFY",
    "DRAFT",
    "PEER_REVIEW",
    "REFINE",
    "HUMAN_PENDING",
    "APPROVED",
]

DEFAULT_MAX_CLARIFY_ROUNDS = 3
DEFAULT_MAX_PEER_REVIEW_ROUNDS = 2

PLAN_WORKFLOW_RECEIPTS: dict[str, str] = {
    "INTAKE": "plan_clarify",
    "CLARIFY": "plan_clarify",
    "DRAFT": "plan_draft",
    "PEER_REVIEW": "plan_peer_review",
    "REFINE": "plan_refine",
    "HUMAN_PENDING": "plan_pending_approval",
    "APPROVED": "plan_approved",
}

PLAN_DRAFT_PHASES = frozenset({"DRAFT", "REFINE"})
PLAN_PRE_APPROVAL = frozenset({"INTAKE", "CLARIFY", "DRAFT", "PEER_REVIEW", "REFINE", "HUMAN_PENDING"})
VERIFIED_PROPOSING = frozenset({"INTAKE", "CLARIFY", "DRAFT", "PEER_REVIEW", "REFINE"})
PLAN_CLARIFY_PHASES = frozenset({"INTAKE", "CLARIFY"})
PLAN_PEER_PHASES = frozenset({"PEER_REVIEW"})
PLAN_FSM_ORDER = ("INTAKE", "CLARIFY", "DRAFT", "PEER_REVIEW", "REFINE", "HUMAN_PENDING", "APPROVED")
MCP_ADVANCE_TARGETS = frozenset({"CLARIFY", "DRAFT", "PEER_REVIEW", "REFINE", "HUMAN_PENDING"})


def plan_fsm_skill_first_enabled() -> bool:
    """P3: phase/clarity authority via MCP first; server tick holds + cap fallback only."""
    return os.getenv("AGENT_LAB_PLAN_FSM_SKILL_FIRST", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


class PlanWorkflowNotApproved(Exception):
    """Raised when execute/dry-run requires whole-plan Human approval first."""

    def __init__(
        self,
        phase: str | None = None,
        reason: str = "plan_workflow_approval_required",
    ) -> None:
        self.phase = phase
        super().__init__(reason)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def plan_workflow_env_disabled() -> bool:
    raw = (os.getenv("AGENT_LAB_PLAN_WORKFLOW") or "").strip().lower()
    return raw in ("0", "false", "no", "off")


def should_enable_plan_workflow(*, synthesize: bool) -> bool:
    if plan_workflow_env_disabled():
        return False
    return bool(synthesize)


def plan_workflow_should_advance_on_turn(
    run: RunStateLike | None,
    *,
    synthesize: bool,
) -> bool:
    """FSM ticks (scribe / peer / phase advance) only on explicit plan-mode sends."""
    if not is_plan_workflow_active(run):
        return False
    return bool(synthesize)


def apply_legacy_verified_turn_profile(
    folder: Path | None,
    run_meta: RunStateLike,
    *,
    synthesize: bool,
) -> None:
    tp = str(run_meta.get("turn_profile") or "").strip().lower()
    if tp != "verified":
        return
    if should_enable_plan_workflow(synthesize=synthesize):
        return
    if folder is not None:
        from agent_lab.verified_loop import init_verified_loop

        init_verified_loop(folder)


def _round_cap(raw: object, default: int) -> int:
    if raw is None or isinstance(raw, bool):
        return default
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if text.isdigit():
            return int(text)
    return default


def resolved_max_peer_review_rounds() -> int:
    """Env override for plan peer-review ITERATE cap (``AGENT_LAB_MAX_PEER_REVIEW_ROUNDS``)."""
    raw = (os.getenv("AGENT_LAB_MAX_PEER_REVIEW_ROUNDS") or "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return DEFAULT_MAX_PEER_REVIEW_ROUNDS


def effective_max_peer_review_rounds(pw: dict[str, Any]) -> int:
    env_raw = (os.getenv("AGENT_LAB_MAX_PEER_REVIEW_ROUNDS") or "").strip()
    if env_raw:
        return resolved_max_peer_review_rounds()
    return _round_cap(pw.get("max_peer_review_rounds"), DEFAULT_MAX_PEER_REVIEW_ROUNDS)


def default_plan_workflow() -> dict[str, Any]:
    return {
        "enabled": False,
        "phase": "INTAKE",
        "clarify_round": 0,
        "max_clarify_rounds": DEFAULT_MAX_CLARIFY_ROUNDS,
        "peer_review_round": 0,
        "max_peer_review_rounds": resolved_max_peer_review_rounds(),
        "last_peer_verdict": None,
        "plan_hash_at_approval": None,
        "approved_at": None,
        "approved_by": None,
    }


def get_plan_workflow(run: RunStateLike | None) -> dict[str, Any]:
    raw = (run or {}).get("plan_workflow")
    if not isinstance(raw, dict):
        return default_plan_workflow()
    base = default_plan_workflow()
    base.update(raw)
    return base


def is_plan_workflow_active(run: RunStateLike | None) -> bool:
    pw = get_plan_workflow(run)
    return bool(pw.get("enabled"))


def plan_workflow_phase(run: RunStateLike | None) -> str:
    return str(get_plan_workflow(run).get("phase") or "INTAKE")


def plan_workflow_wants_inbox_mcp(run: RunStateLike | None) -> bool:
    from agent_lab.room.preset import is_fast_room_session

    if is_fast_room_session(run):
        return False
    if not is_plan_workflow_active(run):
        return False
    return plan_workflow_phase(run) in PLAN_CLARIFY_PHASES


def plan_workflow_allows_scribe(
    run: RunStateLike | None,
    *,
    synthesize: bool,
    user_plan_send: bool,
) -> bool:
    if not is_plan_workflow_active(run):
        return synthesize or _auto_plan_scribe_fallback()
    if not synthesize:
        return False
    phase = plan_workflow_phase(run)
    if phase in PLAN_DRAFT_PHASES:
        return True
    if phase in PLAN_CLARIFY_PHASES:
        return False
    if phase in PLAN_PEER_PHASES:
        return False
    if phase == "HUMAN_PENDING":
        return False
    if phase == "APPROVED":
        return user_plan_send and synthesize
    return False


def plan_workflow_allows_auto_scribe(run: RunStateLike | None) -> bool:
    if is_plan_workflow_active(run):
        return False
    return _auto_plan_scribe_fallback()


def _auto_plan_scribe_fallback() -> bool:
    raw = os.getenv("AGENT_LAB_AUTO_PLAN_SCRIBE", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def plan_workflow_skips_goal_check(run: RunStateLike | None) -> bool:
    return is_plan_workflow_active(run)


def plan_workflow_skips_server_clarifier(run: RunStateLike | None) -> bool:
    return is_plan_workflow_active(run)


def plan_workflow_completed_clarify(run: RunStateLike | None) -> bool:
    """True when plan_workflow already passed CLARIFY (single clarify owner)."""
    if not is_plan_workflow_active(run):
        return False
    return plan_workflow_phase(run) not in PLAN_CLARIFY_PHASES


def _reset_plan_workflow_state(pw: dict[str, Any]) -> dict[str, Any]:
    pw = dict(pw)
    pw["enabled"] = True
    pw["phase"] = "CLARIFY"
    pw["clarify_round"] = 0
    pw["peer_review_round"] = 0
    pw["max_peer_review_rounds"] = resolved_max_peer_review_rounds()
    for key in (
        "plan_hash_at_approval",
        "approved_at",
        "approved_by",
        "notice",
        "last_plan_gate",
    ):
        pw.pop(key, None)
    return pw


def init_plan_workflow_on_plan_send(folder: Path) -> dict[str, Any]:
    from agent_lab.plan.paths import begin_session_plan_cycle

    def _init(run: RunState) -> RunState:
        pw = get_plan_workflow(run)
        phase = str(pw.get("phase") or "")

        if pw.get("enabled") and phase == "APPROVED":
            begin_session_plan_cycle(folder, run)
            pw = _reset_plan_workflow_state(get_plan_workflow(run))
            run["plan_workflow"] = pw
            _mirror_verified_loop_status(run, pw)
            return run

        if pw.get("enabled") and phase in PLAN_PRE_APPROVAL:
            pw["enabled"] = True
            pw.setdefault("max_peer_review_rounds", resolved_max_peer_review_rounds())
            run["plan_workflow"] = pw
            _mirror_verified_loop_status(run, pw)
            return run

        if not pw.get("enabled"):
            begin_session_plan_cycle(folder, run)

        pw = get_plan_workflow(run)
        pw["enabled"] = True
        pw["max_peer_review_rounds"] = resolved_max_peer_review_rounds()
        if pw.get("phase") not in PLAN_PRE_APPROVAL and pw.get("phase") != "APPROVED":
            pw["phase"] = "CLARIFY"
        elif pw.get("phase") == "INTAKE":
            pw["phase"] = "CLARIFY"
        run["plan_workflow"] = pw
        _mirror_verified_loop_status(run, pw)
        return run

    patch_run_meta(folder, _init)
    return get_plan_workflow(read_run_meta(folder))


def _mirror_verified_loop_status(run: RunStateLike, pw: dict[str, Any]) -> None:
    loop = dict(run.get("verified_loop") or {})
    phase = str(pw.get("phase") or "INTAKE")
    if phase == "APPROVED":
        if loop.get("status") not in {"done", "failed", "cancelled"}:
            loop["status"] = "running"
    elif phase == "HUMAN_PENDING":
        loop["status"] = "pending_approval"
    elif phase in VERIFIED_PROPOSING or phase == "INTAKE":
        if loop.get("status") not in {"running", "done", "failed", "cancelled"}:
            loop["status"] = "proposing"
    run["verified_loop"] = loop


def set_plan_workflow_phase(folder: Path, phase: PlanWorkflowPhase) -> dict[str, Any]:
    def _set(run: RunState) -> RunState:
        pw = get_plan_workflow(run)
        pw["enabled"] = True
        pw["phase"] = phase
        run["plan_workflow"] = pw
        _mirror_verified_loop_status(run, pw)
        return run

    patch_run_meta(folder, _set)
    return get_plan_workflow(read_run_meta(folder))


def derive_loop_goal_from_plan(plan_md: str) -> dict[str, str]:
    text = (plan_md or "").strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = ""
    for ln in lines:
        if ln.startswith("#"):
            title = ln.lstrip("#").strip()
            break
    if not title:
        title = lines[0][:500] if lines else "Session plan"
    actions = parse_plan_actions(plan_md or "")
    verify_bits = [a.verify.strip() for a in actions if a.verify.strip()]
    criteria = "; ".join(verify_bits[:8]) if verify_bits else title
    return {
        "goal": title,
        "completion_promise": DEFAULT_COMPLETION_PROMISE,
        "criteria": criteria[:2000],
    }


def plan_workflow_send_receipt(phase: str | None) -> str | None:
    if not phase:
        return None
    return PLAN_WORKFLOW_RECEIPTS.get(phase.strip().upper())


def plan_workflow_complete_payload(folder: Path) -> dict[str, Any]:
    run = read_run_meta(folder)
    if not is_plan_workflow_active(run):
        return {}
    pw = get_plan_workflow(run)
    phase = str(pw.get("phase") or "")
    out: dict[str, Any] = {
        "plan_workflow_phase": phase,
        "plan_workflow_pending_approval": phase == "HUMAN_PENDING",
    }
    notice = pw.get("notice")
    if notice:
        out["plan_workflow_notice"] = notice
    gate = pw.get("last_plan_gate")
    if isinstance(gate, dict) and gate:
        out["plan_workflow_gate"] = gate
    return out


def emit_plan_workflow_phase_if_changed(
    folder: Path,
    on_event: Any | None,
    phase_before: str | None,
    phase_after: str | None,
) -> None:
    if not on_event or not phase_after or phase_after == phase_before:
        return
    pw = get_plan_workflow(read_run_meta(folder))
    payload: dict[str, Any] = {
        "session_id": folder.name,
        "phase": phase_after,
        "clarify_round": pw.get("clarify_round"),
        "peer_review_round": pw.get("peer_review_round"),
    }
    notice = pw.get("notice")
    if notice:
        payload["notice"] = notice
    gate = pw.get("last_plan_gate")
    if isinstance(gate, dict) and gate:
        payload["plan_gate"] = gate
    on_event("plan_workflow_phase", payload)


def plan_workflow_public(run: RunStateLike | None) -> dict[str, Any]:
    pw = get_plan_workflow(run)
    return {
        "plan_workflow": pw,
        "plan_workflow_pending_approval": pw.get("enabled") and pw.get("phase") == "HUMAN_PENDING",
    }


def resolve_work_phase_from_plan_workflow(phase: str | None) -> str | None:
    if phase is None or not phase.strip():
        return None
    p = phase.strip().upper()
    if p == "HUMAN_PENDING":
        return "review_needed"
    if p == "APPROVED":
        return "execute_pending"
    if p in {"INTAKE", "CLARIFY", "DRAFT", "PEER_REVIEW", "REFINE"}:
        return "plan_draft"
    return None
