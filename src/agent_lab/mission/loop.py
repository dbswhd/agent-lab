"""Mission Loop FSM — C안 Discuss ↔ Execute orchestration (Layer 6)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from agent_lab.plan.actions import PlanAction, action_key, parse_plan_actions
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.mission.notepad import (
    ensure_mission_notepads,
    list_mission_notepad_summaries,
    append_wisdom_note,
)

from agent_lab.core.mission_loop import (
    AUTONOMOUS_ENDS,
    DEFAULT_MAX_MISSION_ITERATIONS,
    DEFAULT_MAX_MOMUS_ROUNDS,
    DEFAULT_MAX_REPAIR_PER_ACTION,  # noqa: F401 — public re-export
    default_mission_loop,  # noqa: F401 — public re-export
    get_mission_loop,
)
from agent_lab.mission.advance import (  # noqa: F401  public FSM handlers re-exported (defined in mission_advance)
    maybe_advance_mission,
    on_dry_run_complete,
    on_merge_confirm,
    on_merge_abort,
    on_verify_result,
    set_execution_phase,
)

MissionPhase = Literal[
    "MISSION_DEFINE",
    "MISSION_PAUSED",
    "CLARIFY",
    "DISCUSS",
    "PLAN_GATE",
    "PLAN_REJECT",
    "EXECUTE_QUEUE",
    "DRY_RUN",
    "MERGE_REVIEW",
    "VERIFY",
    "REPAIR",
    "MISSION_DONE",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mission_dispatch(
    folder: Path,
    event: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Route a mission/control transition through AgentLabRuntime (P6)."""
    from agent_lab.runtime.runtime import dispatch

    out = dispatch(folder, event, payload)
    if isinstance(out.result, dict):
        return out.result
    if not out.handled or out.skipped:
        return {
            "skipped": True,
            "reason": out.reason or ("unhandled" if not out.handled else "skipped"),
        }
    return get_mission_loop(read_run_meta(folder))


def mission_loop_env_enabled() -> bool:
    return os.getenv("AGENT_LAB_MISSION_LOOP", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def pipeline_enabled() -> bool:
    """Staged CLARIFY→CONSENSUS→EXECUTE orchestration (always on).

    ``AGENT_LAB_PIPELINE=0`` is deprecated and ignored; kept for call-site compatibility.
    """
    return True


def pipeline_explicitly_disabled() -> bool:
    """Deprecated — pipeline orchestration is always enabled."""
    return False


def _verified_loop_goal(run: dict[str, Any]) -> dict[str, Any] | None:
    loop = run.get("verified_loop")
    if not isinstance(loop, dict):
        return None
    goal = loop.get("loop_goal")
    return goal if isinstance(goal, dict) else None


def mission_define_ready(run: dict[str, Any]) -> bool:
    """Phase 0: mission can leave MISSION_DEFINE."""
    if mission_loop_env_enabled():
        goal = _verified_loop_goal(run)
        if goal and str(goal.get("text") or "").strip():
            return True
        gl = run.get("goal_loop")
        if isinstance(gl, dict) and gl.get("enabled") and str(gl.get("status") or "") == "open":
            return True
    verified = run.get("verified_loop")
    if isinstance(verified, dict) and verified.get("status") == "running":
        goal = _verified_loop_goal(run)
        return bool(goal and str(goal.get("text") or "").strip())
    return False


def sync_mission_phase_from_run(run: dict[str, Any]) -> dict[str, Any]:
    """Derive phase when mission enabled but phase stale."""
    ml = get_mission_loop(run)
    if not ml.get("enabled"):
        return ml
    if ml.get("circuit_breaker"):
        ml["phase"] = "MISSION_PAUSED"
        return ml
    phase = str(ml.get("phase") or "MISSION_DEFINE")
    if phase == "MISSION_DEFINE" and mission_define_ready(run):
        from agent_lab.mode_router import resolve_mission_bootstrap_phase

        ml["phase"] = resolve_mission_bootstrap_phase(run)
    if isinstance(run.get("verified_loop"), dict) and run["verified_loop"].get("circuit_breaker"):
        ml["circuit_breaker"] = True
        ml["circuit_breaker_reason"] = ml.get("circuit_breaker_reason") or "verified_loop"
        ml["phase"] = "MISSION_PAUSED"
    return ml


def evaluate_plan_gate(
    plan_md: str,
    *,
    run: dict[str, Any] | None = None,
    session_folder: Path | None = None,
) -> dict[str, Any]:
    """Momus-lite: mechanical plan gate before execute enqueue."""
    from agent_lab.context.layers import plan_gate_mcp_warnings

    actions = [a for a in parse_plan_actions(plan_md or "") if a.executable]
    failures: list[dict[str, Any]] = []
    for action in actions:
        issues = _action_gate_issues(action)
        if issues:
            failures.append(
                {
                    "action_index": action.index,
                    "action_key": action_key(action.kind, action.index),
                    "issues": issues,
                }
            )

    trading_failures: list[str] = []
    if run and session_folder is not None:
        from agent_lab.trading_mission.plan_gate import trading_plan_gate_issues
        from agent_lab.trading_mission.trading_goal_oracle import is_trading_mission_run

        if is_trading_mission_run(run):
            trading_failures = trading_plan_gate_issues(plan_md, session_folder)

    def _with_mcp_warnings(result: dict[str, Any]) -> dict[str, Any]:
        warnings = plan_gate_mcp_warnings(run, actions)
        if warnings:
            result = dict(result)
            result["mcp_warnings"] = warnings
        return result

    if trading_failures:
        return _with_mcp_warnings(
            {
                "status": "reject",
                "reason": "trading_checklist_failed",
                "failures": [
                    {
                        "action_index": None,
                        "action_key": "trading_consensus",
                        "issues": trading_failures,
                    }
                ],
            }
        )

    if not actions:
        return _with_mcp_warnings(
            {
                "status": "reject",
                "reason": "no_executable_actions",
                "failures": [{"action_index": None, "issues": ["no_executable_actions"]}],
            }
        )
    if failures:
        return _with_mcp_warnings(
            {
                "status": "reject",
                "reason": "action_gate_failed",
                "failures": failures,
            }
        )
    return _with_mcp_warnings(
        {
            "status": "ok",
            "reason": None,
            "failures": [],
            "action_count": len(actions),
        }
    )


def _action_gate_issues(action: PlanAction) -> list[str]:
    issues: list[str] = []
    if not action.what.strip():
        issues.append("empty_what")
    where = action.where.strip()
    if not where:
        issues.append("empty_where")
    elif not action.expected_paths() and len(where) < 8:
        issues.append("vague_where")
    verify = action.verify.strip()
    if not verify:
        issues.append("empty_verify")
    elif len(verify) < 8:
        issues.append("verify_too_short")
    return issues


def _action_indices_from_plan(plan_md: str) -> list[int]:
    return [a.index for a in parse_plan_actions(plan_md or "") if a.executable]


def open_block_reason(run: dict[str, Any]) -> str | None:
    from agent_lab.runtime.policy import PolicyEngine

    return PolicyEngine.execute_block_reason(run)


def trigger_circuit_breaker(
    folder: Path,
    *,
    reason: str,
    inbox_prompt: str | None = None,
) -> dict[str, Any]:
    from agent_lab.human_inbox import append_inbox_item, new_inbox_item

    prompt = inbox_prompt or (f"Mission loop circuit breaker: {reason}. Resolve to resume (DISCUSS or EXECUTE_QUEUE).")

    def _trip(run: dict[str, Any]) -> dict[str, Any]:
        ml = get_mission_loop(run)
        ml["circuit_breaker"] = True
        ml["circuit_breaker_reason"] = reason
        ml["phase"] = "MISSION_PAUSED"
        if ml.get("autonomous_segment", {}).get("active"):
            ml["autonomous_segment"]["active"] = False
        run["mission_loop"] = ml
        item = new_inbox_item(
            kind="question",
            source="mission_circuit_break",
            prompt=prompt,
            summary=f"mission circuit_breaker: {reason}",
            options=[
                {"id": "discuss", "label": "Discuss 재진입"},
                {"id": "execute", "label": "Execute 큐 재개"},
                {"id": "abort", "label": "미션 중단"},
            ],
        )
        return append_inbox_item(run, item)

    patch_run_meta(folder, _trip)
    run = read_run_meta(folder)
    ml_out = get_mission_loop(run)
    from agent_lab.runtime.boulder import record_last_failure, sync_boulder

    record_last_failure(
        folder,
        lane="mission",
        event="mission.circuit_breaker",
        reason=reason,
        phase=str(ml_out.get("phase") or ""),
        action_index=ml_out.get("current_action_index"),
        execution_id=str(ml_out.get("last_execution_id") or "").strip() or None,
        recoverable=True,
        resume_phase="DISCUSS",
    )
    sync_boulder(
        folder,
        resume_phase="DISCUSS",
        phase_before=str(ml_out.get("phase") or "") or None,
        action_index=ml_out.get("current_action_index"),
        execution_id=str(ml_out.get("last_execution_id") or "").strip() or None,
        source="circuit_breaker",
        reason=reason,
    )
    return ml_out


def clear_circuit_breaker(folder: Path, *, resume_phase: str = "DISCUSS") -> dict[str, Any]:
    allowed = {"DISCUSS", "EXECUTE_QUEUE", "PLAN_GATE"}
    phase = resume_phase if resume_phase in allowed else "DISCUSS"

    def _clear(run: dict[str, Any]) -> dict[str, Any]:
        ml = get_mission_loop(run)
        ml["circuit_breaker"] = False
        ml["circuit_breaker_reason"] = None
        ml["phase"] = phase
        run["mission_loop"] = ml
        return run

    patch_run_meta(folder, _clear)
    from agent_lab.runtime.boulder import clear_last_failure

    clear_last_failure(folder)
    append_wisdom_note(
        folder,
        line=f"circuit breaker cleared — resume {phase}",
        filename="decisions.md",
    )
    return get_mission_loop(read_run_meta(folder))


def enable_mission_loop(
    folder: Path,
    *,
    start_autonomous: bool = False,
) -> dict[str, Any]:
    """Phase 0: enable after verified_loop approve or explicit API."""

    def _enable(run: dict[str, Any]) -> dict[str, Any]:
        ml = get_mission_loop(run)
        ml["enabled"] = True
        ml["iteration"] = int(ml.get("iteration") or 0)
        if ml.get("phase") == "MISSION_DEFINE" and mission_define_ready(run):
            from agent_lab.mode_router import resolve_mission_bootstrap_phase

            ml["phase"] = resolve_mission_bootstrap_phase(run)
        if start_autonomous:
            ml["autonomous_segment"] = {
                "active": True,
                "started_at": _now_iso(),
                "ends_on": list(AUTONOMOUS_ENDS),
            }
        run["mission_loop"] = ml
        return run

    patch_run_meta(folder, _enable)

    from agent_lab.mission.board import sync_mission_board

    plan_path = folder / "plan.md"
    plan_md = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else None

    def _board(run: dict[str, Any]) -> dict[str, Any]:
        sync_mission_board(run, plan_md=plan_md)
        from agent_lab.mission.board import default_turn_budget, refresh_turn_budget

        if "turn_budget" not in run:
            run["turn_budget"] = refresh_turn_budget({**run, "turn_budget": default_turn_budget()})
        return run

    patch_run_meta(folder, _board)
    ensure_mission_notepads(folder)
    append_wisdom_note(
        folder,
        line="mission loop enabled",
        filename="decisions.md",
        auto_provenance=False,
    )

    if start_autonomous:
        # C2 drift audit baseline (docs/N10-USER-LOOP-WISDOM-DRAFT.md §4-C2) —
        # freeze the plan action list this autonomous segment starts from.
        from agent_lab.drift_audit import snapshot_drift_baseline
        from agent_lab.room.messages import _human_turn_count
        from agent_lab.room.session_persist import load_session_messages

        try:
            human_turn = _human_turn_count(load_session_messages(folder))
        except Exception:
            human_turn = 0
        snapshot_drift_baseline(folder, plan_md or "", human_turn)

    return get_mission_loop(read_run_meta(folder))


def run_plan_gate(folder: Path, plan_md: str) -> dict[str, Any]:
    """Phase 2: evaluate plan, update momus_round, enqueue or reject."""
    run = read_run_meta(folder)
    ml = get_mission_loop(run)
    if not ml.get("enabled"):
        return {"skipped": True, "reason": "mission_loop_disabled"}
    if ml.get("circuit_breaker"):
        return {"skipped": True, "reason": "circuit_breaker"}

    evaluation = evaluate_plan_gate(plan_md, run=run, session_folder=folder)
    gate = dict(ml.get("plan_gate") or {})

    if evaluation["status"] == "ok":
        block = open_block_reason(run)
        if block:
            return {
                "status": "blocked",
                "reason": block,
                "plan_gate": gate,
                "http_status": 409,
            }

        def _pass(run_in: dict[str, Any]) -> dict[str, Any]:
            m = get_mission_loop(run_in)
            g = dict(m.get("plan_gate") or {})
            g["status"] = "ok"
            g["last_reject_reason"] = None
            g["failures"] = []
            indices = _action_indices_from_plan(plan_md)
            m["plan_gate"] = g
            m["phase"] = "EXECUTE_QUEUE"
            m["pending_action_indices"] = indices
            m["current_action_index"] = indices[0] if indices else None
            run_in["mission_loop"] = m
            return run_in

        patch_run_meta(folder, _pass)
        ml_out = get_mission_loop(read_run_meta(folder))
        indices = list(ml_out.get("pending_action_indices") or [])
        append_wisdom_note(
            folder,
            line=f"plan gate PASS — enqueued {len(indices)} action(s)",
            filename="decisions.md",
        )
        result: dict[str, Any] = {
            "status": "ok",
            "phase": ml_out.get("phase"),
            "pending_action_indices": ml_out.get("pending_action_indices"),
            "plan_gate": ml_out.get("plan_gate"),
        }
        advance = _mission_dispatch(folder, "mission.advance")
        if advance and not advance.get("skipped"):
            result["advance"] = advance
            ml_out = get_mission_loop(read_run_meta(folder))
            result["phase"] = ml_out.get("phase")
        return result

    momus_round = int(gate.get("momus_round") or 0) + 1
    max_rounds = int(gate.get("max_momus_rounds") or DEFAULT_MAX_MOMUS_ROUNDS)
    gate.update(
        {
            "status": "reject",
            "momus_round": momus_round,
            "last_reject_reason": evaluation.get("reason"),
            "failures": evaluation.get("failures") or [],
        }
    )

    def _reject(run_in: dict[str, Any]) -> dict[str, Any]:
        m = get_mission_loop(run_in)
        m["plan_gate"] = gate
        m["phase"] = "PLAN_REJECT"
        m["iteration"] = int(m.get("iteration") or 0) + 1
        run_in["mission_loop"] = m
        return run_in

    patch_run_meta(folder, _reject)
    ml = get_mission_loop(read_run_meta(folder))

    if momus_round >= max_rounds:
        _mission_dispatch(
            folder,
            "mission.circuit_breaker",
            {
                "reason": "momus_round_cap",
                "inbox_prompt": (
                    f"Plan gate failed {momus_round} times (max {max_rounds}). Last reason: {evaluation.get('reason')}"
                ),
            },
        )
        ml = get_mission_loop(read_run_meta(folder))
        return {
            "status": "reject",
            "circuit_breaker": True,
            "plan_gate": ml.get("plan_gate"),
            "phase": ml.get("phase"),
        }

    def _to_discuss(run_in: dict[str, Any]) -> dict[str, Any]:
        m = get_mission_loop(run_in)
        m["phase"] = "DISCUSS"
        run_in["mission_loop"] = m
        return run_in

    patch_run_meta(folder, _to_discuss)
    ml = get_mission_loop(read_run_meta(folder))
    append_wisdom_note(
        folder,
        line=f"plan gate reject (round {momus_round}): {evaluation.get('reason')}",
        filename="learnings.md",
    )
    return {
        "status": "reject",
        "phase": ml.get("phase"),
        "plan_gate": ml.get("plan_gate"),
        "auto_discuss": True,
    }


def after_plan_scribe(folder: Path, plan_md: str) -> dict[str, Any] | None:
    """Conductor hook after plan.md update (scribe / sync)."""
    run = read_run_meta(folder)
    ml = get_mission_loop(run)
    if not ml.get("enabled") or ml.get("circuit_breaker"):
        return None
    phase = str(ml.get("phase") or "")
    if phase not in {"DISCUSS", "PLAN_GATE", "PLAN_REJECT", "MISSION_DEFINE"}:
        return None

    def _plan_gate_phase(run_in: dict[str, Any]) -> dict[str, Any]:
        m = get_mission_loop(run_in)
        m["phase"] = "PLAN_GATE"
        run_in["mission_loop"] = m
        return run_in

    patch_run_meta(folder, _plan_gate_phase)
    return _mission_dispatch(
        folder,
        "mission.plan_gate",
        {"plan_md": plan_md},
    )


_PAUSE_CLEANUP_PHASES = frozenset({"DRY_RUN", "MERGE_REVIEW", "EXECUTE_QUEUE", "REPAIR", "VERIFY"})

_ROLLBACK_RESUME_PHASES: dict[str, str] = {
    "DRY_RUN": "EXECUTE_QUEUE",
    "MERGE_REVIEW": "EXECUTE_QUEUE",
    "REPAIR": "EXECUTE_QUEUE",
    "VERIFY": "EXECUTE_QUEUE",
    "EXECUTE_QUEUE": "EXECUTE_QUEUE",
}


_STRUCTURAL_VERIFY_MARKERS = (
    "merge conflict",
    "merge_conflict",
    "worktree",
    "fail closed",
    "fail_closed",
    "structural",
)


def is_structural_verify_fail(reason: str = "") -> bool:
    """Classify verify/repair failures that need Human circuit breaker."""
    low = (reason or "").strip().lower()
    return any(marker in low for marker in _STRUCTURAL_VERIFY_MARKERS)


def mission_autorun_enabled(ml: dict[str, Any] | None = None) -> bool:
    if os.getenv("AGENT_LAB_MISSION_AUTORUN", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True
    seg = (ml or {}).get("autonomous_segment") or {}
    return bool(seg.get("active"))


def _scheduled_autorun_allowed(
    run: dict[str, Any],
    ml: dict[str, Any],
    *,
    scheduled: bool,
) -> bool:
    if mission_autorun_enabled(ml):
        return True
    if not scheduled:
        return False
    if run.get("schedule_sandbox"):
        return False
    from agent_lab.gate_scope import get_gate_profile

    return get_gate_profile(run) == "assistant"


def _discuss_recovery_prompt(
    folder: Path,
    *,
    action_index: int | None,
    reason: str,
) -> str:
    run = read_run_meta(folder)
    goal = _verified_loop_goal(run) or {}
    goal_text = str(goal.get("text") or "").strip() or "(mission goal)"
    last = (get_mission_loop(run).get("last_verify") or {}) if run else {}
    return (
        "[Mission Loop · verify recovery]\n"
        f"Plan action #{action_index} failed independent verification after repair cap.\n"
        f"Last verify: {last.get('status') or 'fail'} — {reason or last.get('reason') or ''}\n"
        f"Mission goal: {goal_text}\n\n"
        "R1 specialist round (Codex + Claude): root-cause analysis and a revised "
        "executable plan action (무엇을/어디서/검증). Keep the same action intent; "
        "tighten verify criteria. Do not skip the action."
    )


def run_mission_discuss_recovery(
    folder: Path,
    *,
    permissions: dict[str, Any] | None = None,
    on_event: Any = None,
) -> dict[str, Any]:
    """Phase 4: R1 specialist round + partial scribe + plan gate."""
    from agent_lab.run.control import is_cancelled

    if is_cancelled():
        return {"skipped": True, "reason": "run_cancelled"}
    run = read_run_meta(folder)
    ml = get_mission_loop(run)
    if not ml.get("enabled"):
        return {"skipped": True, "reason": "mission_loop_disabled"}
    if ml.get("circuit_breaker"):
        return {"skipped": True, "reason": "circuit_breaker"}
    raw_rec = ml.get("discuss_recovery")
    rec: dict[str, Any] = raw_rec if isinstance(raw_rec, dict) else {}
    if not rec.get("pending"):
        return {"skipped": True, "reason": "no_pending_recovery"}

    max_iter = int(ml.get("max_mission_iterations") or DEFAULT_MAX_MISSION_ITERATIONS)
    if int(ml.get("iteration") or 0) >= max_iter:
        _mission_dispatch(
            folder,
            "mission.circuit_breaker",
            {
                "reason": "mission_iteration_cap",
                "inbox_prompt": (f"Mission iteration cap ({max_iter}) reached during discuss recovery."),
            },
        )
        return {"skipped": True, "reason": "mission_iteration_cap", "circuit_breaker": True}

    action_index = rec.get("action_index")
    reason = str(rec.get("reason") or "")
    chat_path = folder / "chat.jsonl"
    if not chat_path.is_file():
        chat_path.write_text("", encoding="utf-8")
    if not (folder / "topic.txt").is_file():
        (folder / "topic.txt").write_text("mission recovery", encoding="utf-8")

    prompt = _discuss_recovery_prompt(
        folder,
        action_index=int(action_index) if action_index is not None else None,
        reason=reason,
    )

    def _mark_started(run_in: dict[str, Any]) -> dict[str, Any]:
        m = get_mission_loop(run_in)
        dr = dict(m.get("discuss_recovery") or {})
        dr["started_at"] = _now_iso()
        m["discuss_recovery"] = dr
        run_in["mission_loop"] = m
        return run_in

    patch_run_meta(folder, _mark_started)

    from agent_lab.agents.registry import available_agents
    from agent_lab.runtime.invoke_discuss import continue_room_round
    from agent_lab.run.control import run_guard

    ready = set(available_agents())
    agents = [a for a in ("codex", "claude") if a in ready]
    if not agents:
        agents = [a for a in ready if a in {"cursor", "codex", "claude"}][:2]
    if not agents:
        return {"skipped": True, "reason": "no_agents"}

    with run_guard(
        session_id=folder.name,
        run_kind="mission",
        label="Discuss recovery",
    ) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "run_in_progress"}
        try:
            messages, plan_md = continue_room_round(
                folder,
                prompt,
                agents=agents,  # type: ignore[arg-type]
                synthesize=True,
                parallel_rounds=2,
                permissions=permissions,
                turn_profile="specialist",
                research_mode=True,
                on_event=on_event,
            )
        except Exception as exc:
            messages, plan_md = [], ""
            append_wisdom_note(folder, line=f"discuss recovery round failed: {exc}")

    fallback_plan = folder / "plan.md"
    if not (plan_md or "").strip() and fallback_plan.is_file():
        plan_md = fallback_plan.read_text(encoding="utf-8")

    def _complete(run_in: dict[str, Any]) -> dict[str, Any]:
        m = get_mission_loop(run_in)
        dr = dict(m.get("discuss_recovery") or {})
        dr["pending"] = False
        dr["completed_at"] = _now_iso()
        m["discuss_recovery"] = dr
        run_in["mission_loop"] = m
        return run_in

    patch_run_meta(folder, _complete)
    gate_result = None
    if (plan_md or "").strip():
        gate_result = after_plan_scribe(folder, plan_md)
    out = get_mission_loop(read_run_meta(folder))
    return {
        "status": "discuss_recovery_complete",
        "message_count": len(messages),
        "plan_gate": gate_result,
        "phase": out.get("phase"),
    }


def on_structural_execution_failure(
    folder: Path,
    *,
    reason: str,
    action_index: int | None = None,
) -> dict[str, Any] | None:
    """Immediate DISCUSS on merge conflict / worktree fail-closed."""
    run = read_run_meta(folder)
    if not get_mission_loop(run).get("enabled"):
        return None
    append_wisdom_note(folder, line=f"structural execution failure: {reason}")

    def _discuss(run_in: dict[str, Any]) -> dict[str, Any]:
        m = get_mission_loop(run_in)
        m["phase"] = "DISCUSS"
        if action_index is not None:
            m["current_action_index"] = action_index
        m["discuss_recovery"] = {
            "pending": True,
            "reason": reason,
            "action_index": action_index,
            "started_at": None,
            "completed_at": None,
        }
        m["iteration"] = int(m.get("iteration") or 0) + 1
        run_in["mission_loop"] = m
        return run_in

    patch_run_meta(folder, _discuss)
    _mission_dispatch(
        folder,
        "mission.circuit_breaker",
        {
            "reason": "structural_execution_failure",
            "inbox_prompt": f"Structural execution failure: {reason}",
        },
    )
    return get_mission_loop(read_run_meta(folder))


def _rollback_resume_phase(phase: str) -> str:
    return _ROLLBACK_RESUME_PHASES.get(phase, "EXECUTE_QUEUE")


def pause_mission_loop(
    folder: Path,
    *,
    reason: str = "user_cancel",
    cleanup_executions: bool = True,
) -> dict[str, Any]:
    """Track D: pause mission on cancel — cleanup open executions + record last_partial."""
    run = read_run_meta(folder)
    ml = get_mission_loop(run)
    if not ml.get("enabled"):
        return {"skipped": True, "reason": "mission_loop_disabled"}
    phase_before = str(ml.get("phase") or "")
    if phase_before in {"MISSION_DONE", "MISSION_DEFINE"}:
        return {"skipped": True, "reason": "nothing_to_pause", "phase": phase_before}
    if phase_before == "MISSION_PAUSED":
        return {"skipped": True, "reason": "already_paused"}

    action_index = ml.get("current_action_index")
    exec_id = str(ml.get("last_execution_id") or "").strip() or None
    cleanup_result: dict[str, Any] | None = None

    if cleanup_executions and phase_before in _PAUSE_CLEANUP_PHASES:
        from agent_lab.runtime.invoke_execute import cancel_open_execution

        cleanup_result = cancel_open_execution(
            folder,
            execution_id=exec_id,
            reason=reason,
        )

    resume_phase = _rollback_resume_phase(phase_before)

    def _pause(run_in: dict[str, Any]) -> dict[str, Any]:
        m = get_mission_loop(run_in)
        m["last_partial"] = {
            "phase": phase_before,
            "resume_phase": resume_phase,
            "action_index": action_index,
            "execution_id": exec_id,
            "at": _now_iso(),
            "reason": reason,
            "cleanup": cleanup_result,
        }
        m["phase"] = "MISSION_PAUSED"
        m["pause_reason"] = reason
        seg = dict(m.get("autonomous_segment") or {})
        if seg.get("active"):
            seg["active"] = False
            m["autonomous_segment"] = seg
        run_in["mission_loop"] = m
        return run_in

    patch_run_meta(folder, _pause)
    from agent_lab.runtime.boulder import record_last_failure, sync_boulder_from_partial

    sync_boulder_from_partial(folder, source="pause")
    record_last_failure(
        folder,
        lane="mission",
        event="mission.pause",
        reason=reason,
        phase=phase_before,
        action_index=action_index,
        execution_id=exec_id,
        recoverable=True,
        resume_phase=resume_phase,
    )
    append_wisdom_note(
        folder,
        line=f"mission paused ({reason}) from {phase_before} → resume {resume_phase}",
        filename="decisions.md",
        auto_provenance=False,
    )
    out = get_mission_loop(read_run_meta(folder))
    return {
        "status": "paused",
        "phase": out.get("phase"),
        "resume_phase": resume_phase,
        "last_partial": out.get("last_partial"),
        "cleanup": cleanup_result,
    }


def resume_mission_loop(
    folder: Path,
    *,
    resume_phase: str | None = None,
) -> dict[str, Any]:
    """Resume from MISSION_PAUSED using last_partial or explicit phase."""
    run = read_run_meta(folder)
    ml = get_mission_loop(run)
    if not ml.get("enabled"):
        return {"skipped": True, "reason": "mission_loop_disabled"}
    if str(ml.get("phase") or "") != "MISSION_PAUSED":
        return {"skipped": True, "reason": "not_paused", "phase": ml.get("phase")}

    raw_partial = ml.get("last_partial")
    partial: dict[str, Any] = raw_partial if isinstance(raw_partial, dict) else {}
    phase = resume_phase or partial.get("resume_phase") or "EXECUTE_QUEUE"
    allowed = {
        "DISCUSS",
        "EXECUTE_QUEUE",
        "PLAN_GATE",
        "REPAIR",
    }
    if phase not in allowed:
        phase = "EXECUTE_QUEUE"

    def _resume(run_in: dict[str, Any]) -> dict[str, Any]:
        m = get_mission_loop(run_in)
        m["phase"] = phase
        m["pause_reason"] = None
        run_in["mission_loop"] = m
        return run_in

    patch_run_meta(folder, _resume)
    from agent_lab.runtime.boulder import clear_boulder, clear_last_failure

    clear_boulder(folder)
    clear_last_failure(folder)
    append_wisdom_note(
        folder,
        line=f"mission resumed → {phase}",
        filename="decisions.md",
        auto_provenance=False,
    )
    out = get_mission_loop(read_run_meta(folder))
    return {
        "status": "resumed",
        "phase": out.get("phase"),
        "last_partial": partial,
    }


def on_global_run_cancel(folder: Path) -> dict[str, Any]:
    """Hook from POST /api/room/runs/cancel when session_id is known."""
    return _mission_dispatch(
        folder,
        "run.cancel",
        {"reason": "global_cancel"},
    )


def public_mission_payload(folder: Path) -> dict[str, Any]:
    run = read_run_meta(folder)
    ml = sync_mission_phase_from_run(run)
    goal = _verified_loop_goal(run)
    return {
        "ok": True,
        "enabled": bool(ml.get("enabled")),
        "mission_loop": ml,
        "has_loop_goal": bool(goal and str(goal.get("text") or "").strip()),
        "verified_loop_status": (run.get("verified_loop") or {}).get("status"),
        "notepads": list_mission_notepad_summaries(folder),
    }
