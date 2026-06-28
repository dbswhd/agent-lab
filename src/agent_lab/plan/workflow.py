"""Plan-First Workflow FSM — Merge Verified (4C-style plan mode)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from agent_lab.plan.actions import parse_plan_actions
from agent_lab.plan.pending import plan_content_hash
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.turn_modes import approval_starts_execute_loop
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

_PLAN_DRAFT_PHASES = frozenset({"DRAFT", "REFINE"})
_PLAN_PRE_APPROVAL = frozenset({"INTAKE", "CLARIFY", "DRAFT", "PEER_REVIEW", "REFINE", "HUMAN_PENDING"})
_VERIFIED_PROPOSING = frozenset({"INTAKE", "CLARIFY", "DRAFT", "PEER_REVIEW", "REFINE"})
_PLAN_CLARIFY_PHASES = frozenset({"INTAKE", "CLARIFY"})
_PLAN_PEER_PHASES = frozenset({"PEER_REVIEW"})


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
    run: dict[str, Any] | None,
    *,
    synthesize: bool,
) -> bool:
    """FSM ticks (scribe / peer / phase advance) only on explicit plan-mode sends."""
    if not is_plan_workflow_active(run):
        return False
    return bool(synthesize)


def apply_legacy_verified_turn_profile(
    folder: Path | None,
    run_meta: dict[str, Any],
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


def get_plan_workflow(run: dict[str, Any] | None) -> dict[str, Any]:
    raw = (run or {}).get("plan_workflow")
    if not isinstance(raw, dict):
        return default_plan_workflow()
    base = default_plan_workflow()
    base.update(raw)
    return base


def is_plan_workflow_active(run: dict[str, Any] | None) -> bool:
    pw = get_plan_workflow(run)
    return bool(pw.get("enabled"))


def plan_workflow_phase(run: dict[str, Any] | None) -> str:
    return str(get_plan_workflow(run).get("phase") or "INTAKE")


def plan_workflow_wants_inbox_mcp(run: dict[str, Any] | None) -> bool:
    from agent_lab.room.preset import is_fast_room_session

    if is_fast_room_session(run):
        return False
    if not is_plan_workflow_active(run):
        return False
    return plan_workflow_phase(run) in _PLAN_CLARIFY_PHASES


def plan_workflow_allows_scribe(
    run: dict[str, Any] | None,
    *,
    synthesize: bool,
    user_plan_send: bool,
) -> bool:
    if not is_plan_workflow_active(run):
        return synthesize or _auto_plan_scribe_fallback()
    if not synthesize:
        return False
    phase = plan_workflow_phase(run)
    if phase in _PLAN_DRAFT_PHASES:
        return True
    if phase in _PLAN_CLARIFY_PHASES:
        return False
    if phase in _PLAN_PEER_PHASES:
        return False
    if phase == "HUMAN_PENDING":
        return False
    if phase == "APPROVED":
        return user_plan_send and synthesize
    return False


def plan_workflow_allows_auto_scribe(run: dict[str, Any] | None) -> bool:
    if is_plan_workflow_active(run):
        return False
    return _auto_plan_scribe_fallback()


def _auto_plan_scribe_fallback() -> bool:
    raw = os.getenv("AGENT_LAB_AUTO_PLAN_SCRIBE", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def plan_workflow_skips_goal_check(run: dict[str, Any] | None) -> bool:
    return is_plan_workflow_active(run)


def plan_workflow_skips_server_clarifier(run: dict[str, Any] | None) -> bool:
    return is_plan_workflow_active(run)


def plan_workflow_completed_clarify(run: dict[str, Any] | None) -> bool:
    """True when plan_workflow already passed CLARIFY (single clarify owner)."""
    if not is_plan_workflow_active(run):
        return False
    return plan_workflow_phase(run) not in _PLAN_CLARIFY_PHASES


def init_plan_workflow_on_plan_send(folder: Path) -> dict[str, Any]:
    def _init(run: dict[str, Any]) -> dict[str, Any]:
        pw = get_plan_workflow(run)
        if pw.get("enabled") and pw.get("phase") == "APPROVED":
            return run
        pw["enabled"] = True
        pw["max_peer_review_rounds"] = resolved_max_peer_review_rounds()
        if pw.get("phase") not in _PLAN_PRE_APPROVAL and pw.get("phase") != "APPROVED":
            pw["phase"] = "CLARIFY"
        elif pw.get("phase") == "INTAKE":
            pw["phase"] = "CLARIFY"
        run["plan_workflow"] = pw
        _mirror_verified_loop_status(run, pw)
        return run

    patch_run_meta(folder, _init)
    return get_plan_workflow(read_run_meta(folder))


def _mirror_verified_loop_status(run: dict[str, Any], pw: dict[str, Any]) -> None:
    loop = dict(run.get("verified_loop") or {})
    phase = str(pw.get("phase") or "INTAKE")
    if phase == "APPROVED":
        if loop.get("status") not in {"done", "failed", "cancelled"}:
            loop["status"] = "running"
    elif phase == "HUMAN_PENDING":
        loop["status"] = "pending_approval"
    elif phase in _VERIFIED_PROPOSING or phase == "INTAKE":
        if loop.get("status") not in {"running", "done", "failed", "cancelled"}:
            loop["status"] = "proposing"
    run["verified_loop"] = loop


def set_plan_workflow_phase(folder: Path, phase: PlanWorkflowPhase) -> dict[str, Any]:
    def _set(run: dict[str, Any]) -> dict[str, Any]:
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


def build_clarify_context_block(folder: Path) -> str:
    from agent_lab.human_inbox import inbox_items

    run = read_run_meta(folder)
    rows: list[str] = []
    for item in inbox_items(run):
        if item.get("kind") != "question":
            continue
        if item.get("status") not in {"resolved", "deferred"}:
            continue
        prompt = str(item.get("prompt") or "").strip()
        if not prompt:
            continue
        choice = item.get("resolved_choice")
        selected = item.get("resolved_selected")
        answer = choice if choice is not None else selected
        if answer is None:
            answer = item.get("resolved_note") or item.get("resolved_text") or ""
        rows.append(f"Q: {prompt}\nA: {answer}")
    if not rows:
        return ""
    return "## Clarifier answers (Human Inbox)\n\n" + "\n\n".join(rows)


PLAN_CLARIFY_GUIDANCE = (
    "Plan workflow CLARIFY phase: ask Human clarifying questions via the "
    "`ask_human` tool only (never ask in prose). Each question needs at least "
    "two options. Focus on goal, scope, verify criteria, and constraints."
)

PLAN_PEER_REVIEW_GUIDANCE = (
    "Plan peer review: read plan.md only. Do not propose code changes. "
    "Use envelope CHALLENGE or ENDORSE on specific plan actions or sections. "
    "Reference plan_action:N in refs when applicable."
)

PLAN_ARCHITECT_REVIEW_GUIDANCE = (
    "Plan architect review (ralplan architect seat): read plan.md only. "
    "Evaluate structure, dependencies, scope boundaries, and whether each action has "
    "a testable verify criterion. CHALLENGE architectural gaps; ENDORSE when the plan "
    "is coherent. No code changes."
)

PLAN_CRITIC_REVIEW_GUIDANCE = (
    "Plan critic review (ralplan critic seat): adversarial read of plan.md only. "
    "Find the weakest assumption, missing edge case, or unverifiable claim. "
    "CHALLENGE or AMEND one concrete issue; ENDORSE only with a one-line rationale. "
    "No code changes."
)


PLAN_FRESH_EYES_GUIDANCE = (
    "[anti-drift · fresh-eyes 냉정 검토] 이전 토론 맥락 없이 plan.md만 처음 보는 외부 검토자로서 "
    "읽으세요. 합의가 형성됐다는 가정을 버리고, 가장 위험한 가정·누락된 엣지케이스·검증 불가한 "
    "주장 1건을 골라 CHALLENGE 또는 AMEND envelope로 제시하세요. 정말 문제가 없으면 근거를 한 줄로 "
    "밝히고 ENDORSE 하세요. 코드 변경은 제안하지 마세요."
)


def ensure_plan_workflow_approved(folder: Path) -> None:
    run = read_run_meta(folder)
    if not is_plan_workflow_active(run):
        return
    workflow = get_plan_workflow(run)
    phase = str(workflow.get("phase") or "INTAKE")
    if phase != "APPROVED":
        raise PlanWorkflowNotApproved(phase)
    plan_path = folder / "plan.md"
    plan_md = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
    approved_hash = str(workflow.get("plan_hash_at_approval") or "")
    if approved_hash and approved_hash == plan_content_hash(plan_md):
        return

    def _invalidate(current: dict[str, Any]) -> dict[str, Any]:
        current_workflow = get_plan_workflow(current)
        current_workflow["phase"] = "HUMAN_PENDING"
        current_workflow["notice"] = "plan_changed_after_approval"
        current["plan_workflow"] = current_workflow
        _mirror_verified_loop_status(current, current_workflow)
        return current

    patch_run_meta(folder, _invalidate)
    raise PlanWorkflowNotApproved(phase, "plan_workflow_plan_changed")


def approve_plan(
    session_folder: Path,
    *,
    goal: str | None = None,
    completion_promise: str | None = None,
    criteria: str | None = None,
    plan_md: str | None = None,
) -> dict[str, Any]:
    run = read_run_meta(session_folder)
    pw = get_plan_workflow(run)
    if not pw.get("enabled"):
        raise ValueError("plan workflow is not enabled")
    if str(pw.get("phase") or "") != "HUMAN_PENDING":
        raise ValueError("plan is not awaiting Human approval")
    return _finalize_plan_approval(
        session_folder,
        goal=goal,
        completion_promise=completion_promise,
        criteria=criteria,
        plan_md=plan_md,
        approved_by="human",
    )


def approve_plan_bypass(
    session_folder: Path,
    *,
    goal: str | None = None,
    completion_promise: str | None = None,
    criteria: str | None = None,
    plan_md: str | None = None,
    approved_by: str = "template",
) -> dict[str, Any]:
    """Template fast-path — skip HUMAN_PENDING; reuse approve side effects."""
    return _finalize_plan_approval(
        session_folder,
        goal=goal,
        completion_promise=completion_promise,
        criteria=criteria,
        plan_md=plan_md,
        approved_by=approved_by,
        enable_workflow=True,
    )


def _finalize_plan_approval(
    session_folder: Path,
    *,
    goal: str | None = None,
    completion_promise: str | None = None,
    criteria: str | None = None,
    plan_md: str | None = None,
    approved_by: str = "human",
    enable_workflow: bool = False,
) -> dict[str, Any]:
    path = session_folder / "plan.md"
    md = plan_md if plan_md is not None else (path.read_text(encoding="utf-8") if path.is_file() else "")
    if not (md or "").strip():
        raise ValueError("plan.md is empty")

    derived = derive_loop_goal_from_plan(md)
    goal_text = (goal or derived["goal"]).strip()
    criteria_resolved = (criteria or derived["criteria"]).strip() or goal_text
    promise = (completion_promise or derived["completion_promise"]).strip() or DEFAULT_COMPLETION_PROMISE
    if not goal_text:
        raise ValueError("plan goal text is required")

    plan_hash = plan_content_hash(md)
    now = _now()
    approved = {
        "text": goal_text,
        "completion_promise": promise,
        "criteria": criteria_resolved,
        "approved_at": now,
        "approved_by": approved_by,
    }
    oracle_session_id = f"oracle_{session_folder.name}_{uuid.uuid4().hex[:8]}"
    run_before = read_run_meta(session_folder)
    start_execute_loop = approval_starts_execute_loop(run_before)

    def _approve(current: dict[str, Any]) -> dict[str, Any]:
        current_pw = get_plan_workflow(current)
        if enable_workflow or not current_pw.get("enabled"):
            current_pw["enabled"] = True
        current_pw["phase"] = "APPROVED"
        current_pw["plan_hash_at_approval"] = plan_hash
        current_pw["approved_at"] = now
        current_pw["approved_by"] = approved_by
        current_pw.pop("notice", None)
        current_pw.pop("last_plan_gate", None)
        current["plan_workflow"] = current_pw

        if start_execute_loop:
            current_loop = dict(current.get("verified_loop") or {})
            current_loop["loop_goal"] = approved
            current_loop["status"] = "running"
            current_loop["iteration"] = 0
            current_loop["verification_attempts"] = 0
            current_loop["oracle_session_id"] = oracle_session_id
            current_loop.pop("circuit_breaker", None)
            current["verified_loop"] = current_loop

            current["session_goal"] = {
                "text": goal_text,
                "set_at": now,
                "updated_at": now,
                "set_by": "agents+human",
            }
            current["goal_loop"] = {
                "enabled": True,
                "status": "open",
                "max_checks": 5,
                "checks": [],
            }
        return current

    updated = patch_run_meta(session_folder, _approve)

    if start_execute_loop:
        from agent_lab.mission.loop import after_plan_scribe, enable_mission_loop

        enable_mission_loop(session_folder)
        after_plan_scribe(session_folder, md)

        from agent_lab.runtime.events import RuntimeEvent
        from agent_lab.runtime.runtime import dispatch

        dispatch(
            session_folder,
            RuntimeEvent.MISSION_ENABLE,
            {"start_autonomous": True},
        )
        updated = read_run_meta(session_folder)

    pw_out = get_plan_workflow(updated)
    loop_out = dict(updated.get("verified_loop") or {})
    return {
        "fast_path": enable_workflow,
        "plan_workflow": pw_out,
        "verified_loop": loop_out,
        "session_goal": updated.get("session_goal"),
        "goal_loop": updated.get("goal_loop"),
        "execute_loop_started": start_execute_loop,
    }


def reject_plan(
    session_folder: Path,
    *,
    note: str = "",
    target_phase: PlanWorkflowPhase = "CLARIFY",
) -> dict[str, Any]:
    allowed = {"CLARIFY", "REFINE", "DRAFT"}
    phase = target_phase if target_phase in allowed else "CLARIFY"

    def _reject(run: dict[str, Any]) -> dict[str, Any]:
        pw = get_plan_workflow(run)
        pw["phase"] = phase
        pw.pop("notice", None)
        pw.pop("last_plan_gate", None)
        if note.strip():
            pw["last_reject_note"] = note.strip()[:500]
        run["plan_workflow"] = pw
        loop = dict(run.get("verified_loop") or {})
        loop["status"] = "proposing"
        run["verified_loop"] = loop
        return run

    patch_run_meta(session_folder, _reject)
    return get_plan_workflow(read_run_meta(session_folder))


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


def plan_workflow_public(run: dict[str, Any] | None) -> dict[str, Any]:
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


def _open_plan_objections(run: dict[str, Any]) -> list[dict[str, Any]]:
    from agent_lab.room.objections import list_objections

    return [o for o in list_objections(run) if o.get("status") == "open" and o.get("act") in {"CHALLENGE", "BLOCK"}]


def _clarity_gate_questions(folder: Path, run: dict[str, Any]) -> dict[str, Any] | None:
    """Engine+pipeline CLARIFY gate: surface clarity-engine questions via the Human Inbox.

    Returns a hold-result dict when CLARIFY must hold on unmet clarity, or ``None`` when clarity
    is already met or no human-visible question could be created (no silent deadlock). Anchored
    tasks (regex short-circuit) pass immediately without an LLM call.
    """
    from agent_lab.clarity import _mission_clarity_text, clarity_threshold_met

    if clarity_threshold_met(run):
        return None

    from agent_lab.clarifier_engine import engine_questions

    text = _mission_clarity_text(run)
    _result, questions = engine_questions(text)
    if not questions:
        # Clarity unmet but no targeted question to ask → do not silently hold; advance.
        return {"phase": "CLARIFY", "clarity_pending": False, "clarity_notice": "clarity_no_questions"}

    from agent_lab.inbox.harvest import harvest_clarifier_questions
    from agent_lab.session.clarifier import persist_clarifier_interview

    interview = {
        "version": 2,
        "plan_mode": True,
        "status": "pending",
        "source": "clarity_engine",
        "human_turn": 0,
        "questions": questions[:5],
        "answers": {},
        "created_at": _now(),
    }
    # Persist through the identity-aware arbiter and harvest from the ACTUAL persisted
    # interview (which may be a preserved pre-existing pending one), so the Human Inbox can
    # never diverge from run.json's clarifier_interview.
    persisted = persist_clarifier_interview(folder, interview)
    actual: dict[str, Any] = persisted.get("interview") or interview
    prompts = [
        str(q.get("prompt") or "").strip()
        for q in (actual.get("questions") or [])
        if str(q.get("prompt") or "").strip()
    ]
    if not prompts:
        return {"phase": "CLARIFY", "clarity_pending": False, "clarity_notice": "clarity_no_questions"}

    def _harvest(run_in: dict[str, Any]) -> dict[str, Any]:
        harvest_clarifier_questions(run_in, prompts)
        cur = get_plan_workflow(run_in)
        cur["phase"] = "CLARIFY"
        cur["notice"] = "clarity_pending"
        run_in["plan_workflow"] = cur
        _mirror_verified_loop_status(run_in, cur)
        return run_in

    patch_run_meta(folder, _harvest)

    from agent_lab.human_inbox import has_pending_question

    if not has_pending_question(read_run_meta(folder)):
        from agent_lab.inbox.harvest import orchestrator_inbox_harvest_enabled

        if orchestrator_inbox_harvest_enabled():
            # Harvest was enabled but questions were all deduped → advance to avoid deadlock.
            return {"phase": "CLARIFY", "clarity_pending": False, "clarity_notice": "clarity_no_visible_question"}
        # MCP-first: harvest off, questions live in clarifier_interview. Agents surface them
        # via ask_human or room context; round cap (max_clarify_rounds) guards against infinite wait.
        return {
            "phase": "CLARIFY",
            "clarity_pending": True,
            "clarity_notice": "clarity_mcp_first_hold",
            "questions": prompts,
            "wait_inbox": False,
        }
    return {
        "phase": "CLARIFY",
        "clarity_pending": True,
        "clarity_notice": "clarity_pending",
        "questions": prompts,
        "wait_inbox": True,
    }


def tick_plan_workflow_after_turn(
    folder: Path,
    *,
    synthesize: bool,
    cancelled: bool,
    plan_md: str,
    plan_before: str,
    has_pending_inbox_question: bool,
) -> dict[str, Any]:
    """Advance FSM after a room turn; returns hints for follow-up automation."""
    run = read_run_meta(folder)
    if not is_plan_workflow_active(run) or cancelled:
        return {"handled": False}

    pw = get_plan_workflow(run)
    phase = str(pw.get("phase") or "CLARIFY")
    out: dict[str, Any] = {"handled": True, "phase": phase}

    if not synthesize:
        out["discuss_only"] = True
        return out

    if phase in _PLAN_CLARIFY_PHASES:
        if has_pending_inbox_question:
            set_plan_workflow_phase(folder, "CLARIFY")
            out["phase"] = "CLARIFY"
            out["wait_inbox"] = True
            return out
        clarify_round = int(pw.get("clarify_round") or 0) + 1
        max_clarify = _round_cap(pw.get("max_clarify_rounds"), DEFAULT_MAX_CLARIFY_ROUNDS)
        # Round cap takes precedence: exhausted cap → advance unconditionally (no clarity gate).
        if clarify_round <= max_clarify:
            clarity_hold = _clarity_gate_questions(folder, run)
            if clarity_hold is not None and clarity_hold.get("clarity_pending"):
                out.update(clarity_hold)
                return out
            if clarity_hold is not None:
                out.update(clarity_hold)

        def _clarify_done(run_in: dict[str, Any]) -> dict[str, Any]:
            cur = get_plan_workflow(run_in)
            cur["clarify_round"] = clarify_round
            cur["phase"] = "DRAFT"
            run_in["plan_workflow"] = cur
            _mirror_verified_loop_status(run_in, cur)
            return run_in

        patch_run_meta(folder, _clarify_done)
        if clarify_round > max_clarify:

            def _clarify_cap(run_in: dict[str, Any]) -> dict[str, Any]:
                cur = get_plan_workflow(run_in)
                cur["notice"] = "clarify_cap_reached"
                run_in["plan_workflow"] = cur
                return run_in

            patch_run_meta(folder, _clarify_cap)
            out["clarify_cap_reached"] = True
        out["advance"] = "DRAFT"
        out["phase"] = "DRAFT"
        return out

    if phase == "DRAFT":
        if plan_md and plan_md != plan_before:
            set_plan_workflow_phase(folder, "PEER_REVIEW")
            out["phase"] = "PEER_REVIEW"
            out["advance"] = "PEER_REVIEW"
        return out

    if phase == "PEER_REVIEW":
        objections = _open_plan_objections(read_run_meta(folder))
        peer_round = int(pw.get("peer_review_round") or 0)
        max_peer = effective_max_peer_review_rounds(pw)
        last_verdict = str(pw.get("last_peer_verdict") or "")
        iterate_requested = last_verdict in {"iterate", "reject"}
        if (objections or iterate_requested) and peer_round < max_peer:
            set_plan_workflow_phase(folder, "REFINE")
            out["phase"] = "REFINE"
            out["advance"] = "REFINE"
            out["peer_iterate"] = last_verdict or "objections"
            return out
        evaluation = _evaluate_plan_for_human_pending(folder, plan_md)
        if evaluation.get("status") == "reject" and peer_round < max_peer:

            def _refine_gate(run_in: dict[str, Any]) -> dict[str, Any]:
                cur = get_plan_workflow(run_in)
                cur["phase"] = "REFINE"
                cur["last_plan_gate"] = evaluation
                run_in["plan_workflow"] = cur
                _mirror_verified_loop_status(run_in, cur)
                return run_in

            patch_run_meta(folder, _refine_gate)
            out["plan_gate"] = evaluation
            out["phase"] = "REFINE"
            return out

        pending_notices: list[str] = []
        if objections and peer_round >= max_peer:
            pending_notices.append("peer_review_cap_reached")
        if evaluation.get("status") == "reject":
            pending_notices.append("plan_gate_cap_reached")

        def _human_pending(run_in: dict[str, Any]) -> dict[str, Any]:
            cur = get_plan_workflow(run_in)
            cur["phase"] = "HUMAN_PENDING"
            if pending_notices:
                cur["notice"] = pending_notices[-1]
            if evaluation.get("status") == "reject":
                cur["last_plan_gate"] = evaluation
            run_in["plan_workflow"] = cur
            proposed = derive_loop_goal_from_plan(plan_md)
            loop = dict(run_in.get("verified_loop") or {})
            loop["proposed"] = {
                **proposed,
                "proposed_at": _now(),
                "source": "plan_workflow",
            }
            loop["status"] = "pending_approval"
            run_in["verified_loop"] = loop
            return run_in

        patch_run_meta(folder, _human_pending)
        out["phase"] = "HUMAN_PENDING"
        out["pending_approval"] = True
        return out

    if phase == "REFINE":
        if plan_md and plan_md != plan_before:

            def _inc_peer(run_in: dict[str, Any]) -> dict[str, Any]:
                cur = get_plan_workflow(run_in)
                cur["peer_review_round"] = int(cur.get("peer_review_round") or 0) + 1
                cur["phase"] = "PEER_REVIEW"
                cur.pop("last_plan_gate", None)
                cur.pop("last_peer_verdict", None)
                run_in["plan_workflow"] = cur
                _mirror_verified_loop_status(run_in, cur)
                return run_in

            patch_run_meta(folder, _inc_peer)
            out["phase"] = "PEER_REVIEW"
        return out

    return out


def tick_plan_workflow_after_inbox_resolve(folder: Path) -> dict[str, Any]:
    """Advance CLARIFY→DRAFT when Human resolves inbox without a new chat turn."""
    run = read_run_meta(folder)
    if not is_plan_workflow_active(run):
        return {"handled": False}
    phase = plan_workflow_phase(run).upper()
    if phase not in _PLAN_CLARIFY_PHASES:
        return {"handled": False, "phase": phase}
    from agent_lab.human_inbox import has_pending_question

    run = read_run_meta(folder)
    plan_path = folder / "plan.md"
    plan_md = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
    return tick_plan_workflow_after_turn(
        folder,
        synthesize=True,
        cancelled=False,
        plan_md=plan_md,
        plan_before=plan_md,
        has_pending_inbox_question=has_pending_question(run),
    )


def _evaluate_plan_for_human_pending(folder: Path, plan_md: str) -> dict[str, Any]:
    from agent_lab.mission.loop import evaluate_plan_gate

    run = read_run_meta(folder)
    return evaluate_plan_gate(plan_md, run=run, session_folder=folder)


def orchestrate_plan_workflow_pipeline(
    folder: Path,
    *,
    topic: str,
    messages: list[Any],
    plan_md: str,
    plan_before: str,
    synthesize: bool,
    cancelled: bool,
    agents: list[str] | None,
    permissions: dict[str, Any] | None,
    run_meta: dict[str, Any] | None,
    on_event: Any | None = None,
) -> tuple[str, list[Any], dict[str, Any]]:
    """Run post-scribe plan pipeline: peer review, refine scribe, human pending."""
    from agent_lab.human_inbox import has_pending_question

    if cancelled or not is_plan_workflow_active(run_meta):
        return plan_md, [], {"handled": False}

    extra_messages: list[Any] = []
    plan_md_current = plan_md
    tick = tick_plan_workflow_after_turn(
        folder,
        synthesize=synthesize,
        cancelled=cancelled,
        plan_md=plan_md_current,
        plan_before=plan_before,
        has_pending_inbox_question=has_pending_question(read_run_meta(folder)),
    )

    for _ in range(5):
        phase = plan_workflow_phase(read_run_meta(folder))
        if phase in ("HUMAN_PENDING", "APPROVED"):
            break
        if phase == "PEER_REVIEW":
            peer_replies = run_plan_peer_review_round(
                folder,
                topic=topic,
                messages=messages + extra_messages,
                agents=agents,
                permissions=permissions,
                run_meta=run_meta,
                plan_md=plan_md_current,
                on_event=on_event,
            )
            extra_messages.extend(peer_replies)
            tick = tick_plan_workflow_after_turn(
                folder,
                synthesize=synthesize,
                cancelled=False,
                plan_md=plan_md_current,
                plan_before=plan_before,
                has_pending_inbox_question=False,
            )
            continue
        if phase == "REFINE":
            from agent_lab.room import synthesize_plan

            prior = plan_md_current
            refined = synthesize_plan(topic, messages + extra_messages, run_meta=run_meta)
            if refined.strip():
                plan_md_current = refined
                (folder / "plan.md").write_text(refined, encoding="utf-8")
            tick = tick_plan_workflow_after_turn(
                folder,
                synthesize=synthesize,
                cancelled=False,
                plan_md=plan_md_current,
                plan_before=prior,
                has_pending_inbox_question=False,
            )
            continue
        break

    return plan_md_current, extra_messages, tick


def run_plan_peer_review_round(
    folder: Path,
    *,
    topic: str,
    messages: list[Any],
    agents: list[str] | None,
    permissions: dict[str, Any] | None,
    run_meta: dict[str, Any] | None,
    plan_md: str,
    on_event: Any | None = None,
) -> list[Any]:
    """Read-only peer review of plan.md by non-scribe agents."""
    from agent_lab.agents.registry import AGENT_IDS, available_agents
    from agent_lab.plan.peer_seats import (
        plan_cold_critic_enabled,
        plan_peer_review_seats,
        plan_peer_review_uses_role_lanes,
        plan_scribe_agent,
    )
    from agent_lab.room import run_parallel_round

    active = [a for a in (agents or available_agents()) if a in AGENT_IDS]
    active_ids = [str(a) for a in active]
    scribe_raw = plan_scribe_agent(run_meta=run_meta, active=active_ids)
    reviewers = plan_peer_review_seats(active_ids, run_meta=run_meta)
    if not reviewers:
        return []

    if run_meta is not None:
        run_meta["_plan_peer_review"] = True
        run_meta["_plan_scribe_agent"] = scribe_raw

    replies: list[Any] = []
    if plan_peer_review_uses_role_lanes(run_meta=run_meta) and len(reviewers) >= 2:
        architect, critic = reviewers[0], reviewers[1]
        replies.extend(
            run_parallel_round(
                topic,
                messages,
                agents=[architect],  # type: ignore[arg-type]
                parallel_round=1,
                on_event=on_event,
                permissions=permissions,
                plan_md=plan_md,
                run_meta=run_meta,
                extra_follow_up=PLAN_ARCHITECT_REVIEW_GUIDANCE,
                task_type="peer_review",
            )
        )
        replies.extend(
            run_parallel_round(
                topic,
                messages + replies,
                agents=[critic],  # type: ignore[arg-type]
                parallel_round=1,
                on_event=on_event,
                permissions=permissions,
                plan_md=plan_md,
                run_meta=run_meta,
                extra_follow_up=PLAN_CRITIC_REVIEW_GUIDANCE,
                task_type="peer_review",
            )
        )
    else:
        replies.extend(
            run_parallel_round(
                topic,
                messages,
                agents=reviewers,  # type: ignore[arg-type]
                parallel_round=1,
                on_event=on_event,
                permissions=permissions,
                plan_md=plan_md,
                run_meta=run_meta,
                extra_follow_up=PLAN_PEER_REVIEW_GUIDANCE,
                task_type="peer_review",
            )
        )

    if plan_cold_critic_enabled(run_meta=run_meta) and reviewers:
        cold_critic = reviewers[-1]
        replies.extend(
            run_parallel_round(
                topic,
                [],
                agents=[cold_critic],  # type: ignore[arg-type]
                parallel_round=1,
                on_event=on_event,
                permissions=permissions,
                plan_md=plan_md,
                run_meta=run_meta,
                extra_follow_up=PLAN_FRESH_EYES_GUIDANCE,
                task_type="cold_critic",
            )
        )

    from agent_lab.plan.peer_iterate import finalize_plan_peer_review_round

    human_turn = int((run_meta or {}).get("human_turn") or 0)
    finalize_plan_peer_review_round(
        folder,
        run_meta=run_meta,
        replies=replies,
        human_turn=human_turn,
    )

    return replies
