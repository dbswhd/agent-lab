from __future__ import annotations

"""Plan workflow FSM tick and post-scribe orchestration."""

from pathlib import Path
from typing import Any

from agent_lab.run.state import RunStateLike

from agent_lab.plan.workflow_clarify import clarity_gate_questions, open_plan_objections
from agent_lab.plan.workflow_state import (
    DEFAULT_MAX_CLARIFY_ROUNDS,
    PLAN_CLARIFY_PHASES,
    _round_cap,
    apply_plan_substate_patch,
    derive_loop_goal_from_plan,
    effective_max_peer_review_rounds,
    get_plan_workflow,
    is_plan_workflow_active,
    plan_fsm_skill_first_enabled,
    plan_workflow_phase,
    set_plan_workflow_phase,
)
from agent_lab.time_utils import utc_now_iso as _now
from agent_lab.run.meta import patch_run_meta, read_run_meta


def tick_plan_workflow_after_turn(
    folder: Path,
    *,
    synthesize: bool,
    cancelled: bool,
    plan_md: str,
    plan_before: str,
    has_pending_inbox_question: bool,
    turn_policy_advance: bool = False,
) -> dict[str, Any]:
    """Advance FSM after a room turn via runtime ``plan.workflow.tick``."""
    from agent_lab.runtime.events import RuntimeEvent
    from agent_lab.runtime.runtime import dispatch

    out = dispatch(
        folder,
        RuntimeEvent.PLAN_WORKFLOW_TICK,
        {
            "synthesize": synthesize,
            "cancelled": cancelled,
            "plan_md": plan_md,
            "plan_before": plan_before,
            "has_pending_inbox_question": has_pending_inbox_question,
            "turn_policy_advance": turn_policy_advance,
        },
    )
    if out.skipped:
        return {"handled": False, "reason": out.reason or "plan_workflow_tick_skipped"}
    if isinstance(out.result, dict):
        return out.result
    return {"handled": out.handled}


def _execute_plan_workflow_tick(
    folder: Path,
    *,
    synthesize: bool,
    cancelled: bool,
    plan_md: str,
    plan_before: str,
    has_pending_inbox_question: bool,
    turn_policy_advance: bool = False,
) -> dict[str, Any]:
    """Internal plan FSM tick body (invoked by plan_lane handler)."""
    run = read_run_meta(folder)
    if not is_plan_workflow_active(run) or cancelled:
        return {"handled": False}

    pw = get_plan_workflow(run)
    phase = str(pw.get("phase") or "CLARIFY")
    out: dict[str, Any] = {"handled": True, "phase": phase}

    if not synthesize and not turn_policy_advance:
        out["discuss_only"] = True
        return out

    if phase in PLAN_CLARIFY_PHASES:
        if has_pending_inbox_question:
            set_plan_workflow_phase(folder, "CLARIFY")
            out["phase"] = "CLARIFY"
            out["wait_inbox"] = True
            return out
        clarify_round = int(pw.get("clarify_round") or 0) + 1
        max_clarify = _round_cap(pw.get("max_clarify_rounds"), DEFAULT_MAX_CLARIFY_ROUNDS)

        if plan_fsm_skill_first_enabled():
            if clarify_round > max_clarify:

                def _clarify_done_cap(run_in: dict[str, Any]) -> dict[str, Any]:
                    return apply_plan_substate_patch(
                        run_in,
                        phase="DRAFT",
                        clarify_round=clarify_round,
                        notice="clarify_cap_reached",
                    )

                patch_run_meta(folder, _clarify_done_cap)
                out["clarify_cap_reached"] = True
                out["advance"] = "DRAFT"
                out["phase"] = "DRAFT"
                out["skill_first_cap_fallback"] = True
                return out

            from agent_lab.clarity import clarity_threshold_met

            if clarity_threshold_met(read_run_meta(folder)):

                def _clarify_done_met(run_in: dict[str, Any]) -> dict[str, Any]:
                    return apply_plan_substate_patch(
                        run_in,
                        phase="DRAFT",
                        clarify_round=clarify_round,
                        notice="skill_first_clarity_met",
                    )

                patch_run_meta(folder, _clarify_done_met)
                out["advance"] = "DRAFT"
                out["phase"] = "DRAFT"
                out["skill_first_clarity_met"] = True
                return out

            def _skill_first_hold(run_in: dict[str, Any]) -> dict[str, Any]:
                return apply_plan_substate_patch(
                    run_in,
                    phase="CLARIFY",
                    clarify_round=clarify_round,
                    notice="skill_first_hold",
                )

            patch_run_meta(folder, _skill_first_hold)
            out["phase"] = "CLARIFY"
            out["skill_first_hold"] = True
            return out

        # Round cap takes precedence: exhausted cap → advance unconditionally (no clarity gate).
        if clarify_round <= max_clarify:
            clarity_hold = clarity_gate_questions(folder, run)
            if clarity_hold is not None and clarity_hold.get("clarity_pending"):
                out.update(clarity_hold)
                return out
            if clarity_hold is not None:
                out.update(clarity_hold)

        def _clarify_done(run_in: dict[str, Any]) -> dict[str, Any]:
            return apply_plan_substate_patch(
                run_in,
                phase="DRAFT",
                clarify_round=clarify_round,
            )

        patch_run_meta(folder, _clarify_done)
        if clarify_round > max_clarify:

            def _clarify_cap(run_in: dict[str, Any]) -> dict[str, Any]:
                return apply_plan_substate_patch(run_in, notice="clarify_cap_reached")

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
        objections = open_plan_objections(read_run_meta(folder))
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
                return apply_plan_substate_patch(
                    run_in,
                    phase="REFINE",
                    last_plan_gate=evaluation,
                )

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
            patch_kwargs: dict[str, Any] = {}
            if pending_notices:
                patch_kwargs["notice"] = pending_notices[-1]
            if evaluation.get("status") == "reject":
                patch_kwargs["last_plan_gate"] = evaluation
            run_in = apply_plan_substate_patch(
                run_in,
                phase="HUMAN_PENDING",
                stamp_orchestration=False,
                **patch_kwargs,
            )
            proposed = derive_loop_goal_from_plan(plan_md)
            loop = dict(run_in.get("verified_loop") or {})
            loop["proposed"] = {
                **proposed,
                "proposed_at": _now(),
                "source": "plan_workflow",
            }
            loop["status"] = "pending_approval"
            run_in["verified_loop"] = loop
            from agent_lab.runtime.orchestration import stamp_orchestration_state

            return stamp_orchestration_state(run_in)

        patch_run_meta(folder, _human_pending)
        out["phase"] = "HUMAN_PENDING"
        out["pending_approval"] = True
        return out

    if phase == "REFINE":
        if plan_md and plan_md != plan_before:

            def _inc_peer(run_in: dict[str, Any]) -> dict[str, Any]:
                cur = get_plan_workflow(run_in)
                return apply_plan_substate_patch(
                    run_in,
                    phase="PEER_REVIEW",
                    peer_review_round=int(cur.get("peer_review_round") or 0) + 1,
                    pop_fields=("last_plan_gate", "last_peer_verdict"),
                )

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
    if phase not in PLAN_CLARIFY_PHASES:
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
    run_meta: RunStateLike | None,
    on_event: Any | None = None,
) -> tuple[str, list[Any], dict[str, Any]]:
    """Run post-scribe plan pipeline: peer review, refine scribe, human pending."""
    from agent_lab.human_inbox import has_pending_question
    from agent_lab.room.turn_policy import turn_policy_enabled

    if cancelled or not is_plan_workflow_active(run_meta):
        return plan_md, [], {"handled": False}

    extra_messages: list[Any] = []
    plan_md_current = plan_md
    turn_policy_advance = turn_policy_enabled()
    tick = tick_plan_workflow_after_turn(
        folder,
        synthesize=synthesize,
        cancelled=cancelled,
        plan_md=plan_md_current,
        plan_before=plan_before,
        has_pending_inbox_question=has_pending_question(read_run_meta(folder)),
        turn_policy_advance=turn_policy_advance,
    )

    for _ in range(5):
        phase = plan_workflow_phase(read_run_meta(folder))
        if phase in ("HUMAN_PENDING", "APPROVED"):
            break
        if phase == "PEER_REVIEW":
            import agent_lab.plan.workflow as plan_workflow

            peer_replies = plan_workflow.run_plan_peer_review_round(
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
                turn_policy_advance=turn_policy_advance,
            )
            continue
        if phase == "REFINE":
            from agent_lab.room import synthesize_plan

            prior = plan_md_current
            refined = synthesize_plan(topic, messages + extra_messages, run_meta=run_meta)
            if refined.strip():
                plan_md_current = refined
                from agent_lab.plan.paths import write_session_plan_md

                run_snapshot = read_run_meta(folder)
                write_session_plan_md(folder, refined, run_snapshot)
                from agent_lab.run.meta import patch_run_meta

                def _persist_active(run_in: dict[str, Any]) -> dict[str, Any]:
                    if run_snapshot.get("active_plan_relpath"):
                        run_in["active_plan_relpath"] = run_snapshot["active_plan_relpath"]
                    return run_in

                patch_run_meta(folder, _persist_active)
            tick = tick_plan_workflow_after_turn(
                folder,
                synthesize=synthesize,
                cancelled=False,
                plan_md=plan_md_current,
                plan_before=prior,
                has_pending_inbox_question=False,
                turn_policy_advance=turn_policy_advance,
            )
            continue
        break

    return plan_md_current, extra_messages, tick
