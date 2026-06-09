"""Mission Loop FSM — C안 Discuss ↔ Execute orchestration (Layer 6)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from agent_lab.plan_actions import PlanAction, action_key, parse_plan_actions
from agent_lab.run_meta import patch_run_meta, read_run_meta

MissionPhase = Literal[
    "MISSION_DEFINE",
    "MISSION_PAUSED",
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

DEFAULT_MAX_MOMUS_ROUNDS = 3
DEFAULT_MAX_REPAIR_PER_ACTION = 2
DEFAULT_MAX_MISSION_ITERATIONS = 20
MISSION_WISDOM_INJECT_CAP = 1500

MISSION_NOTEPAD_FILES: tuple[str, ...] = (
    "learnings.md",
    "verification.md",
    "decisions.md",
)
_NOTEPAD_HEADERS: dict[str, str] = {
    "learnings.md": "# Mission learnings\n\n",
    "verification.md": "# Mission verification log\n\n",
    "decisions.md": "# Mission decisions\n\n",
}
_WISDOM_SKIP_PHASES = frozenset({"MISSION_DEFINE", "MISSION_DONE", "MISSION_PAUSED"})
_NOTEPAD_READ_ORDER = ("verification.md", "learnings.md", "decisions.md")

_AUTONOMOUS_ENDS = (
    "merge_review",
    "circuit_breaker",
    "mission_done",
    "inbox_escalate",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mission_loop_env_enabled() -> bool:
    return os.getenv("AGENT_LAB_MISSION_LOOP", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def default_mission_loop() -> dict[str, Any]:
    return {
        "enabled": False,
        "phase": "MISSION_DEFINE",
        "iteration": 0,
        "max_mission_iterations": DEFAULT_MAX_MISSION_ITERATIONS,
        "pending_action_indices": [],
        "current_action_index": None,
        "action_repair_counts": {},
        "max_repair_per_action": DEFAULT_MAX_REPAIR_PER_ACTION,
        "last_verify": None,
        "last_execution_id": None,
        "plan_gate": {
            "status": "pending",
            "momus_round": 0,
            "max_momus_rounds": DEFAULT_MAX_MOMUS_ROUNDS,
            "last_reject_reason": None,
            "failures": [],
        },
        "wisdom_refs": [],
        "discuss_recovery": {
            "pending": False,
            "reason": None,
            "action_index": None,
            "started_at": None,
            "completed_at": None,
        },
        "autonomous_segment": {
            "active": False,
            "started_at": None,
            "ends_on": list(_AUTONOMOUS_ENDS),
        },
        "circuit_breaker": False,
        "circuit_breaker_reason": None,
        "pause_reason": None,
        "last_partial": None,
    }


def get_mission_loop(run: dict[str, Any] | None) -> dict[str, Any]:
    raw = (run or {}).get("mission_loop")
    if not isinstance(raw, dict):
        return default_mission_loop()
    base = default_mission_loop()
    for key, val in raw.items():
        if key == "plan_gate" and isinstance(val, dict):
            gate = dict(base["plan_gate"])
            gate.update(val)
            base["plan_gate"] = gate
        elif key == "autonomous_segment" and isinstance(val, dict):
            seg = dict(base["autonomous_segment"])
            seg.update(val)
            base["autonomous_segment"] = seg
        elif key == "discuss_recovery" and isinstance(val, dict):
            rec = dict(base["discuss_recovery"])
            rec.update(val)
            base["discuss_recovery"] = rec
        else:
            base[key] = val
    return base


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
        ml["phase"] = "DISCUSS"
    if isinstance(run.get("verified_loop"), dict) and run["verified_loop"].get(
        "circuit_breaker"
    ):
        ml["circuit_breaker"] = True
        ml["circuit_breaker_reason"] = ml.get("circuit_breaker_reason") or "verified_loop"
        ml["phase"] = "MISSION_PAUSED"
    return ml


def evaluate_plan_gate(
    plan_md: str,
    *,
    run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Momus-lite: mechanical plan gate before execute enqueue."""
    from agent_lab.context_layers import plan_gate_mcp_warnings

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
    def _with_mcp_warnings(result: dict[str, Any]) -> dict[str, Any]:
        warnings = plan_gate_mcp_warnings(run, actions)
        if warnings:
            result = dict(result)
            result["mcp_warnings"] = warnings
        return result

    if not actions:
        return _with_mcp_warnings(
            {
                "status": "reject",
                "reason": "no_executable_actions",
                "failures": [
                    {"action_index": None, "issues": ["no_executable_actions"]}
                ],
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

    prompt = inbox_prompt or (
        f"Mission loop circuit breaker: {reason}. "
        "Resolve to resume (DISCUSS or EXECUTE_QUEUE)."
    )

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
            ml["phase"] = "DISCUSS"
        if start_autonomous:
            ml["autonomous_segment"] = {
                "active": True,
                "started_at": _now_iso(),
                "ends_on": list(_AUTONOMOUS_ENDS),
            }
        run["mission_loop"] = ml
        return run

    patch_run_meta(folder, _enable)
    ensure_mission_notepads(folder)
    append_wisdom_note(
        folder,
        line="mission loop enabled",
        filename="decisions.md",
        auto_provenance=False,
    )
    return get_mission_loop(read_run_meta(folder))


def run_plan_gate(folder: Path, plan_md: str) -> dict[str, Any]:
    """Phase 2: evaluate plan, update momus_round, enqueue or reject."""
    run = read_run_meta(folder)
    ml = get_mission_loop(run)
    if not ml.get("enabled"):
        return {"skipped": True, "reason": "mission_loop_disabled"}
    if ml.get("circuit_breaker"):
        return {"skipped": True, "reason": "circuit_breaker"}

    evaluation = evaluate_plan_gate(plan_md, run=run)
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
        advance = maybe_advance_mission(folder)
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
        trigger_circuit_breaker(
            folder,
            reason="momus_round_cap",
            inbox_prompt=(
                f"Plan gate failed {momus_round} times (max {max_rounds}). "
                f"Last reason: {evaluation.get('reason')}"
            ),
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
    return run_plan_gate(folder, plan_md)


_OPEN_EXECUTION_STATUSES = frozenset(
    {"pending_approval", "review_required", "merge_conflict", "pending"}
)

_PAUSE_CLEANUP_PHASES = frozenset(
    {"DRY_RUN", "MERGE_REVIEW", "EXECUTE_QUEUE", "REPAIR", "VERIFY"}
)

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
    append_wisdom_note(
        folder,
        line=f"dry-run complete action #{action_index} → MERGE_REVIEW ({exec_id})",
    )
    return get_mission_loop(read_run_meta(folder))


def on_merge_confirm(folder: Path, *, execution_id: str) -> dict[str, Any] | None:
    """Merge approved — enter VERIFY (oracle runs in plan_execute)."""
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
    return get_mission_loop(read_run_meta(folder))


def on_merge_abort(folder: Path, *, execution_id: str) -> dict[str, Any] | None:
    """Human rejected merge — discuss revise path."""
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
    append_wisdom_note(folder, line=f"merge rejected {execution_id} → DISCUSS")
    return get_mission_loop(read_run_meta(folder))


def maybe_advance_mission(
    folder: Path,
    *,
    permissions: dict[str, Any] | None = None,
    executor: str | None = None,
) -> dict[str, Any]:
    """Conductor tick: autorun dry-run or repair when phase allows."""
    run = read_run_meta(folder)
    ml = get_mission_loop(run)
    if not ml.get("enabled"):
        return {"skipped": True, "reason": "mission_loop_disabled"}
    if ml.get("circuit_breaker"):
        return {"skipped": True, "reason": "circuit_breaker"}
    if not mission_autorun_enabled(ml):
        return {"skipped": True, "reason": "autorun_off"}

    phase = str(ml.get("phase") or "")
    if phase == "EXECUTE_QUEUE":
        return _advance_execute_queue(folder, permissions=permissions, executor=executor)
    if phase == "REPAIR":
        return _advance_repair(folder, permissions=permissions, executor=executor)
    if phase == "DISCUSS":
        rec = ml.get("discuss_recovery") if isinstance(ml.get("discuss_recovery"), dict) else {}
        if rec.get("pending"):
            return run_mission_discuss_recovery(
                folder,
                permissions=permissions,
                on_event=None,
            )
    return {"skipped": True, "reason": "wrong_phase", "phase": phase}


def _advance_execute_queue(
    folder: Path,
    *,
    permissions: dict[str, Any] | None,
    executor: str | None,
) -> dict[str, Any]:
    run = read_run_meta(folder)
    ml = get_mission_loop(run)
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

    from agent_lab.plan_pending import PlanSnapshotRequired
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
    run = read_run_meta(folder)
    ml = get_mission_loop(run)
    exec_id = str(ml.get("last_execution_id") or "").strip()
    if not exec_id:
        for row in reversed(run.get("executions") or []):
            if isinstance(row, dict) and row.get("status") == "merged":
                oracle = row.get("oracle") if isinstance(row.get("oracle"), dict) else {}
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

    execution = result.get("execution") if isinstance(result.get("execution"), dict) else {}
    oracle = execution.get("oracle") if isinstance(execution.get("oracle"), dict) else {}
    phase = get_mission_loop(read_run_meta(folder)).get("phase")
    return {
        "status": "repair_complete",
        "execution_id": exec_id,
        "repair": result.get("repair"),
        "oracle_verdict": oracle.get("verdict"),
        "phase": phase,
    }


def set_execution_phase(
    folder: Path,
    *,
    phase: MissionPhase,
    current_action_index: int | None = None,
) -> dict[str, Any]:
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

    return _on_verify_fail(folder, action_index, ml, reason=reason, oracle=oracle)


def _on_verify_pass(
    folder: Path,
    action_index: int,
    ml: dict[str, Any],
    *,
    oracle: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        advance = maybe_advance_mission(folder)
        if advance and not advance.get("skipped"):
            result["advance"] = advance
            out = get_mission_loop(read_run_meta(folder))
            result["phase"] = out.get("phase")
    return result


def _on_verify_fail(
    folder: Path,
    action_index: int,
    ml: dict[str, Any],
    *,
    reason: str,
    oracle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repairs = dict(ml.get("action_repair_counts") or {})
    key = str(action_index)
    count = int(repairs.get(key) or 0) + 1
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
            line=(
                f"verify FAIL action #{action_index} → REPAIR "
                f"({count}/{max_rep}): {reason}"
            ),
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
            advance = maybe_advance_mission(folder)
            if advance and not advance.get("skipped"):
                result["advance"] = advance
                out = get_mission_loop(read_run_meta(folder))
                result["phase"] = out.get("phase")
        return result

    structural = is_structural_verify_fail(reason)
    append_wisdom_note(
        folder,
        line=(
            f"verify repair cap action #{action_index}"
            f" ({'structural' if structural else 'recoverable'}): {reason}"
        ),
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
        trigger_circuit_breaker(
            folder,
            reason=f"repair_cap_action_{action_index}",
            inbox_prompt=(
                f"Structural verify failure after {count} repair(s) "
                f"for action {action_index}: {reason}"
            ),
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
    if (
        not structural
        and mission_autorun_enabled(out)
        and (out.get("discuss_recovery") or {}).get("pending")
    ):
        recovery = run_mission_discuss_recovery(folder)
        if recovery and not recovery.get("skipped"):
            result["discuss_recovery"] = recovery
            out = get_mission_loop(read_run_meta(folder))
            result["phase"] = out.get("phase")
    return result


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
    run = read_run_meta(folder)
    ml = get_mission_loop(run)
    if not ml.get("enabled"):
        return {"skipped": True, "reason": "mission_loop_disabled"}
    if ml.get("circuit_breaker"):
        return {"skipped": True, "reason": "circuit_breaker"}
    rec = ml.get("discuss_recovery") if isinstance(ml.get("discuss_recovery"), dict) else {}
    if not rec.get("pending"):
        return {"skipped": True, "reason": "no_pending_recovery"}

    max_iter = int(ml.get("max_mission_iterations") or DEFAULT_MAX_MISSION_ITERATIONS)
    if int(ml.get("iteration") or 0) >= max_iter:
        trigger_circuit_breaker(
            folder,
            reason="mission_iteration_cap",
            inbox_prompt=f"Mission iteration cap ({max_iter}) reached during discuss recovery.",
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

    ready = set(available_agents())
    agents = [a for a in ("codex", "claude") if a in ready]
    if not agents:
        agents = [a for a in ready if a in {"cursor", "codex", "claude"}][:2]
    if not agents:
        return {"skipped": True, "reason": "no_agents"}

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
        append_wisdom_note(folder, line=f"discuss recovery failed: {exc}")
        return {"status": "error", "error": str(exc)}

    def _complete(run_in: dict[str, Any]) -> dict[str, Any]:
        m = get_mission_loop(run_in)
        dr = dict(m.get("discuss_recovery") or {})
        dr["pending"] = False
        dr["completed_at"] = _now_iso()
        m["discuss_recovery"] = dr
        run_in["mission_loop"] = m
        return run_in

    patch_run_meta(folder, _complete)
    gate_result = after_plan_scribe(folder, plan_md) if (plan_md or "").strip() else None
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
            "pending": False,
            "reason": reason,
            "action_index": action_index,
            "started_at": None,
            "completed_at": None,
        }
        m["iteration"] = int(m.get("iteration") or 0) + 1
        run_in["mission_loop"] = m
        return run_in

    patch_run_meta(folder, _discuss)
    trigger_circuit_breaker(
        folder,
        reason="structural_execution_failure",
        inbox_prompt=f"Structural execution failure: {reason}",
    )
    return get_mission_loop(read_run_meta(folder))


def mission_notepad_dir(folder: Path) -> Path:
    return Path.home() / ".agent-lab" / "missions" / folder.name


def mission_notepad_rel(session_id: str, filename: str) -> str:
    return f"missions/{session_id}/{filename}"


def ensure_mission_notepads(folder: Path) -> list[str]:
    """Create mission notepad files with headers (Phase 5)."""
    base = mission_notepad_dir(folder)
    base.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for name in MISSION_NOTEPAD_FILES:
        path = base / name
        if path.is_file():
            continue
        path.write_text(_NOTEPAD_HEADERS.get(name, f"# {name}\n\n"), encoding="utf-8")
        created.append(name)

    if not created:
        return created

    def _refs(run: dict[str, Any]) -> dict[str, Any]:
        m = get_mission_loop(run)
        refs = list(m.get("wisdom_refs") or [])
        for name in MISSION_NOTEPAD_FILES:
            rel = mission_notepad_rel(folder.name, name)
            if rel not in refs:
                refs.append(rel)
        m["wisdom_refs"] = refs
        run["mission_loop"] = m
        return run

    patch_run_meta(folder, _refs)
    return created


def _chat_provenance_ref(folder: Path) -> str | None:
    path = folder / "chat.jsonl"
    if not path.is_file():
        return None
    try:
        line_count = sum(1 for _ in path.open(encoding="utf-8"))
    except OSError:
        return None
    if line_count < 1:
        return None
    return f"chat.jsonl#L{line_count}"


def _plan_provenance_ref(folder: Path, action_index: int | None = None) -> str | None:
    plan_path = folder / "plan.md"
    if not plan_path.is_file():
        return None
    try:
        lines = plan_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if not lines:
        return None
    if action_index is not None:
        needle = f"{action_index}."
        for i, line in enumerate(lines, start=1):
            if line.strip().startswith(needle):
                return f"plan (ref: L{i})"
    return f"plan.md#L{len(lines)}"


def _format_provenance(
    folder: Path,
    *,
    action_index: int | None = None,
    extra: str | None = None,
) -> str | None:
    parts: list[str] = []
    if extra:
        parts.append(extra.strip())
    chat = _chat_provenance_ref(folder)
    if chat:
        parts.append(chat)
    plan = _plan_provenance_ref(folder, action_index)
    if plan:
        parts.append(plan)
    return " · ".join(parts) if parts else None


def _read_notepad_tail(path: Path, *, max_chars: int) -> str:
    if not path.is_file() or max_chars < 1:
        return ""
    try:
        body = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not body:
        return ""
    if len(body) <= max_chars:
        return body
    return "…\n" + body[-max_chars:]


def list_mission_notepad_summaries(folder: Path) -> list[dict[str, Any]]:
    """Summaries for API / UI (line counts + tail preview)."""
    base = mission_notepad_dir(folder)
    out: list[dict[str, Any]] = []
    for name in MISSION_NOTEPAD_FILES:
        path = base / name
        if not path.is_file():
            out.append({"file": name, "lines": 0, "preview": ""})
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            out.append({"file": name, "lines": 0, "preview": ""})
            continue
        lines = [ln for ln in text.splitlines() if ln.strip()]
        preview = _read_notepad_tail(path, max_chars=160)
        out.append(
            {
                "file": name,
                "lines": len(lines),
                "preview": preview,
                "path": str(path),
            }
        )
    return out


def _notepad_base_from_run_meta(run_meta: dict[str, Any] | None) -> Path | None:
    session_id = str((run_meta or {}).get("_session_id") or "").strip()
    home = Path.home() / ".agent-lab"
    if session_id:
        return home / "missions" / session_id
    ml = get_mission_loop(run_meta)
    for ref in ml.get("wisdom_refs") or []:
        if isinstance(ref, str) and ref.startswith("missions/"):
            parts = ref.split("/")
            if len(parts) >= 2 and parts[1]:
                return home / "missions" / parts[1]
    return None


def build_mission_wisdom_block(
    run_meta: dict[str, Any] | None,
    *,
    max_chars: int = MISSION_WISDOM_INJECT_CAP,
) -> str:
    """Phase 5: inject mission notepad tails into agent context."""
    from agent_lab.context_layers import mission_wisdom_layer_enabled

    if not mission_wisdom_layer_enabled(run_meta):
        return ""
    ml = get_mission_loop(run_meta)
    if not ml.get("enabled"):
        return ""
    phase = str(ml.get("phase") or "")
    if phase in _WISDOM_SKIP_PHASES:
        return ""
    base = _notepad_base_from_run_meta(run_meta)
    if base is None:
        return ""
    per_file = max(120, max_chars // len(_NOTEPAD_READ_ORDER))
    chunks: list[str] = []
    used = 0
    for name in _NOTEPAD_READ_ORDER:
        path = base / name
        tail = _read_notepad_tail(path, max_chars=per_file)
        if not tail:
            continue
        room = per_file - (used % per_file) if used else per_file
        if len(tail) > room and room > 0:
            tail = tail[-room:]
        chunks.append(f"[{name}]\n{tail}")
        used += len(tail)
        if used >= max_chars:
            break
    if not chunks:
        return ""
    block = "[Mission wisdom]\n" + "\n\n".join(chunks)
    return block[:max_chars]


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

    partial = ml.get("last_partial") if isinstance(ml.get("last_partial"), dict) else {}
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
    return pause_mission_loop(folder, reason="global_cancel")


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


def append_wisdom_note(
    folder: Path,
    *,
    line: str,
    filename: str = "learnings.md",
    action_index: int | None = None,
    provenance: str | None = None,
    auto_provenance: bool = True,
) -> str:
    """Append one line to a mission notepad with optional provenance."""
    if filename not in MISSION_NOTEPAD_FILES:
        filename = "learnings.md"
    ensure_mission_notepads(folder)
    path = mission_notepad_dir(folder) / filename
    text = (line or "").strip()
    prov = provenance
    if auto_provenance and not prov:
        prov = _format_provenance(folder, action_index=action_index)
    if text:
        entry = f"- {_now_iso()} {text}"
        if prov:
            entry += f" ({prov})"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"{entry}\n")

    def _ref(run: dict[str, Any]) -> dict[str, Any]:
        m = get_mission_loop(run)
        refs = list(m.get("wisdom_refs") or [])
        for name in MISSION_NOTEPAD_FILES:
            r = mission_notepad_rel(folder.name, name)
            if r not in refs:
                refs.append(r)
        m["wisdom_refs"] = refs
        run["mission_loop"] = m
        return run

    patch_run_meta(folder, _ref)
    return str(path)


def inject_wisdom_into_prompt(
    user: str,
    run_meta: dict[str, Any] | None,
) -> str:
    """Append [Mission wisdom] block to an execute/repair user prompt."""
    wisdom = build_mission_wisdom_block(run_meta)
    if not wisdom.strip():
        return user
    return f"{user.rstrip()}\n\n{wisdom.strip()}"
