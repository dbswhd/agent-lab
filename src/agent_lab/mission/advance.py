"""Mission FSM phase-advance, verify, and merge-transition handlers (Layer 6 Phase 3/4)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent_lab.run.meta import patch_run_meta, read_run_meta

if TYPE_CHECKING:
    from agent_lab.mission.loop import MissionPhase


from agent_lab.plan.execution_status_scopes import find_open_merge_pending_execution


def _find_open_execution(
    run: dict[str, Any],
    *,
    action_index: int,
) -> dict[str, Any] | None:
    for row in reversed(run.get("executions") or []):
        if not isinstance(row, dict):
            continue
        if row.get("action_index") != action_index:
            continue
        status = str(row.get("status") or "")
        if status in _OPEN_EXECUTION_STATUSES:
            return row
    return None


def on_dry_run_complete(folder: Path, execution: dict[str, Any]) -> dict[str, Any] | None:
    """Phase 3: dry-run finished — Human merge gate."""
    from agent_lab.mission.loop import get_mission_loop
    from agent_lab.mission.notepad import append_wisdom_note

    run = read_run_meta(folder)
    ml = get_mission_loop(run)
    if not ml.get("enabled"):
        return None
    exec_id = str(execution.get("id") or "")
    action_index = execution.get("action_index")

    def _merge_review(run_in: dict[str, Any]) -> dict[str, Any]:
        m = get_mission_loop(run_in)
        m["phase"] = "MERGE_REVIEW"
        m["last_execution_id"] = exec_id or None
        if action_index is not None:
            m["current_action_index"] = action_index
        seg = dict(m.get("autonomous_segment") or {})
        if seg.get("active"):
            seg["active"] = False
            m["autonomous_segment"] = seg
        run_in["mission_loop"] = m
        return run_in

    patch_run_meta(folder, _merge_review)
    from agent_lab.mission.board import sync_mission_board

    plan_path = folder / "plan.md"
    plan_md = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else None

    def _board(run_in: dict[str, Any]) -> dict[str, Any]:
        sync_mission_board(run_in, plan_md=plan_md)
        return run_in

    patch_run_meta(folder, _board)
    append_wisdom_note(
        folder,
        line=f"dry-run complete action #{action_index} → MERGE_REVIEW ({exec_id})",
    )
    return get_mission_loop(read_run_meta(folder))


def on_merge_confirm(folder: Path, *, execution_id: str) -> dict[str, Any] | None:
    """Merge approved — enter VERIFY (oracle runs in plan_execute)."""
    from agent_lab.mission.loop import get_mission_loop

    run = read_run_meta(folder)
    if not get_mission_loop(run).get("enabled"):
        return None

    def _verify(run_in: dict[str, Any]) -> dict[str, Any]:
        m = get_mission_loop(run_in)
        m["phase"] = "VERIFY"
        m["last_execution_id"] = execution_id
        run_in["mission_loop"] = m
        return run_in

    patch_run_meta(folder, _verify)
    from agent_lab.mission.board import clear_checkout

    clear_checkout(folder)
    return get_mission_loop(read_run_meta(folder))


def on_merge_abort(folder: Path, *, execution_id: str) -> dict[str, Any] | None:
    """Human rejected merge — discuss revise path."""
    from agent_lab.mission.loop import get_mission_loop
    from agent_lab.mission.notepad import append_wisdom_note

    run = read_run_meta(folder)
    if not get_mission_loop(run).get("enabled"):
        return None

    def _discuss(run_in: dict[str, Any]) -> dict[str, Any]:
        m = get_mission_loop(run_in)
        m["phase"] = "DISCUSS"
        m["last_execution_id"] = execution_id
        run_in["mission_loop"] = m
        return run_in

    patch_run_meta(folder, _discuss)
    from agent_lab.mission.board import clear_checkout

    clear_checkout(folder)
    append_wisdom_note(folder, line=f"merge rejected {execution_id} → DISCUSS")
    return get_mission_loop(read_run_meta(folder))


def maybe_advance_mission(
    folder: Path,
    *,
    permissions: dict[str, Any] | None = None,
    executor: str | None = None,
    scheduled: bool = False,
    on_event: Any = None,
) -> dict[str, Any]:
    """Conductor tick: autorun dry-run, merge, verify, or repair when phase allows."""
    from agent_lab.mission.loop import (
        _mission_dispatch,
        _scheduled_autorun_allowed,
        get_mission_loop,
        trigger_circuit_breaker,
    )
    from agent_lab.mission.board import record_autorun_tick, sync_turn_budget_from_mission

    record_autorun_tick(folder)
    sync_turn_budget_from_mission(folder)
    run = read_run_meta(folder)
    ml = get_mission_loop(run)
    if not ml.get("enabled"):
        return {"skipped": True, "reason": "mission_loop_disabled"}
    if ml.get("circuit_breaker"):
        return {"skipped": True, "reason": "circuit_breaker"}
    from agent_lab.cost_ledger import budget_status

    budget = budget_status(run)
    if budget["over"]:
        trigger_circuit_breaker(
            folder,
            reason="budget_exceeded",
            inbox_prompt=(
                f"Mission budget exceeded: spent ${budget['spent_usd']:.4f} of "
                f"${budget['limit_usd']:.4f} cap. Resolve to resume (raise "
                "AGENT_LAB_MISSION_BUDGET_USD then Discuss/Execute)."
            ),
        )
        return {"skipped": True, "reason": "budget_exceeded", "budget": budget}
    if not _scheduled_autorun_allowed(run, ml, scheduled=scheduled):
        return {"skipped": True, "reason": "autorun_off"}

    from agent_lab.mode_router import apply_mission_mode_route

    mode_result = apply_mission_mode_route(folder)
    if mode_result is not None:
        return mode_result

    phase = str(get_mission_loop(read_run_meta(folder)).get("phase") or "")
    if phase == "EXECUTE_QUEUE":
        return _advance_execute_queue(folder, permissions=permissions, executor=executor)
    if phase == "REPAIR":
        return _advance_repair(folder, permissions=permissions, executor=executor)
    if phase == "MERGE_REVIEW" and scheduled:
        return _advance_merge_review(folder)
    if phase == "VERIFY" and scheduled:
        return _advance_verify_stalled(folder)
    raw_rec = ml.get("discuss_recovery")
    rec: dict[str, Any] = raw_rec if isinstance(raw_rec, dict) else {}
    if rec.get("pending"):
        return _mission_dispatch(
            folder,
            "mission.discuss_recovery",
            {"permissions": permissions, "on_event": on_event},
        )
    return {"skipped": True, "reason": "wrong_phase", "phase": phase}


def _advance_merge_review(folder: Path) -> dict[str, Any]:
    from agent_lab.mission.loop import get_mission_loop, open_block_reason
    from agent_lab.mission.notepad import append_wisdom_note

    run = read_run_meta(folder)
    ml = get_mission_loop(run)
    if run.get("schedule_sandbox"):
        return {
            "skipped": True,
            "reason": "schedule_sandbox_read_only",
            "phase": str(ml.get("phase") or ""),
        }

    exec_id = str(ml.get("last_execution_id") or "").strip() or None
    pending = find_open_merge_pending_execution(run, execution_id=exec_id)
    if pending is None:
        return {"skipped": True, "reason": "no_pending_execution", "phase": "MERGE_REVIEW"}

    block = open_block_reason(run)
    if block:
        return {"skipped": True, "reason": "blocked", "detail": block, "phase": "MERGE_REVIEW"}

    from agent_lab.auto_merge import evaluate_auto_merge_eligibility, resolve_auto_merge

    pending_id = str(pending.get("id") or "")
    elig = evaluate_auto_merge_eligibility(folder, execution_id=pending_id)
    if not elig.get("eligible"):
        notify_result: dict[str, Any] | None = None
        try:
            from agent_lab.gateway.notify_helpers import notify_auto_merge_blocked

            notify_result = notify_auto_merge_blocked(
                folder,
                execution=pending,
                eligibility=elig,
                source="scheduled_tick",
            )
        except Exception:
            pass
        return {
            "skipped": True,
            "reason": "auto_merge_not_eligible",
            "detail": elig.get("reason"),
            "phase": "MERGE_REVIEW",
            "execution_id": pending_id,
            "notify": notify_result,
        }

    try:
        result = resolve_auto_merge(folder, execution_id=pending_id)
    except Exception as exc:
        append_wisdom_note(folder, line=f"scheduled auto-merge failed {pending_id}: {exc}")
        return {
            "status": "error",
            "error": str(exc),
            "execution_id": pending_id,
            "phase": "MERGE_REVIEW",
        }

    phase = str(get_mission_loop(read_run_meta(folder)).get("phase") or "")
    return {
        "status": "auto_merge_complete",
        "execution_id": pending_id,
        "phase": phase,
        "auto_merge": result.get("auto_merge"),
    }


def _advance_verify_stalled(folder: Path) -> dict[str, Any]:
    """Recover VERIFY when merge+oracle already recorded but phase did not advance."""
    from agent_lab.mission.loop import get_mission_loop

    run = read_run_meta(folder)
    ml = get_mission_loop(run)
    exec_id = str(ml.get("last_execution_id") or "").strip()
    target: dict[str, Any] | None = None
    for row in reversed(run.get("executions") or []):
        if isinstance(row, dict) and str(row.get("id") or "") == exec_id:
            target = row
            break
    if target is None:
        return {"skipped": True, "reason": "no_execution_for_verify", "phase": "VERIFY"}

    raw_oracle = target.get("oracle")
    oracle: dict[str, Any] = raw_oracle if isinstance(raw_oracle, dict) else {}
    verdict = str(oracle.get("verdict") or "").strip().lower()
    if str(target.get("status") or "") != "merged" or not verdict:
        return {"skipped": True, "reason": "verify_in_progress", "phase": "VERIFY"}

    action_index = int(target.get("action_index") or ml.get("current_action_index") or 0)
    reason = str(oracle.get("detail") or oracle.get("feedback") or oracle.get("reason") or "")
    return on_verify_result(
        folder,
        action_index=action_index,
        verdict=verdict,
        reason=reason,
        oracle=oracle,
    )


def _advance_execute_queue(
    folder: Path,
    *,
    permissions: dict[str, Any] | None,
    executor: str | None,
) -> dict[str, Any]:
    from agent_lab.mission.loop import get_mission_loop, open_block_reason
    from agent_lab.mission.notepad import append_wisdom_note

    run = read_run_meta(folder)
    ml = get_mission_loop(run)
    if run.get("schedule_sandbox"):
        return {
            "skipped": True,
            "reason": "schedule_sandbox_read_only",
            "phase": str(ml.get("phase") or ""),
        }

    idx = ml.get("current_action_index")
    pending = list(ml.get("pending_action_indices") or [])
    if idx is None and pending:
        idx = pending[0]

    if idx is None:
        return {"skipped": True, "reason": "no_current_action"}

    block = open_block_reason(run)
    if block:
        return {"skipped": True, "reason": "blocked", "detail": block}

    existing = _find_open_execution(run, action_index=int(idx))
    if existing:
        on_dry_run_complete(folder, existing)
        return {
            "status": "awaiting_merge",
            "execution_id": existing.get("id"),
            "phase": "MERGE_REVIEW",
        }

    from agent_lab.plan.pending import PlanSnapshotRequired
    from agent_lab.runtime.invoke_execute import run_dry_run

    try:
        execution = run_dry_run(
            folder,
            action_index=int(idx),
            permissions=permissions,
            executor=executor,
        )
    except PlanSnapshotRequired as exc:
        return {
            "status": "plan_snapshot_required",
            "action_index": idx,
            "pending_plan": exc.pending_plan,
        }
    except Exception as exc:
        append_wisdom_note(folder, line=f"dry-run failed action #{idx}: {exc}")
        return {"status": "error", "error": str(exc), "action_index": idx}

    on_dry_run_complete(folder, execution)
    return {
        "status": "dry_run_complete",
        "execution_id": execution.get("id"),
        "phase": "MERGE_REVIEW",
        "action_index": idx,
    }


def _advance_repair(
    folder: Path,
    *,
    permissions: dict[str, Any] | None,
    executor: str | None,
) -> dict[str, Any]:
    from agent_lab.mission.loop import get_mission_loop
    from agent_lab.mission.notepad import append_wisdom_note

    run = read_run_meta(folder)
    ml = get_mission_loop(run)
    exec_id = str(ml.get("last_execution_id") or "").strip()
    if not exec_id:
        for row in reversed(run.get("executions") or []):
            if isinstance(row, dict) and row.get("status") == "merged":
                raw_row_oracle = row.get("oracle")
                oracle: dict[str, Any] = raw_row_oracle if isinstance(raw_row_oracle, dict) else {}
                if oracle.get("verdict") == "fail":
                    exec_id = str(row.get("id") or "")
                    break
    if not exec_id:
        return {"skipped": True, "reason": "no_execution_for_repair"}

    from agent_lab.runtime.invoke_execute import reverify_merged_execution

    try:
        result = reverify_merged_execution(
            folder,
            execution_id=exec_id,
            permissions=permissions,
            executor=executor,
        )
    except Exception as exc:
        append_wisdom_note(folder, line=f"repair failed {exec_id}: {exc}")
        return {"status": "error", "error": str(exc), "execution_id": exec_id}

    raw_execution = result.get("execution")
    execution: dict[str, Any] = raw_execution if isinstance(raw_execution, dict) else {}
    raw_exec_oracle = execution.get("oracle")
    repair_oracle: dict[str, Any] = raw_exec_oracle if isinstance(raw_exec_oracle, dict) else {}
    phase = get_mission_loop(read_run_meta(folder)).get("phase")
    return {
        "status": "repair_complete",
        "execution_id": exec_id,
        "repair": result.get("repair"),
        "oracle_verdict": repair_oracle.get("verdict"),
        "phase": phase,
    }


def set_execution_phase(
    folder: Path,
    *,
    phase: MissionPhase,
    current_action_index: int | None = None,
) -> dict[str, Any]:
    from agent_lab.mission.loop import get_mission_loop

    def _set(run: dict[str, Any]) -> dict[str, Any]:
        m = get_mission_loop(run)
        if not m.get("enabled"):
            return run
        m["phase"] = phase
        if current_action_index is not None:
            m["current_action_index"] = current_action_index
        if phase == "MERGE_REVIEW" and m.get("autonomous_segment", {}).get("active"):
            seg = dict(m["autonomous_segment"])
            seg["active"] = False
            m["autonomous_segment"] = seg
        run["mission_loop"] = m
        return run

    patch_run_meta(folder, _set)
    return get_mission_loop(read_run_meta(folder))


def on_verify_result(
    folder: Path,
    *,
    action_index: int,
    verdict: str,
    reason: str = "",
    oracle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Phase 3/4: update mission state after merge verify."""
    from agent_lab.mission.loop import _now_iso, get_mission_loop

    run = read_run_meta(folder)
    ml = get_mission_loop(run)
    if not ml.get("enabled"):
        return {"skipped": True}

    verdict_norm = str(verdict or "").strip().lower()
    last_verify = {
        "status": verdict_norm,
        "reason": reason,
        "at": _now_iso(),
        "action_index": action_index,
    }

    def _save_verify(run_in: dict[str, Any]) -> dict[str, Any]:
        m = get_mission_loop(run_in)
        m["last_verify"] = last_verify
        run_in["mission_loop"] = m
        return run_in

    patch_run_meta(folder, _save_verify)
    ml = get_mission_loop(read_run_meta(folder))

    if verdict_norm == "pass":
        return _on_verify_pass(folder, action_index, ml, oracle=oracle)

    _advance_verify_with_policy(folder, {"oracle": oracle, "status": "failed", "blocked_message": reason}, action_index)
    ml = get_mission_loop(read_run_meta(folder))
    return _on_verify_fail(folder, action_index, ml, reason=reason, oracle=oracle)


def _on_verify_pass(
    folder: Path,
    action_index: int,
    ml: dict[str, Any],
    *,
    oracle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from agent_lab.mission.loop import _mission_dispatch, get_mission_loop
    from agent_lab.mission.notepad import append_wisdom_note

    pending = [i for i in (ml.get("pending_action_indices") or []) if i != action_index]
    repairs = dict(ml.get("action_repair_counts") or {})
    repairs.pop(str(action_index), None)

    def _advance(run: dict[str, Any]) -> dict[str, Any]:
        m = get_mission_loop(run)
        m["pending_action_indices"] = pending
        m["action_repair_counts"] = repairs
        m["phase"] = "MISSION_DONE" if not pending else "EXECUTE_QUEUE"
        m["current_action_index"] = pending[0] if pending else None
        run["mission_loop"] = m
        return run

    patch_run_meta(folder, _advance)
    out = get_mission_loop(read_run_meta(folder))
    from agent_lab.runtime.boulder import clear_boulder, clear_last_failure

    clear_last_failure(folder)
    if out.get("phase") == "MISSION_DONE":
        clear_boulder(folder)
        try:
            from agent_lab.autonomy_promotion import record_mission_completion
            from agent_lab.human_inbox import pending_inbox_items

            run_after = read_run_meta(folder)
            record_mission_completion(
                folder,
                completed=True,
                inbox_escalated=bool(pending_inbox_items(run_after)),
            )
        except Exception:
            pass
    verify_line = f"verify PASS action #{action_index}"
    if oracle and str(oracle.get("detail") or "").strip():
        verify_line += f" — {str(oracle.get('detail') or '')[:220]}"
    append_wisdom_note(
        folder,
        line=verify_line,
        filename="verification.md",
        action_index=action_index,
    )
    if isinstance(oracle, dict):
        for row in (oracle.get("evidence") or [])[:5]:
            if str(row or "").strip():
                append_wisdom_note(
                    folder,
                    line=f"evidence: {str(row).strip()[:240]}",
                    filename="verification.md",
                    action_index=action_index,
                )
    if pending:
        append_wisdom_note(
            folder,
            line=f"action #{action_index} complete — next #{pending[0]}",
            filename="learnings.md",
            action_index=action_index,
        )
    else:
        append_wisdom_note(
            folder,
            line="all actions verified — MISSION_DONE",
            filename="decisions.md",
        )
    result: dict[str, Any] = {
        "status": "pass",
        "phase": out.get("phase"),
        "pending": pending,
    }
    if out.get("phase") == "EXECUTE_QUEUE":
        advance = _mission_dispatch(folder, "mission.advance")
        if advance and not advance.get("skipped"):
            result["advance"] = advance
            out = get_mission_loop(read_run_meta(folder))
            result["phase"] = out.get("phase")
    return result


def _advance_verify_with_policy(folder: Path, execution: dict[str, Any], action_index: int) -> dict[str, Any]:
    from agent_lab.mission.loop import get_mission_loop

    try:
        from agent_lab.verify_repair_policy import (
            classify_failure,
            ensure_worktree_usable,
            policy_for,
            repair_counts_key,
            normalize_repair_counts,
        )
    except Exception:
        return {"skipped": True, "reason": "policy_unavailable"}
    failure = classify_failure(execution)
    policy = policy_for(failure)
    repair_label = policy.get("repair")
    if repair_label in {"reinvoke", "reverify", "merge_repair", "worktree_recreate"}:
        run = read_run_meta(folder)
        ml = get_mission_loop(run)
        counts = normalize_repair_counts(ml)
        key = repair_counts_key(action_index)
        counts[key] = int(counts.get(key, 0)) + 1

        def _patch(run_in: dict[str, Any]) -> dict[str, Any]:
            m = get_mission_loop(run_in)
            m["action_repair_counts"] = counts
            m["current_action_index"] = action_index
            run_in["mission_loop"] = m
            return run_in

        patch_run_meta(folder, _patch)
    outcome: dict[str, Any] = {"applied": True, "failure": failure, "policy": policy}
    if repair_label == "worktree_recreate":
        try:
            ok, result = ensure_worktree_usable(folder, execution=execution, exec_id=str(action_index), mode="recreate")
        except Exception as exc:
            ok, result = False, {"action": "recreate_exception", "error": str(exc)}
        outcome["worktree_recreate"] = {"ok": ok, "result": result}
    return outcome


def _on_verify_fail(
    folder: Path,
    action_index: int,
    ml: dict[str, Any],
    *,
    reason: str,
    oracle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from agent_lab.mission.loop import (
        DEFAULT_MAX_REPAIR_PER_ACTION,
        _mission_dispatch,
        get_mission_loop,
        is_structural_verify_fail,
        mission_autorun_enabled,
    )
    from agent_lab.mission.notepad import append_wisdom_note

    repairs = dict(ml.get("action_repair_counts") or {})
    key = str(action_index)
    count = int(repairs.get(key) or 0)
    repairs[key] = count
    max_rep = int(ml.get("max_repair_per_action") or DEFAULT_MAX_REPAIR_PER_ACTION)

    if count < max_rep:

        def _repair(run: dict[str, Any]) -> dict[str, Any]:
            m = get_mission_loop(run)
            m["action_repair_counts"] = repairs
            m["phase"] = "REPAIR"
            m["current_action_index"] = action_index
            run["mission_loop"] = m
            return run

        patch_run_meta(folder, _repair)
        out = get_mission_loop(read_run_meta(folder))
        from agent_lab.runtime.boulder import record_last_failure

        record_last_failure(
            folder,
            lane="execute",
            event="execute.verify.fail",
            reason=reason,
            phase="REPAIR",
            action_index=action_index,
            execution_id=str(out.get("last_execution_id") or "").strip() or None,
            recoverable=True,
            resume_phase="REPAIR",
        )
        append_wisdom_note(
            folder,
            line=(f"verify FAIL action #{action_index} → REPAIR ({count}/{max_rep}): {reason}"),
            filename="verification.md",
            action_index=action_index,
        )
        result: dict[str, Any] = {
            "status": "fail",
            "phase": "REPAIR",
            "repair_count": count,
            "action_index": action_index,
        }
        if mission_autorun_enabled(out):
            advance = _mission_dispatch(folder, "mission.advance")
            if advance and not advance.get("skipped"):
                result["advance"] = advance
                out = get_mission_loop(read_run_meta(folder))
                result["phase"] = out.get("phase")
        return result

    structural = is_structural_verify_fail(reason)
    append_wisdom_note(
        folder,
        line=(f"verify repair cap action #{action_index} ({'structural' if structural else 'recoverable'}): {reason}"),
        filename="verification.md",
    )

    def _discuss(run: dict[str, Any]) -> dict[str, Any]:
        m = get_mission_loop(run)
        m["action_repair_counts"] = repairs
        m["phase"] = "DISCUSS"
        m["current_action_index"] = action_index
        m["iteration"] = int(m.get("iteration") or 0) + 1
        m["discuss_recovery"] = {
            "pending": not structural,
            "reason": reason,
            "action_index": action_index,
            "started_at": None,
            "completed_at": None,
        }
        run["mission_loop"] = m
        return run

    patch_run_meta(folder, _discuss)
    out = get_mission_loop(read_run_meta(folder))
    from agent_lab.runtime.boulder import record_last_failure

    record_last_failure(
        folder,
        lane="execute",
        event="execute.verify.fail",
        reason=reason,
        phase="DISCUSS",
        action_index=action_index,
        execution_id=str(out.get("last_execution_id") or "").strip() or None,
        recoverable=not structural,
        resume_phase="DISCUSS",
    )

    if structural:
        _mission_dispatch(
            folder,
            "mission.circuit_breaker",
            {
                "reason": f"repair_cap_action_{action_index}",
                "inbox_prompt": (
                    f"Structural verify failure after {count} repair(s) for action {action_index}: {reason}"
                ),
            },
        )
        out = get_mission_loop(read_run_meta(folder))

    result = {
        "status": "fail",
        "phase": "DISCUSS",
        "repair_cap": True,
        "action_index": action_index,
        "structural": structural,
        "circuit_breaker": out.get("circuit_breaker"),
        "discuss_recovery_pending": (out.get("discuss_recovery") or {}).get("pending"),
    }
    try:
        from agent_lab.verify_repair_policy import classify_failure

        result["failure"] = classify_failure(
            {
                "oracle": oracle,
                "status": "failed",
                "blocked_message": reason,
            },
            evidence={"error": reason},
        )
    except Exception:
        pass
    if not structural and mission_autorun_enabled(out) and (out.get("discuss_recovery") or {}).get("pending"):
        recovery = _mission_dispatch(folder, "mission.discuss_recovery")
        if recovery and not recovery.get("skipped"):
            result["discuss_recovery"] = recovery
            out = get_mission_loop(read_run_meta(folder))
            result["phase"] = out.get("phase")
    return result
